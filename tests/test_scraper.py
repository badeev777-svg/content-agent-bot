import httpx
import pytest

from app.agents import scraper
from app.agents.scraper import ScraperError, extract, validate_url


SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>Тестовая статья</title>
  <meta name="description" content="Краткое описание для теста">
  <meta property="og:title" content="OG: Тестовая статья">
  <meta property="og:description" content="OG описание">
  <script>console.log("noise");</script>
</head>
<body>
  <nav>menu</nav>
  <main>
    <article>
      <h1>Главный заголовок статьи</h1>
      <p>Это первый параграф с достаточным количеством текста, чтобы попасть в тезисы.</p>
      <p>Второй параграф тоже не слишком короткий и должен оказаться в выдаче.</p>
      <p>short</p>
      <h2>Подзаголовок раздела о маркетинге</h2>
      <p>Третий параграф, в котором рассказывается про целевую аудиторию и её боли.</p>
    </article>
  </main>
  <footer>footer noise</footer>
</body>
</html>
"""


def test_validate_url_https_passes() -> None:
    assert validate_url("https://example.com/article") == "https://example.com/article"


def test_validate_url_strips_whitespace() -> None:
    assert validate_url("  https://example.com  ") == "https://example.com"


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com",
        "javascript:alert(1)",
        "file:///etc/passwd",
        "",
        "not-a-url",
    ],
)
def test_validate_url_rejects_bad_schemes(url: str) -> None:
    with pytest.raises(ScraperError):
        validate_url(url)


@pytest.mark.parametrize(
    "host",
    [
        "http://localhost",
        "http://127.0.0.1/api",
        "http://10.0.0.1",
        "http://192.168.1.1",
        "http://[::1]/",
    ],
)
def test_validate_url_blocks_ssrf(host: str) -> None:
    with pytest.raises(ScraperError) as ei:
        validate_url(host)
    assert ei.value.code in {"ssrf", "dns"}


def test_extract_title_and_og() -> None:
    content = extract(SAMPLE_HTML, "https://example.com/x")
    assert content.title == "OG: Тестовая статья"  # og:title перебивает <title>
    assert content.theme == "OG описание"


def test_extract_finds_paragraphs_as_theses() -> None:
    content = extract(SAMPLE_HTML, "https://example.com/x")
    assert len(content.theses) >= 3
    assert all(40 <= len(t) <= 400 for t in content.theses)
    assert "short" not in content.theses
    assert all("noise" not in t for t in content.theses)


def test_extract_strips_script_and_nav() -> None:
    content = extract(SAMPLE_HTML, "https://example.com/x")
    assert "console.log" not in content.raw_text
    assert "footer noise" not in content.raw_text
    assert "menu" not in content.raw_text


@pytest.mark.asyncio
async def test_scrape_full_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch(url: str, *, timeout: float | None = None) -> str:
        return SAMPLE_HTML

    monkeypatch.setattr(scraper, "fetch_html", fake_fetch)
    content = await scraper.scrape("https://example.com/post")
    assert content.url == "https://example.com/post"
    assert content.title.startswith("OG:")
    assert content.theses


@pytest.mark.asyncio
async def test_fetch_translates_404(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResp:
        status_code = 404
        content = b""
        encoding = "utf-8"

    class FakeClient:
        def __init__(self, *a, **kw): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def get(self, url): return FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    with pytest.raises(ScraperError) as ei:
        await scraper.fetch_html("https://example.com/missing")
    assert ei.value.code == "not_found"


@pytest.mark.asyncio
async def test_fetch_translates_403(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResp:
        status_code = 403
        content = b""
        encoding = "utf-8"

    class FakeClient:
        def __init__(self, *a, **kw): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def get(self, url): return FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    with pytest.raises(ScraperError) as ei:
        await scraper.fetch_html("https://example.com/blocked")
    assert ei.value.code == "forbidden"


@pytest.mark.asyncio
async def test_fetch_translates_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        def __init__(self, *a, **kw): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def get(self, url):
            raise httpx.TimeoutException("read timeout")

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    with pytest.raises(ScraperError) as ei:
        await scraper.fetch_html("https://example.com/slow")
    assert ei.value.code == "timeout"
