# Using fancy-inertia-server — guide for agents

How an agent installs and uses this package in a consumer app. What the package
is, is in [README.md](./README.md). Notes for working ON this repo's code are in
[CONTRIBUTING.md](./CONTRIBUTING.md).

## Install

Not on PyPI yet. Until it is:

```bash
pip install git+https://github.com/Particle-Academy/fancy-inertia-server@main
```

Once published: `pip install fancy-inertia-server`.

- Python `>=3.11`. Zero runtime dependencies; Starlette is used when present.
- The client half is `@particle-academy/fancy-inertia` (or any Inertia React
  client). Pin `@inertiajs/react` to `^2`.

## Find it on the Fancy MCP server

Not listed on the Fancy MCP catalog server
(`https://ui.particle.academy/mcp`, MCP id `fancy-ui`) yet; it appears there
once published. Look for it later with `search-backend-packages` (stack
`python`). The client, `fancy-inertia`, is listed: `search-components` or
`install-instructions` with the slug `fancy-inertia`.

## API essentials

```python
from fastapi import FastAPI, Request
from fancy_inertia_server import InertiaConfig, InertiaMiddleware, inertia
from fancy_inertia_server.vite import asset_tags, manifest_version, root_template

assets = asset_tags(entry="resources/js/app.tsx", dev_server="http://localhost:5173")

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

- Exports: `InertiaMiddleware`, `InertiaConfig`, `inertia(request)` (takes a
  Starlette / FastAPI `Request` or a bare ASGI scope), `flatten_errors`,
  `make_response`; Vite helpers in `fancy_inertia_server.vite`.
- `render(component, props)` answers HTML with `data-page` for a normal request
  and page-object JSON for an `X-Inertia` one.
- Shared props: app-wide `InertiaConfig(share=lambda scope: {...})`, or per
  request `inertia(request).share(...)`. Page props win over both.
- `root_template` can be any `Callable[[str], str]`; it receives the page JSON
  already escaped for a single-quoted attribute.
- `asset_tags(..., react_refresh=True)` (the default) emits the React Fast
  Refresh preamble in dev; `dev_server="/"` for a same-origin dev server.

## Traps

- **`props.errors` must be flat**: one string per field. Run validator output
  through `flatten_errors()`; dotted keys pass through verbatim.
- **No SSR, no Inertia v3 props** (`deferredProps`, `mergeProps`,
  `encryptHistory`, `clearHistory`), **no Django or WSGI**, no server-rendered
  SEO baseline. Set `clientOnly: false` on the client.
- **Pass `react_refresh=False`** for a Vue / Svelte client, or a React setup not
  using `@vitejs/plugin-react`.
- A stale asset version is answered with a bare `409` by the middleware, before
  your handler runs; an external redirect is `409` with `X-Inertia-Location`.
  Do not add that header to version responses yourself.
