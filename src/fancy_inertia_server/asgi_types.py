"""ASGI's own vocabulary, named once.

Spelled out here rather than depending on `asgiref.typing`, because a package
whose whole claim is "zero runtime dependencies" should not acquire one for four
type aliases. These match the ASGI 3.0 specification.

`InertiaResponse` is `Any` on purpose: `make_response` returns a
`starlette.responses.Response` when Starlette is importable and an `ASGIResponse`
otherwise, and the first of those is a type this package cannot name without
depending on it. Both are awaitable ASGI apps, which is the only property any
caller here relies on.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

#: What `make_response` hands back. See the module docstring.
InertiaResponse = Any
