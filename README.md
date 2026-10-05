# fancy-inertia-server

ASGI middleware speaking the **Inertia server protocol**, so a Starlette or
FastAPI backend can run [`@particle-academy/fancy-inertia`](https://www.npmjs.com/package/@particle-academy/fancy-inertia)
— or any Inertia React client — unchanged.

`fancy-inertia` is the **client half only**. Laravel has `inertia-laravel`;
Python had nothing, which left the kit's own Python start guide pointing at an
adapter that did not exist. This is that adapter.

**Zero runtime dependencies.** ASGI is a protocol of three dicts, so none are
needed. Starlette is imported *softly*, only to hand FastAPI a response type it
recognises — see `response.py`. Nothing here makes a network call or emits
telemetry.

```bash
pip install fancy-inertia-server
```

Not on PyPI yet. Until it is:

```bash
pip install git+https://github.com/Particle-Academy/fancy-inertia-server@main
```

## Quick start

```python
from fastapi import FastAPI, Request
from fancy_inertia_server import InertiaConfig, InertiaMiddleware, inertia
from fancy_inertia_server.vite import asset_tags, manifest_version, root_template

DEBUG = True

assets = asset_tags(
    entry="resources/js/app.tsx",
    dev_server="http://localhost:5173" if DEBUG else None,
)

app = FastAPI()
app.add_middleware(
    InertiaMiddleware,
    config=InertiaConfig(
        version=manifest_version("public/build/manifest.json"),
        root_template=root_template(assets=assets, title="My app"),
    ),
)


@app.get("/users/{user_id}")
async def show_user(request: Request, user_id: int):
    return inertia(request).render("Users/Show", {"user": load(user_id)})
```

That is the whole integration. A request without `X-Inertia` gets the HTML
document with the page object in `data-page`; a request with it gets the page
object as JSON.

## What you get

| | |
|---|---|
| **Page objects** | `component` / `props` / `url` / `version`, as both first-byte HTML and `X-Inertia` JSON |
| **Partial reloads** | `X-Inertia-Partial-Data` and `X-Inertia-Partial-Except`, scoped to the requesting component |
| **Redeploy detection** | asset versioning + a bare `409`, which is what `useAppUpdate` needs |
| **Validation errors** | `props.errors` flattened to one string per field, dotted keys intact |
| **External redirects** | `409` **with** `X-Inertia-Location` |
| **Shared props** | per-request via `inertia(request).share(...)`, or app-wide via `InertiaConfig(share=...)` |
| **Vite** | asset version from the manifest, script tags from the dev server or the manifest |

## Shared props

Two levels, and page props win over both:

```python
# App-wide, called once per request with the ASGI scope.
InertiaConfig(share=lambda scope: {"auth": {"user": current_user(scope)}})

# Per request, from anywhere that has the request.
inertia(request).share(flash=pop_flash(request))
```

## Root template

`root_template()` is a convenience, not a requirement. Pass any
`Callable[[str], str]` — it receives the page JSON already escaped for a
single-quoted attribute, and returns the whole document:

```python
def my_template(page_json: str) -> str:
    return f"<!DOCTYPE html>…<div id='app' data-page='{page_json}'></div>…"


InertiaConfig(root_template=my_template)
```

## Three things that will bite a hand-rolled adapter

These are why this package exists rather than fifty lines in your app. Each is
covered by a conformance fixture.

1. **`useAppUpdate` pings for a prop that does not exist.** It sends
   `X-Inertia-Partial-Data: __app_update_ping__`, which no page declares. An
   adapter that errors on an unknown partial key turns the update detector into
   a permanent no-op, or makes every deploy 500. Here, unknown keys resolve to
   nothing — for any name, not just that one.

2. **A stale asset version is a BARE `409`.** `409` *with* `X-Inertia-Location`
   means an external redirect; the client's `isLocationVisit()` is literally
   `hasStatus(409) && hasHeader("x-inertia-location")`. Sending the header on a
   version mismatch means the update banner never appears, because every stale
   response is read as a redirect.

3. **`props.errors` must be flat.** `{"email": "Required."}`, never
   `{"email": ["Required."]}` — a list renders as `[object Array]` into
   `<Input error={…}>`. Use `flatten_errors()` on your validator output; dotted
   keys like `address.city` pass through verbatim, because the client reads
   `form.errors[name]` with the same notation it asked with.

The version check runs in the middleware, **before** your route handler, so a
stale-version ping costs nothing.

## What 0.1.0 does not do

Stated rather than discovered:

- **No SSR.** `fancy-inertia`'s `createFancyServer` is a separate Node process;
  this adapter renders CSR only. The client degrades to CSR with no
  configuration.
- **No Inertia v3 props** — `deferredProps`, `mergeProps`, `encryptHistory`,
  `clearHistory`. Pin `@inertiajs/react` to `^2`. This is the one row the kit's
  spec prices moderate-hard, and dropping it is what makes this package small.
- **No Django or WSGI.** ASGI only. Django support is deferred to a consumer who
  wants it, rather than guessed at now.
- **No server-rendered SEO baseline.** Set `clientOnly: false` on the client.

`X-Inertia-Partial-Except` **is** honoured despite the rest of v2 being out of
scope, because ignoring it would *invert* its meaning and return precisely the
props the caller asked to be spared. An unimplemented feature that sends more
data than requested is not a missing feature, it is a wrong answer.

## Conformance

`tests/test_conformance.py` is fixtures A1–A7 of the kit's language-agnostic
Inertia server contract, transcribed one test per fixture. That contract was
derived by reading the `@inertiajs/core` client source rather than the Inertia
documentation, so it asserts what the client actually does.

```bash
pip install -e . --group dev
pytest
```

## Licence

MIT.
