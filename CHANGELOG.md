# Changelog

All notable changes to `fancy-inertia-server` are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Pre-1.0: breaking changes land in MINOR releases.** `0.x` is not a promise
> the version number can keep, so read this file before upgrading a minor.

## [Unreleased]

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
- **No SSR**, no Inertia v3 props (`deferredProps`, `mergeProps`,
  `encryptHistory`, `clearHistory`), no Django/WSGI, no server-rendered SEO
  baseline. Pin `@inertiajs/react` to `^2`.
- Not on PyPI. Install from git until a pending publisher is configured.
