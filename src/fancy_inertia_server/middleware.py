"""The ASGI middleware: attaches the per-request helper and guards the version.

The asset-version check lives HERE rather than in `Inertia.render` for a reason
the spec is explicit about (3.4, requirement 3): it must run **before** prop
resolution, or the `useAppUpdate` ping costs a full page render on every poll.
Checking it in the middleware means the route handler never runs at all on a
stale version — which is also why the conformance suite can assert it by making
prop resolution raise.
"""

from __future__ import annotations

from .asgi_types import ASGIApp, Receive, Scope, Send
from .inertia import Inertia, InertiaConfig
from .response import make_response

#: Methods the asset-version 409 applies to.
#:
#: GET only, deliberately. A 409 on a POST would leave a stale tab unable to
#: submit anything, and the client cannot retry a mutation it has already sent —
#: so version-gating a write turns a soft "please reload" into lost work.
VERSION_CHECKED_METHODS = frozenset({"GET"})


class InertiaMiddleware:
    """Wraps an ASGI app.

        app.add_middleware(InertiaMiddleware, config=InertiaConfig(...))

    or, for a raw ASGI stack:

        app = InertiaMiddleware(app, config)
    """

    def __init__(self, app: ASGIApp, config: InertiaConfig | None = None) -> None:
        self.app = app
        self.config = config or InertiaConfig()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            # websocket and lifespan pass straight through. A middleware that
            # swallows lifespan stops startup handlers from ever running.
            await self.app(scope, receive, send)
            return

        inertia = Inertia(scope=scope, config=self.config)
        scope[Inertia.SCOPE_KEY] = inertia

        # Starlette and FastAPI read request.state from here; exposing it means a
        # handler can reach the helper either way.
        state = scope.get("state")
        if isinstance(state, dict):
            state[Inertia.SCOPE_KEY] = inertia

        if self._is_stale(inertia, scope):
            # A BARE 409. No `X-Inertia-Location` — the client's
            # `isLocationVisit()` is `hasStatus(409) && hasHeader(
            # "x-inertia-location")`, so adding it here would make every stale
            # version read as an external redirect and the update banner would
            # never fire.
            response = make_response(409, b"", {"vary": "X-Inertia"})
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    def _is_stale(self, inertia: Inertia, scope: Scope) -> bool:
        if not inertia.is_inertia:
            return False

        if scope.get("method", "GET").upper() not in VERSION_CHECKED_METHODS:
            return False

        current = self.config.resolve_version()
        if not current:
            # No versioning configured means no redeploy detection, which is a
            # valid setup. Returning 409 against an empty version would 409
            # every request instead.
            return False

        sent = inertia.header("x-inertia-version")
        if sent is None:
            # A first visit has no version to send. Treating absent as stale
            # would 409 the client's very first navigation.
            return False

        return sent != current
