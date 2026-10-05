"""Dev-mode asset tags, including the React Fast Refresh preamble.

Both cases here were reported by the YouGene estate after integrating 0.1.0 —
the first consumer finding, in an afternoon, two things the conformance fixtures
had no opinion about because they are about HTML rather than the Inertia
protocol.

## The preamble

`@vitejs/plugin-react` refuses to run without a global it installs itself, and it
fails loudly inside components: *"@vitejs/plugin-react can't detect preamble"*.
Laravel emits it from `@viteReactRefresh`; the exact script is transcribed from
`Illuminate\\Foundation\\Vite::reactRefresh()` rather than from the report, so
this matches the reference implementation and not someone's recollection of it.

**Order matters.** The preamble must run before the entry module, or the global
is set after the components that look for it. Laravel places
`@viteReactRefresh` above `@vite(...)` for this reason, and asserting only that
both tags are *present* would miss it.
"""

from __future__ import annotations

import json

import pytest

from fancy_inertia_server.vite import asset_tags

DEV = "http://localhost:5173"
ENTRY = "resources/js/app.tsx"


def test_dev_mode_emits_the_react_refresh_preamble_by_default():
    html = asset_tags(entry=ENTRY, dev_server=DEV)()

    assert "RefreshRuntime.injectIntoGlobalHook(window)" in html
    assert "window.__vite_plugin_react_preamble_installed__ = true" in html
    assert f"{DEV}/@react-refresh" in html


def test_the_preamble_comes_before_the_entry_module():
    html = asset_tags(entry=ENTRY, dev_server=DEV)()

    preamble = html.index("__vite_plugin_react_preamble_installed__")
    entry = html.index(ENTRY)

    assert preamble < entry, (
        "the preamble must run BEFORE the entry module, or plugin-react's global "
        "is set after the components looking for it"
    )


def test_react_refresh_can_be_turned_off():
    html = asset_tags(entry=ENTRY, dev_server=DEV, react_refresh=False)()

    assert "RefreshRuntime" not in html
    assert "@vite/client" in html
    assert ENTRY in html


def test_the_preamble_is_dev_only(tmp_path):
    # In production the module is a built asset; a preamble importing from a dev
    # server that is not running would simply 404.
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({ENTRY: {"file": "assets/app-abc.js"}}), encoding="utf-8")

    html = asset_tags(entry=ENTRY, manifest_path=manifest)()

    assert "RefreshRuntime" not in html
    assert "assets/app-abc.js" in html


# ---------------------------------------------------------------------------
# Same-origin dev server
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dev", ["/", ""])
def test_a_same_origin_dev_server_does_not_double_the_slash(dev):
    """`dev_server="/"` is the Vite-proxies-the-backend setup.

    Naive f-string joining produces `//@vite/client`, which the browser reads as
    a PROTOCOL-RELATIVE URL — `http://@vite/client` — so it leaves the origin
    entirely. It fails as a DNS error rather than a 404, which is why it is worth
    a test rather than a glance.
    """
    if dev == "":
        pytest.skip("empty string means production; covered by the manifest test")

    html = asset_tags(entry=ENTRY, dev_server=dev)()

    assert "//@vite/client" not in html
    assert 'src="/@vite/client"' in html
    assert f'src="/{ENTRY}"' in html
    assert "from '/@react-refresh'" in html


def test_a_trailing_slash_on_an_absolute_dev_server_is_tolerated():
    html = asset_tags(entry=ENTRY, dev_server=DEV + "/")()

    assert f"{DEV}//" not in html
    assert f'src="{DEV}/@vite/client"' in html


def test_a_leading_slash_on_the_entry_is_tolerated():
    # Vite config and Python config disagree about this constantly.
    html = asset_tags(entry="/" + ENTRY, dev_server=DEV)()

    assert f"{DEV}//" not in html
    assert f'src="{DEV}/{ENTRY}"' in html
