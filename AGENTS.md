# AGENTS.md — fancy-inertia-server

ASGI middleware speaking the Inertia **server** protocol. `CLAUDE.md` points
here. Read the envelope's `RULES.md` too — process rules live there, not here.

## The rule that shapes this repo

**Zero runtime dependencies, and ASGI rather than a framework.** This is
middleware for Starlette and FastAPI, and it depends on neither. ASGI is a
protocol of three dicts, so none is needed; a hard `starlette` requirement would
make the package unusable from any other ASGI stack and would buy a FastAPI
consumer nothing, since FastAPI already depends on it.

Starlette is imported **softly**, once, in `response.py`, for exactly one reason:
FastAPI inspects what a handler returns and serializes anything that is not a
`starlette.responses.Response`. Returning a raw ASGI callable there would be
JSON-encoded into nonsense. That is the whole justification, and it is the only
soft import that earns its place.

`dependencies = []` in `pyproject.toml` is a constraint, not a current state.

## What this package owes

It is a protocol adapter, so it owes **the protocol as the client actually
implements it** — not as the Inertia documentation describes it. The contract is
`.ai/plans/polyglot/specs/fancy-inertia.md` §7 in the envelope, derived by
reading `@inertiajs/core`'s source. Three clauses matter more than the rest, and
each has a fixture:

1. **A stale asset version is a BARE `409`.** `409` *with* `X-Inertia-Location`
   is the external-redirect branch; `isLocationVisit()` in the client is
   literally `hasStatus(409) && hasHeader("x-inertia-location")`. Adding the
   header on a version mismatch makes every stale response read as a redirect,
   and the app-update banner never appears. The protocol docs invite exactly
   this misreading.

2. **An unknown partial key resolves to nothing — it does not raise.**
   `useAppUpdate` pings with `X-Inertia-Partial-Data: __app_update_ping__`, a
   prop no page declares. An adapter that errors there turns the update detector
   into a permanent no-op, or makes every deploy 500. This is not special-cased
   to that name: *any* unknown key yields nothing, or the next hook the client
   adds breaks the server.

3. **`props.errors` is flat.** One string per field, dotted keys verbatim. A
   list renders `[object Array]` into `<Input error={…}>` and type-checks
   nowhere.

**The version check lives in the middleware, not in `render()`**, because the
spec requires it to run before prop resolution — otherwise the ping costs a full
page render on every poll. `tests/test_conformance.py` asserts this by making
prop resolution raise and checking the `409` still comes back.

## What 0.1.0 does not do

Stated here so it is a decision rather than a discovery:

- No SSR, no Inertia v3 props (`deferredProps` / `mergeProps` /
  `encryptHistory` / `clearHistory`), no Django or WSGI, no server-rendered SEO.
  Pin `@inertiajs/react` to `^2`. Dropping v3 is what makes this package small —
  it is the one row the kit's spec prices moderate-hard.
- **But `X-Inertia-Partial-Except` IS honoured**, despite the rest of v2 being
  out of scope. Ignoring it would *invert* its meaning and return precisely the
  props the caller asked to be spared. An unimplemented feature that sends more
  data than requested is not a missing feature, it is a wrong answer. Any future
  "not implemented yet" decision here gets the same test: does ignoring this
  relax the request, or reverse it?

## Testing

```bash
pip install -e . --group dev
pytest                      # 21 tests
python tests/sabotage.py    # 8 mutations, all must be CAUGHT
ruff check . && ruff format --check . && mypy
```

- **`tests/asgi.py` is a hand-written ASGI driver**, so the suite needs no HTTP
  client. A harness pulling in `httpx` would test that library's request handling
  as much as ours, and the driver is forty lines because ASGI is three dicts.

  It also means the suite runs with NO dependencies at all, which is what lets
  the `no-dependencies` CI job execute the same fixtures against the raw ASGI
  branch. Starlette is in the `test` group so the other branch is covered too --
  that is a deliberate exception for the framework this package integrates with,
  not a drift. `httpx` would not earn the same exception.
- **`tests/sabotage.py` is not optional.** Every fixture passed on its first run
  because the suite and the implementation were written together, which is the
  easiest way to write a suite that asserts only what the code already does. Run
  it after changing anything in `src/`; a mutation that SURVIVES is a gap in the
  suite, not a win.

### Both response branches are covered, and that took a dependency

`make_response` returns a real `starlette.responses.Response` when Starlette is
importable and a raw ASGI app when it is not. Both branches are now exercised by
the SAME conformance fixtures, twice:

* **With Starlette** -- it is in the `test` dependency group, so `pytest` locally
  and the matrix job in CI run every fixture against a real Starlette response.
  This is the branch a FastAPI consumer actually reaches.
* **Without it** -- the `no-dependencies` CI job installs the package and pytest
  and nothing else, and runs the same fixtures against the raw ASGI fallback.
  That job also proves the zero-RUNTIME-dependency claim rather than asserting it.

Starlette is a TEST dependency only; `dependencies` stays empty. It is the
framework this package exists to integrate with, which the owner made a standing
approval on 2026-10-06 -- the same shape as react-fancy carrying React in
devDependencies.

**Adding it immediately found a test that was measuring the machine rather than
the code.** `test_falls_back_to_raw_asgi_when_starlette_is_absent` set
`sys.modules["starlette"] = None` but not `sys.modules["starlette.responses"]`,
and this package imports `from starlette.responses import Response` -- which
resolves straight out of the module cache. With Starlette absent from the
environment the test passed for the wrong reason; the moment it was installed,
the test went red and the hole was visible. If you ever stub a module here, stub
every submodule the import path actually touches.

## Conventions

- **Fixture numbers in test names.** `test_a3_…` so a failure names the clause of
  the contract it broke, not just a behaviour.
- **`--import-mode=importlib` with src-layout**: the tests exercise the
  INSTALLED package. Under the default mode a missing `py.typed` or an unshipped
  file passes locally and breaks for every user.
- **`filterwarnings = ["error"]`.** It has already caught an invented pytest
  marker. Do not relax it to silence a warning you have not read.
- Python floor is **3.11**, matching every other Python package in the kit.
