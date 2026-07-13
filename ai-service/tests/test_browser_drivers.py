from __future__ import annotations

import pytest


def test_normalize_browser_mode():
    from browser_drivers import normalize_browser_mode

    assert normalize_browser_mode(None) == "auto"
    assert normalize_browser_mode("") == "auto"
    assert normalize_browser_mode("OPENCLI") == "opencli"
    assert normalize_browser_mode("playwright") == "playwright"
    assert normalize_browser_mode("something-else") == "auto"


@pytest.mark.anyio
async def test_opencli_driver_calls_once_bridge(tmp_path):
    from browser_drivers import OpenCliBrowserDriver

    bridge = tmp_path / "bridge.mjs"
    bridge.write_text(
        """
const chunks = [];
process.stdin.on('data', c => chunks.push(c));
process.stdin.on('end', () => {
  const args = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  process.stdout.write(JSON.stringify({
    type: 'text',
    url: args.url,
    text: 'Rendered legal text',
    metadata: { source: 'test-bridge', session: args.session }
  }));
});
""".strip(),
        encoding="utf-8",
    )

    driver = OpenCliBrowserDriver(server_path=str(bridge), node_bin="node")
    result = await driver.fetch_legal_content("https://example.test/law", timeout=5000)

    assert result["type"] == "text"
    assert result["url"] == "https://example.test/law"
    assert result["text"] == "Rendered legal text"
    assert result["metadata"]["source"] == "test-bridge"


@pytest.mark.anyio
async def test_fetch_legal_content_opencli_mode_uses_opencli_without_playwright(monkeypatch):
    import crawler

    calls = []

    async def fake_precheck(_url):
        calls.append("precheck")
        return None

    async def fake_http(_url, _timeout):
        calls.append("http")
        return None

    async def fake_opencli(url, timeout):
        calls.append("opencli")
        return {
            "type": "text",
            "url": url,
            "text": f"opencli rendered with {timeout}",
            "metadata": {"source": "opencli"},
        }

    def fail_playwright():
        raise AssertionError("Playwright should not be opened in browser_mode=opencli")

    monkeypatch.setattr(crawler, "_precheck_url", fake_precheck)
    monkeypatch.setattr(crawler, "_try_http_fallback", fake_http)
    monkeypatch.setattr(crawler, "_try_opencli_fetch", fake_opencli)
    monkeypatch.setattr(crawler, "async_playwright", fail_playwright)

    result = await crawler.fetch_legal_content(
        "https://example.test/law",
        timeout=12345,
        browser_mode="opencli",
    )

    assert result == {
        "type": "text",
        "url": "https://example.test/law",
        "text": "opencli rendered with 12345",
        "metadata": {"source": "opencli"},
    }
    assert calls == ["opencli"]


@pytest.mark.anyio
async def test_opencli_driver_reports_bridge_errors(tmp_path):
    from browser_drivers import BrowserFetchError, OpenCliBrowserDriver

    bridge = tmp_path / "bridge.mjs"
    bridge.write_text(
        "process.stdout.write(JSON.stringify({ ok: false, error: 'not configured' }));",
        encoding="utf-8",
    )

    driver = OpenCliBrowserDriver(server_path=str(bridge), node_bin="node")
    with pytest.raises(BrowserFetchError, match="not configured"):
        await driver.fetch_legal_content("https://example.test/law", timeout=5000)


@pytest.mark.anyio
async def test_opencli_driver_missing_node_is_browser_fetch_error(tmp_path):
    from browser_drivers import BrowserFetchError, OpenCliBrowserDriver

    bridge = tmp_path / "bridge.mjs"
    bridge.write_text("process.stdout.write('{}');", encoding="utf-8")

    driver = OpenCliBrowserDriver(
        server_path=str(bridge),
        node_bin="/definitely/missing/node",
    )
    with pytest.raises(BrowserFetchError, match="Could not start OpenCLI bridge"):
        await driver.fetch_legal_content("https://example.test/law", timeout=5000)


@pytest.mark.anyio
async def test_opencli_driver_parses_last_json_stdout_line(tmp_path):
    from browser_drivers import OpenCliBrowserDriver

    bridge = tmp_path / "bridge.mjs"
    bridge.write_text(
        """
console.log('debug: bridge warmup');
process.stdout.write(JSON.stringify({
  type: 'text',
  url: 'https://example.test/law',
  text: 'Rendered legal text after logs'
}) + '\\n');
""".strip(),
        encoding="utf-8",
    )

    driver = OpenCliBrowserDriver(server_path=str(bridge), node_bin="node")
    result = await driver.fetch_legal_content("https://example.test/law", timeout=5000)

    assert result["type"] == "text"
    assert result["text"] == "Rendered legal text after logs"
