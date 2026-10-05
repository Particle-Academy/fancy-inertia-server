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
  client. A harness pulling in `httpx` or `starlette` would quietly make the
  zero-dependency claim untrue for anyone running the suite, and would test
  those libraries as much as ours.
- **`tests/sabotage.py` is not optional.** Every fixture passed on its first run
  because the suite and the implementation were written together, which is the
  easiest way to write a suite that asserts only what the code already does. Run
  it after changing anything in `src/`; a mutation that SURVIVES is a gap in the
  suite, not a win.

### The gap you should know about

**The Starlette branch of `make_response` is tested with a stub, not with
Starlette.** It is not installed here, so the conformance suite exercises the
raw-ASGI branch only — which is the branch a FastAPI consumer will never reach.
`tests/test_response_branch.py` asserts the branching contract and the call
shape; it cannot prove Starlette behaves as documented.

Installing Starlette as a test dependency needs owner approval under the
envelope's third-party rule. When one is given, run the whole conformance suite
a second time with it present.

**Verified once by hand against real Starlette 1.7.0** (2026-10-05): fixtures
A1, A2, A3 and A5 driven through a genuine `Starlette` app in a throwaway venv,
including that the response really is a `starlette.responses.Response` and that
`content-length` is not duplicated. So the branch is known to work; what is
missing is *automated* coverage that would catch it breaking later.

Until then this is a named gap in REGRESSION cover, not an unknown.

## Conventions

- **Fixture numbers in test names.** `test_a3_…` so a failure names the clause of
  the contract it broke, not just a behaviour.
- **`--import-mode=importlib` with src-layout**: the tests exercise the
  INSTALLED package. Under the default mode a missing `py.typed` or an unshipped
  file passes locally and breaks for every user.
- **`filterwarnings = ["error"]`.** It has already caught an invented pytest
  marker. Do not relax it to silence a warning you have not read.
- Python floor is **3.11**, matching every other Python package in the kit.
