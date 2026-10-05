"""Responses that satisfy a raw ASGI server AND FastAPI, without a hard dependency.

## Why this file exists

The package declares zero runtime dependencies, so it cannot import Starlette.
But FastAPI route handlers are not raw ASGI: FastAPI inspects what a handler
returns and runs it through serialization *unless* it is a
`starlette.responses.Response`. Returning a plain ASGI callable there would be
JSON-encoded into nonsense rather than sent.

So Starlette is imported **softly**, once, at first use. When it is present —
which it always is under FastAPI, since FastAPI depends on it — a real
`Response` is returned and FastAPI passes it through untouched. When it is
absent, the fallback is a raw ASGI app, which is what plain Starlette routing
and any other ASGI framework will happily await.

The consumer gains no new dependency either way. That is the point: a hard
`starlette` requirement would make this package unusable from a non-Starlette
ASGI stack for no benefit, and a FastAPI-only package would not have been worth
writing.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .asgi_types import InertiaResponse, Receive, Scope, Send

_starlette_response: Any = None
_checked = False


def _starlette() -> Any:
    """The Starlette Response class, or None. Resolved once."""
    global _starlette_response, _checked

    if not _checked:
        _checked = True
        try:
            from starlette.responses import Response

            _starlette_response = Response
        except ImportError:  # pragma: no cover - exercised by the no-starlette run
            _starlette_response = None

    return _starlette_response


class ASGIResponse:
    """A minimal ASGI response, for stacks without Starlette."""

    def __init__(self, status: int, body: bytes, headers: Mapping[str, str]) -> None:
        self.status = status
        self.body = body
        self.headers = dict(headers)

        # content-length is not optional: without it a client must wait for the
        # connection to close to know the body ended, which turns every response
        # into a hang under keep-alive.
        self.headers.setdefault("content-length", str(len(body)))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": self.status,
                "headers": [
                    (key.lower().encode("latin-1"), value.encode("latin-1"))
                    for key, value in self.headers.items()
                ],
            }
        )
        await send({"type": "http.response.body", "body": self.body})


def make_response(
    status: int, body: bytes, headers: Mapping[str, str] | None = None
) -> InertiaResponse:
    """A response the host framework will recognise."""
    headers = dict(headers or {})
    starlette_response = _starlette()

    if starlette_response is not None:
        return starlette_response(content=body, status_code=status, headers=headers)

    return ASGIResponse(status, body, headers)
