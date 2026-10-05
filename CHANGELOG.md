# Changelog

All notable changes to `fancy-inertia-server` are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Pre-1.0: breaking changes land in MINOR releases.** `0.x` is not a promise
> the version number can keep, so read this file before upgrading a minor.

## [Unreleased]

## [0.2.0] - 2026-10-05

Both items reported by the YouGene estate within a day of integrating 0.1.0 —
the first consumer finding, in an afternoon, two things the conformance fixtures
had no opinion about because they are about HTML rather than the Inertia
protocol.

### Added

- **React Fast Refresh preamble in dev mode**, on by default via
  `asset_tags(react_refresh=True)`. `@vitejs/plugin-react` installs a global it
  then requires, and without it throws *"@vitejs/plugin-react can't detect
  preamble"* from inside a component — an error that names React rather than the
  missing script tag. Transcribed from Laravel's
  `Illuminate\Foundation\Vite::reactRefresh()` so it matches the reference
  implementation rather than a recollection of it, and emitted **before** the
  entry module, because a global installed after the components that look for it
  is the same as no global.

  Default is on because the two failures are not symmetrical: omitting it breaks
  every component for a React consumer, while emitting it for a non-React one
  costs a single 404 on `/@react-refresh` in development. Pass
  `react_refresh=False` for a Vue/Svelte client or a React setup not using
  `@vitejs/plugin-react`.

- **Same-origin dev server**: `asset_tags(dev_server="/")`, for setups where
  Vite proxies pages to the backend.

### Fixed

- **Dev-server URLs no longer double the slash.** `dev_server="/"` produced
  `//@vite/client`, which a browser reads as a PROTOCOL-RELATIVE url
  (`http://@vite/client`) and so leaves the origin entirely — failing as a DNS
  error rather than a 404, a long way from where the mistake was made. A
  trailing slash on an absolute `dev_server` and a leading slash on `entry` are
  both tolerated now too; Vite config and Python config disagree about those
  constantly.


## [0.1.0] - 2026-10-05

First release. ASGI middleware speaking the Inertia **server** protocol, so a
Starlette or FastAPI backend can run `@particle-academy/fancy-inertia` — the
client half — unchanged.

### Added

- `InertiaMiddleware` + `InertiaConfig`, and `inertia(request)` for the
  per-request helper. Works from a Starlette/FastAPI `Request` or a bare ASGI
  scope.
- `render()` — the page object as first-byte HTML (`data-page`) or as
  `X-Inertia` JSON, chosen by the request.
- **Partial reloads**, scoped to the requesting component, including
  `X-Inertia-Partial-Except`.
- **Asset versioning + a bare `409`**, which is what `useAppUpdate` needs. The
  check runs in the middleware, *before* the route handler, so a stale-version
  ping costs nothing.
- `location()` — external redirect as `409` **with** `X-Inertia-Location`.
- `back()` + `flatten_errors()` — `props.errors` as a flat
  `Record<str, str>`, dotted keys intact.
- Shared props, app-wide via `InertiaConfig(share=…)` and per-request via
  `inertia(request).share(…)`. Page props win over both.
- `vite.manifest_version()`, `vite.asset_tags()`, `vite.root_template()` —
  asset version from the manifest, script tags from the dev server or the
  manifest.
- **Zero runtime dependencies.** Starlette is a soft import used only to hand
  FastAPI a type it recognises.

### Conformance

`tests/test_conformance.py` is fixtures **A1–A7** of the kit's language-agnostic
Inertia server contract (`.ai/plans/polyglot/specs/fancy-inertia.md` §7),
transcribed one test per fixture. That contract was derived by reading the
`@inertiajs/core` client source rather than the Inertia docs.

All 17 fixtures passed on their first run, because the suite and the
implementation were written together — which is the easiest way to produce a
suite that asserts only what the code already happens to do. So
`tests/sabotage.py` breaks one clause of the contract at a time, in the way a
plausible implementation would break it, and checks the suite notices.
**8 of 8 mutations caught**, including the two the spec names as the likely
silent failures: a stale version answered with `X-Inertia-Location`, and an
unknown partial key raising instead of resolving to nothing.

### Known gaps, stated rather than discovered

- **The Starlette branch of `make_response` is covered by a stub, not by
  Starlette.** It is not installed here, so the conformance suite exercised the
  raw-ASGI branch only — the branch a FastAPI consumer will *never* use. The
  stub asserts the branching contract and the call shape; it cannot prove
  Starlette behaves as documented. Running the suite against real
  Starlette/FastAPI needs a test-dependency approval and is the first thing to
  do when one is given.

  **Verified once by hand against real Starlette 1.7.0**: A1/A2/A3/A5 driven
  through a genuine Starlette app, confirming the response is a real
  `starlette.responses.Response` and that `content-length` is not duplicated.
  The branch is known to work; what is missing is automated cover that would
  catch it breaking later.
- **No SSR**, no Inertia v3 props (`deferredProps`, `mergeProps`,
  `encryptHistory`, `clearHistory`), no Django/WSGI, no server-rendered SEO
  baseline. Pin `@inertiajs/react` to `^2`.
- Not on PyPI. Install from git until a pending publisher is configured.
