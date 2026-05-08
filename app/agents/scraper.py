import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from app.config import get_settings

log = logging.getLogger(__name__)


class ScrapedContent(BaseModel):
    url: str
    title: str = ""
    theme: str = Field(default="", description="Краткая тема (description / og:description)")
    raw_text: str = Field(default="", description="Очищенный текст страницы (до 20 000 симв)")
    theses: list[str] = Field(default_factory=list, description="Эвристические тезисы")


class ScraperError(Exception):
    """Базовый класс ошибок скрейпера. Содержит код для маппинга в russian message."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


MAX_CONTENT_BYTES = 1_500_000
MAX_RAW_TEXT_CHARS = 20_000
MAX_URL_LENGTH = 2_000
ALLOWED_SCHEMES = {"http", "https"}
USER_AGENT = (
    "Mozilla/5.0 (compatible; ContentAgentBot/0.1; +https://github.com/badeev777-svg/content-agent-bot)"
)


def _is_blocked_host(hostname: str) -> bool:
    if not hostname:
        return True
    lowered = hostname.lower()
    if lowered in {"localhost", "localhost.localdomain"}:
        return True
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise ScraperError("dns", f"hostname {hostname} not resolvable") from None
    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return True
    return False


def validate_url(url: str) -> str:
    if not url or len(url) > MAX_URL_LENGTH:
        raise ScraperError("bad_url", "пустой URL или слишком длинный")
    parsed = urlparse(url.strip())
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ScraperError("bad_scheme", f"схема {parsed.scheme!r} не поддерживается")
    if not parsed.hostname:
        raise ScraperError("bad_url", "не могу извлечь hostname из URL")
    if _is_blocked_host(parsed.hostname):
        raise ScraperError("ssrf", f"hostname {parsed.hostname} запрещён")
    return url.strip()


async def fetch_html(url: str, *, timeout: float | None = None) -> str:
    timeout_val = timeout or get_settings().scraper_timeout_seconds
    try:
        async with httpx.AsyncClient(
            timeout=timeout_val,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "ru,en;q=0.7"},
            max_redirects=5,
        ) as client:
            resp = await client.get(url)
    except httpx.TimeoutException as e:
        raise ScraperError("timeout", str(e)) from e
    except httpx.RequestError as e:
        raise ScraperError("network", str(e)) from e

    if resp.status_code == 404:
        raise ScraperError("not_found", "страница не существует")
    if resp.status_code == 403:
        raise ScraperError("forbidden", "сайт блокирует ботов")
    if 500 <= resp.status_code < 600:
        raise ScraperError("server_error", f"upstream вернул {resp.status_code}")
    if resp.status_code >= 400:
        raise ScraperError("http_error", f"upstream вернул {resp.status_code}")

    content = resp.content[:MAX_CONTENT_BYTES]
    encoding = resp.encoding or "utf-8"
    try:
        return content.decode(encoding, errors="replace")
    except LookupError:
        return content.decode("utf-8", errors="replace")


def _strip_html_noise(soup: BeautifulSoup) -> None:
    for tag_name in ("script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg"):
        for tag in soup.find_all(tag_name):
            tag.decompose()


def extract(html: str, url: str) -> ScrapedContent:
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        title = og_title["content"].strip() or title

    theme = ""
    desc = soup.find("meta", attrs={"name": "description"})
    if desc and desc.get("content"):
        theme = desc["content"].strip()
    og_desc = soup.find("meta", attrs={"property": "og:description"})
    if og_desc and og_desc.get("content"):
        theme = og_desc["content"].strip() or theme

    _strip_html_noise(soup)

    main = soup.find("article") or soup.find("main") or soup.body or soup
    paragraphs: list[str] = []
    for p in main.find_all(["p", "h1", "h2", "h3", "li"]):
        text = p.get_text(separator=" ", strip=True)
        if len(text) >= 30:
            paragraphs.append(text)

    raw_text = "\n\n".join(paragraphs)[:MAX_RAW_TEXT_CHARS]

    theses = _heuristic_theses(paragraphs)

    return ScrapedContent(url=url, title=title, theme=theme, raw_text=raw_text, theses=theses)


def _heuristic_theses(paragraphs: list[str], limit: int = 5) -> list[str]:
    """Простая эвристика: первые N длинных параграфов как «тезисы». LLM сделает лучше потом."""
    out: list[str] = []
    for p in paragraphs:
        if 40 <= len(p) <= 400:
            out.append(p)
        if len(out) >= limit:
            break
    return out


async def scrape(url: str) -> ScrapedContent:
    url = validate_url(url)
    log.info("scraping url=%s", url)
    html = await fetch_html(url)
    content = extract(html, url)
    log.info(
        "scraped url=%s title=%r theses=%d chars=%d",
        url,
        content.title[:60],
        len(content.theses),
        len(content.raw_text),
    )
    return content
