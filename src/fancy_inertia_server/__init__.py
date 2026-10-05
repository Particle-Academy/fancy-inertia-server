"""ASGI middleware speaking the Inertia SERVER protocol.

`@particle-academy/fancy-inertia` is the CLIENT half only. Laravel has
inertia-laravel; Python had nothing, which left the kit's own Python start guide
pointing at an adapter that did not exist. This is that adapter, for
Starlette/FastAPI.

    from fancy_inertia_server import InertiaConfig, InertiaMiddleware, inertia
    from fancy_inertia_server.vite import asset_tags, manifest_version, root_template

    assets = asset_tags(dev_server="http://localhost:5173" if DEBUG else None)

    app.add_middleware(
        InertiaMiddleware,
        config=InertiaConfig(
            version=manifest_version("public/build/manifest.json"),
            root_template=root_template(assets=assets, title="YouGene"),
        ),
    )

    @app.get("/genome/{sample_id}")
    async def genome(request: Request, sample_id: str):
        return inertia(request).render("Genome/Show", {"sample": load(sample_id)})
"""

from __future__ import annotations

from typing import Any

from .inertia import PING_PROP, Inertia, InertiaConfig, flatten_errors
from .middleware import InertiaMiddleware
from .response import ASGIResponse, make_response

__all__ = [
    "PING_PROP",
    "ASGIResponse",
    "Inertia",
    "InertiaConfig",
    "InertiaMiddleware",
    "flatten_errors",
    "inertia",
    "make_response",
]

__version__ = "0.2.0"


def inertia(request: Any) -> Inertia:
    """The per-request helper, from a Starlette/FastAPI `Request` or a raw scope.

    Takes either so a handler does not have to know which it has — `request.scope`
    when it is a Request object, the mapping itself when it is a bare ASGI scope.
    """
    scope = getattr(request, "scope", request)
    return Inertia.from_scope(scope)
