"""A tiny ASGI driver, so the suite needs no HTTP client.

The package has zero runtime dependencies on purpose, and a test harness that
dragged in `httpx` or `starlette` would quietly make that claim untrue for
anyone running the suite — and would test those libraries' request handling as
much as ours.

ASGI is a protocol of three dicts, so driving it directly is about forty lines
and exercises exactly the surface a real server would.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field


@dataclass
class Response:
    status: int = 0
    headers: list[tuple[bytes, bytes]] = field(default_factory=list)
    body: str = ""

    def header(self, name: str) -> str | None:
        """Case-insensitive lookup. Returns None when absent.

        Absent and empty must stay distinguishable: `x-inertia-location` being
        missing is the whole of fixture A3, and a `""` default would make a
        stale-version 409 indistinguishable from a location visit.
        """
        wanted = name.lower().encode()
        for key, value in self.headers:
            if key.lower() == wanted:
                return value.decode()
        return None

    def data_page(self) -> dict:
        """The page object out of the mount element's `data-page` attribute."""
        match = re.search(r"data-page='(.*?)'></div>", self.body, re.S)
        assert match is not None, f"no data-page attribute in:\n{self.body[:400]}"
        return json.loads(match.group(1))


class Client:
    """Calls an ASGI app directly, with no socket and no event loop reuse."""

    def __init__(self, app) -> None:
        self.app = app

    def get(self, path: str, headers: dict[str, str] | None = None) -> Response:
        return self.request("GET", path, headers)

    def request(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        body: bytes = b"",
    ) -> Response:
        return asyncio.run(self._call(method, path, headers or {}, body))

    async def _call(self, method: str, path: str, headers: dict[str, str], body: bytes) -> Response:
        path, _, query = path.partition("?")

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query.encode(),
            "root_path": "",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "state": {},
        }

        received = False

        async def receive():
            nonlocal received
            if received:
                return {"type": "http.disconnect"}
            received = True
            return {"type": "http.request", "body": body, "more_body": False}

        response = Response()
        chunks: list[bytes] = []

        async def send(message):
            if message["type"] == "http.response.start":
                response.status = message["status"]
                response.headers = list(message.get("headers", []))
            elif message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))

        await self.app(scope, receive, send)
        response.body = b"".join(chunks).decode()
        return response
