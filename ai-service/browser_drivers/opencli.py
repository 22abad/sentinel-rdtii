from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from .base import BrowserFetchError


class OpenCliBrowserDriver:
    """Thin Python client for the local OpenCLI browser bridge.

    The Node side intentionally lives in ``tools/opencli-browser-mcp`` so this
    FastAPI service can keep its Python dependency set unchanged. At runtime the
    bridge loads a built OpenCLI checkout via ``OPENCLI_PACKAGE_DIR`` or the
    sibling ``../opencli`` directory.
    """

    def __init__(self, server_path: str | None = None, node_bin: str | None = None):
        root = Path(__file__).resolve().parents[2]
        self.server_path = Path(
            server_path
            or os.getenv("OPENCLI_BROWSER_MCP_SERVER", "")
            or root / "tools" / "opencli-browser-mcp" / "server.mjs"
        )
        self.node_bin = node_bin or os.getenv("OPENCLI_NODE_BIN", "node")

    async def fetch_legal_content(
        self,
        url: str,
        *,
        timeout: int = 60000,
        selector: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "url": url,
            "timeoutMs": timeout,
            "selector": selector,
            "chunkSize": 200000,
            "session": os.getenv("OPENCLI_BROWSER_SESSION", "rdtii-ingest"),
            "siteSession": os.getenv("OPENCLI_SITE_SESSION", "persistent"),
            "windowMode": os.getenv("OPENCLI_WINDOW_MODE", "background"),
        }
        result = await self._call_once("fetch_url", payload, timeout=timeout)
        if result.get("type") == "text" and result.get("text"):
            return result
        message = result.get("message") or result.get("error") or "OpenCLI returned no text"
        raise BrowserFetchError(str(message))

    async def search_gov_law(
        self,
        query: str,
        *,
        limit: int = 10,
        timeout: int = 60000,
    ) -> list[dict[str, Any]]:
        payload = {
            "query": query,
            "limit": limit,
            "timeoutMs": timeout,
            "session": os.getenv("OPENCLI_BROWSER_SESSION", "rdtii-law-search"),
            "siteSession": os.getenv("OPENCLI_SITE_SESSION", "persistent"),
            "windowMode": os.getenv("OPENCLI_WINDOW_MODE", "background"),
        }
        result = await self._call_once("search_gov_law", payload, timeout=timeout)
        rows = result.get("results", [])
        return rows if isinstance(rows, list) else []

    async def _call_once(self, tool: str, payload: dict[str, Any], *, timeout: int) -> dict[str, Any]:
        if not self.server_path.exists():
            raise BrowserFetchError(f"OpenCLI bridge not found: {self.server_path}")

        try:
            proc = await asyncio.create_subprocess_exec(
                self.node_bin,
                str(self.server_path),
                "--once",
                tool,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise BrowserFetchError(
                f"Could not start OpenCLI bridge with {self.node_bin!r}: {exc}"
            ) from exc

        stdin = json.dumps(payload).encode("utf-8")
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(stdin),
                timeout=max(5, timeout / 1000 + 10),
            )
        except asyncio.TimeoutError as exc:
            await _terminate_process(proc)
            raise BrowserFetchError(f"OpenCLI bridge timed out after {timeout}ms") from exc
        except asyncio.CancelledError:
            await _terminate_process(proc)
            raise
        except OSError as exc:
            await _terminate_process(proc)
            raise BrowserFetchError(f"OpenCLI bridge communication failed: {exc}") from exc

        err_text = stderr.decode("utf-8", errors="replace").strip()
        out_text = stdout.decode("utf-8", errors="replace").strip()
        if proc.returncode != 0:
            detail = err_text or out_text or f"exit code {proc.returncode}"
            if out_text:
                try:
                    parsed = _loads_last_json_line(out_text)
                    if isinstance(parsed, dict) and parsed.get("error"):
                        detail = str(parsed["error"])
                except BrowserFetchError:
                    pass
            raise BrowserFetchError(f"OpenCLI bridge failed: {detail}")
        if not out_text:
            raise BrowserFetchError("OpenCLI bridge returned an empty response")
        data = _loads_last_json_line(out_text)
        if isinstance(data, dict) and data.get("ok") is False:
            raise BrowserFetchError(str(data.get("error") or "OpenCLI bridge error"))
        return data if isinstance(data, dict) else {"result": data}


async def _terminate_process(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    try:
        proc.kill()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except asyncio.TimeoutError:
        pass


def _loads_last_json_line(text: str) -> Any:
    for line in reversed([line.strip() for line in text.splitlines()]):
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    raise BrowserFetchError(f"OpenCLI bridge returned invalid JSON: {text[:300]}")
