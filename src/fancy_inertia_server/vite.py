"""Asset version and root HTML, from the Vite manifest or the dev server.

Two jobs, both of which a Laravel consumer gets for free and a Python one does
not:

1. **An asset version that changes on deploy.** `useAppUpdate` compares the
   version it loaded with the one the server reports, so a value that never
   changes makes the detector a no-op and a value that changes per request makes
   every poll a false alarm. Hashing the manifest gives exactly one change per
   build, which is the property wanted.
2. **The script tags.** In development they point at the Vite dev server so HMR
   works; in production they come from the manifest. Getting this backwards is
   the usual cause of "it works locally and ships a blank page".
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any


def manifest_version(manifest_path: str | Path) -> Callable[[], str]:
    """An asset version that changes when the build does.

    Returns a CALLABLE, not a string, and reads the file each time it is asked.
    A value captured at import would never change in a long-running process, so
    the first deploy after start would be the last one ever detected — the
    failure is silent and looks exactly like "no new builds happened".

    A missing manifest yields `""`, which `InertiaMiddleware` reads as "no
    versioning configured" and therefore never 409s. That is the right failure:
    in development there is no manifest, and 409-ing every request because a
    production file is absent would make the package unusable locally.
    """
    path = Path(manifest_path)

    def version() -> str:
        try:
            raw = path.read_bytes()
        except OSError:
            return ""
        return hashlib.sha256(raw).hexdigest()[:12]

    return version


def _tags_from_manifest(manifest: dict[str, Any], entry: str, base: str) -> list[str]:
    chunk = manifest.get(entry)
    if chunk is None:
        raise KeyError(
            f"Vite manifest has no entry {entry!r}. Available: {', '.join(sorted(manifest))}"
        )

    tags: list[str] = []

    # CSS first: a stylesheet after the module is a flash of unstyled content.
    for css in chunk.get("css", []):
        tags.append(f'<link rel="stylesheet" href="{base}{css}">')

    tags.append(f'<script type="module" src="{base}{chunk["file"]}"></script>')

    return tags


def _dev_url(dev_server: str, path: str) -> str:
    """Join a dev-server origin to a path with exactly one slash between them.

    `dev_server="/"` is the same-origin setup, where Vite proxies pages to the
    backend and assets must be requested relatively. Joining that with an
    f-string produces `//@vite/client`, which a browser reads as a
    PROTOCOL-RELATIVE url — `http://@vite/client` — and so leaves the origin
    entirely. It fails as a DNS error rather than a 404, which is a long way from
    where the mistake was made.
    """
    return f"{dev_server.rstrip('/')}/{path.lstrip('/')}"


def react_refresh_preamble(dev_server: str) -> str:
    """The script `@vitejs/plugin-react` requires before any component loads.

    Without it the plugin throws *"@vitejs/plugin-react can't detect preamble"*
    from inside a component, which reads as a React error rather than a missing
    script tag. Laravel emits the same thing from `@viteReactRefresh`; this is
    transcribed from `Illuminate\\Foundation\\Vite::reactRefresh()` so it matches
    the reference implementation rather than a recollection of it.

    Reported by the first consumer within a day of 0.1.0, who had to supply their
    own `assets` callable to work around its absence.
    """
    return (
        '<script type="module">'
        f"import RefreshRuntime from '{_dev_url(dev_server, '@react-refresh')}';"
        "RefreshRuntime.injectIntoGlobalHook(window);"
        "window.$RefreshReg$ = () => {};"
        "window.$RefreshSig$ = () => (type) => type;"
        "window.__vite_plugin_react_preamble_installed__ = true"
        "</script>"
    )


def asset_tags(
    *,
    entry: str = "resources/js/app.tsx",
    manifest_path: str | Path = "public/build/manifest.json",
    base: str = "/build/",
    dev_server: str | None = None,
    react_refresh: bool = True,
) -> Callable[[], str]:
    """The `<script>`/`<link>` tags for the root template.

    Pass `dev_server="http://localhost:5173"` in development and leave it None in
    production. The choice is the caller's rather than sniffed from an
    environment variable, because guessing wrong is invisible: a production
    deploy pointing at a dev server renders a blank page with no error.

    `dev_server="/"` is the same-origin form, for setups where Vite proxies pages
    to the backend.

    `react_refresh` defaults to **True**, and only applies in dev mode. The
    default is on because this package exists to serve `fancy-inertia`, which is
    React — and the two failures are not symmetrical. Omitting the preamble for a
    React consumer breaks every component with an error that names React rather
    than the missing tag; emitting it for a non-React consumer costs one 404 on
    `/@react-refresh` in development and nothing else. Set it to False for a
    Vue/Svelte client or a React setup not using `@vitejs/plugin-react`.
    """

    def tags() -> str:
        if dev_server:
            parts = []

            # BEFORE the entry module. The preamble installs a global that
            # plugin-react's component transform looks for, so running it after
            # the app module is the same as not running it at all.
            if react_refresh:
                parts.append(react_refresh_preamble(dev_server))

            parts.append(
                f'<script type="module" src="{_dev_url(dev_server, "@vite/client")}"></script>'
            )
            parts.append(f'<script type="module" src="{_dev_url(dev_server, entry)}"></script>')

            return "".join(parts)

        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        return "".join(_tags_from_manifest(manifest, entry, base))

    return tags


def root_template(
    *,
    assets: Callable[[], str],
    title: str = "",
    root_id: str = "app",
    lang: str = "en",
    head: str = "",
) -> Callable[[str], str]:
    """A default root document. Replace it entirely whenever you need to.

    `page_json` arrives already escaped for a single-quoted attribute.
    """

    def render(page_json: str) -> str:
        return (
            f'<!DOCTYPE html><html lang="{lang}"><head>'
            '<meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{title}</title>"
            f"{head}"
            f"{assets()}"
            "</head><body>"
            f"<div id=\"{root_id}\" data-page='{page_json}'></div>"
            "</body></html>"
        )

    return render
