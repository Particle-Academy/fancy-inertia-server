"""The Inertia server protocol, as a pure-ASGI adapter.

Zero runtime dependencies, which is a design constraint rather than an accident:
ASGI is a protocol of three dicts, so this works under Starlette, FastAPI, or any
other ASGI server without depending on any of them. Starlette is imported
*softly* in `response.py` only to hand FastAPI a type it recognises.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .asgi_types import InertiaResponse, Scope
from .response import make_response

PING_PROP = "__app_update_ping__"


def flatten_errors(errors: Mapping[str, Any]) -> dict[str, str]:
    """Framework validator output -> the flat map `useFancyForm` requires.

    `useFancyForm` types errors as `Partial<Record<keyof TData, string>>` — ONE
    string per field. A list reaches `<Input error={…}>` as "[object Array]" and
    type-checks nowhere, so flattening is the adapter's job and not the caller's.

    Dotted keys (`address.city`) pass through verbatim, because the client reads
    `form.errors[name]` with the same dot notation it asked with.
    """
    flat: dict[str, str] = {}

    for field_name, value in errors.items():
        if isinstance(value, str):
            flat[field_name] = value
        elif isinstance(value, (list, tuple)):
            # First message, matching what the Laravel adapter does — showing a
            # field's errors one at a time is the contract the UI was built for.
            if value:
                flat[field_name] = str(value[0])
        else:
            flat[field_name] = str(value)

    return flat


@dataclass
class InertiaConfig:
    """How this app answers the Inertia protocol.

    `version` is either a string or a zero-argument callable. A callable is the
    production shape: hash the Vite manifest so the value changes on deploy
    without a restart. A string is the test and development shape.
    """

    version: str | Callable[[], str] = ""
    root_template: Callable[[str], str] | None = None
    #: Called per request with the ASGI scope; its result is merged UNDER the
    #: page's own props, so a page can always override a shared value.
    share: Callable[[Scope], Mapping[str, Any]] | None = None
    #: Where the page object is mounted in the root template.
    root_id: str = "app"

    def resolve_version(self) -> str:
        return self.version() if callable(self.version) else self.version


@dataclass
class Inertia:
    """Per-request helper. Reach it with `Inertia.from_scope(request.scope)`."""

    scope: Scope
    config: InertiaConfig
    _shared: dict[str, Any] = field(default_factory=dict)

    SCOPE_KEY = "fancy_inertia"

    @classmethod
    def from_scope(cls, scope: Mapping[str, Any]) -> Inertia:
        try:
            found: Inertia = scope[cls.SCOPE_KEY]
            return found
        except KeyError:  # pragma: no cover - defensive
            raise RuntimeError(
                "InertiaMiddleware is not installed, so there is no Inertia helper on this "
                "request. Add it with app.add_middleware(InertiaMiddleware, config=…)."
            ) from None

    # -- request facts ----------------------------------------------------

    def header(self, name: str) -> str | None:
        wanted = name.lower().encode()
        for key, value in self.scope.get("headers", []):
            if key.lower() == wanted:
                decoded: str = value.decode("latin-1")
                return decoded
        return None

    @property
    def is_inertia(self) -> bool:
        return (self.header("x-inertia") or "").lower() == "true"

    @property
    def url(self) -> str:
        path = self.scope.get("path", "/")
        query = self.scope.get("query_string", b"").decode()
        return f"{path}?{query}" if query else path

    def share(self, **values: Any) -> None:
        """Add props to every page rendered on this request."""
        self._shared.update(values)

    # -- partial reloads --------------------------------------------------

    def _partial_keys(self, component: str) -> set[str] | None:
        """Which props this request asked for, or None for all of them.

        Returns None rather than an empty set when the request is not partial:
        empty is a legitimate answer (the app-update ping asks for a prop that
        does not exist and must receive nothing), so the two cannot share a
        representation. Conflating them is how the ping returns a full page.
        """
        requested = self.header("x-inertia-partial-data")
        if not requested:
            return None

        # Inertia scopes a partial reload to the component it came from. A
        # mismatch means the user navigated, so the full props are correct.
        partial_component = self.header("x-inertia-partial-component")
        if partial_component and partial_component != component:
            return None

        keys = {key.strip() for key in requested.split(",") if key.strip()}

        # `X-Inertia-Partial-Except` is honoured even though the rest of v2 is
        # not: IGNORING it would INVERT its meaning, returning precisely the
        # props the client asked to be spared. An unimplemented feature that
        # sends MORE data than requested is not a missing feature, it is a wrong
        # answer. See AGENTS.md "What 0.1.0 does not do".
        except_header = self.header("x-inertia-partial-except")
        if except_header:
            keys -= {key.strip() for key in except_header.split(",") if key.strip()}

        return keys

    # -- responses --------------------------------------------------------

    def render(self, component: str, props: Mapping[str, Any] | None = None) -> InertiaResponse:
        """Render a page: an Inertia JSON response, or the full HTML document."""
        merged: dict[str, Any] = {}

        if self.config.share is not None:
            merged.update(self.config.share(self.scope))

        merged.update(self._shared)
        merged.update(props or {})

        keys = self._partial_keys(component)
        if keys is not None:
            # An unknown key yields nothing rather than raising. The app-update
            # ping asks for `__app_update_ping__`, a prop no page declares, and
            # an adapter that errors here turns the update detector into a
            # permanent no-op. Spec 3.4 calls it the most likely silent breakage.
            merged = {key: value for key, value in merged.items() if key in keys}

        page = {
            "component": component,
            "props": merged,
            "url": self.url,
            "version": self.config.resolve_version(),
        }

        if self.is_inertia:
            return make_response(
                200,
                json.dumps(page).encode(),
                {
                    "content-type": "application/json; charset=utf-8",
                    "x-inertia": "true",
                    "vary": "X-Inertia",
                },
            )

        return self._html(page)

    def _html(self, page: dict[str, Any]) -> InertiaResponse:
        if self.config.root_template is None:
            raise RuntimeError(
                "No root_template configured, so the first byte of a page cannot be rendered. "
                "Set InertiaConfig(root_template=…) — see README 'Root template'."
            )

        # Single quotes delimit the attribute, so an apostrophe in a prop would
        # close it early. `&apos;` is the only escape the attribute needs; `<`
        # and `&` are escaped too so a prop can never open a tag.
        page_json = (
            json.dumps(page)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("'", "&apos;")
        )

        return make_response(
            200,
            self.config.root_template(page_json).encode(),
            {"content-type": "text/html; charset=utf-8", "vary": "X-Inertia"},
        )

    def location(self, url: str) -> InertiaResponse:
        """An EXTERNAL redirect: 409 WITH `X-Inertia-Location`.

        The client's `isLocationVisit()` is literally
        `hasStatus(409) && hasHeader("x-inertia-location")`, so this header is
        the only thing separating this from a stale-asset 409. Never send it on
        a version mismatch.
        """
        if self.is_inertia:
            return make_response(409, b"", {"x-inertia-location": url})

        return make_response(302, b"", {"location": url})

    def back(self, errors: Mapping[str, Any] | None = None, status: int = 303) -> InertiaResponse:
        """Redirect to the referrer, carrying flattened validation errors."""
        target = self.header("referer") or "/"
        flat = flatten_errors(errors or {})

        if self.is_inertia:
            # Re-rendering with the errors as props is what the client expects
            # after a failed submit; a bare redirect loses them.
            page = {
                "component": self.header("x-inertia-partial-component") or "",
                "props": {"errors": flat},
                "url": target,
                "version": self.config.resolve_version(),
            }
            return make_response(
                200,
                json.dumps(page).encode(),
                {
                    "content-type": "application/json; charset=utf-8",
                    "x-inertia": "true",
                    "vary": "X-Inertia",
                },
            )

        return make_response(status, b"", {"location": target})
