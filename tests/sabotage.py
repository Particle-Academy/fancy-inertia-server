"""Mutation sweep: prove each conformance fixture can actually fail.

Not a test — a tool, run by hand and recorded in the changelog. Run it with
`python tests/sabotage.py` from the repository root.

## Why

All 17 fixtures passed on their first run, because the suite and the
implementation were written together. A check never observed to fail is
indistinguishable from one that cannot fail, and writing both halves at once is
the single easiest way to produce a suite that asserts only what the code
already happens to do.

So each mutation below breaks ONE clause of the contract, in the way a plausible
implementation would break it, and the sweep asserts the suite notices. A
mutation that leaves the suite green is a gap in the suite, not a victory.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "fancy_inertia_server"

#: (file, find, replace, why this is a plausible mistake)
MUTATIONS = [
    (
        "middleware.py",
        'response = make_response(409, b"", {"vary": "X-Inertia"})',
        'response = make_response(409, b"", {"vary": "X-Inertia", "x-inertia-location": "/"})',
        "stale version sends X-Inertia-Location -- the documented-protocol "
        "misreading, which makes every stale response look like a redirect",
    ),
    (
        "inertia.py",
        "merged = {key: value for key, value in merged.items() if key in keys}",
        "merged = {key: merged[key] for key in keys}",
        "unknown partial key raises KeyError -- what a naive partial "
        "implementation does, and it 500s the app-update ping",
    ),
    (
        "middleware.py",
        "if self._is_stale(inertia, scope):",
        "if False and self._is_stale(inertia, scope):",
        "version check never runs, so a stale client is never told to reload",
    ),
    (
        "inertia.py",
        "            if value:\n                flat[field_name] = str(value[0])",
        "            flat[field_name] = value  # type: ignore[assignment]",
        "errors left as a list -- renders [object Array] into <Input error>",
    ),
    (
        "inertia.py",
        'return make_response(409, b"", {"x-inertia-location": url})',
        'return make_response(409, b"", {})',
        "external redirect loses its Location header, so the client cannot "
        "tell it from a stale asset version",
    ),
    (
        "inertia.py",
        "        if not requested:\n            return None",
        "        if not requested:\n            return set()",
        "non-partial request treated as asking for nothing -- every page renders with empty props",
    ),
    (
        "inertia.py",
        "if partial_component and partial_component != component:\n            return None",
        "if False:\n            return None",
        "partial reload not scoped to its component, so navigating returns a partial page",
    ),
    (
        "middleware.py",
        'if scope.get("method", "GET").upper() not in VERSION_CHECKED_METHODS:',
        "if False:",
        "version-gates POST too, so a stale tab cannot submit anything",
    ),
]


def run_suite() -> bool:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def main() -> int:
    if not run_suite():
        print("BASELINE IS RED -- fix the suite before sabotaging it.")
        return 1

    print(f"baseline green. applying {len(MUTATIONS)} mutations.\n")

    survived = []

    for filename, find, replace, why in MUTATIONS:
        path = SRC / filename
        original = path.read_text(encoding="utf-8")

        if find not in original:
            print(f"  SKIP  {filename}: anchor not found -- mutation is stale")
            survived.append(f"{why} (anchor missing)")
            continue

        path.write_text(original.replace(find, replace, 1), encoding="utf-8", newline="\n")
        try:
            caught = not run_suite()
        finally:
            path.write_text(original, encoding="utf-8", newline="\n")

        print(f"  {'CAUGHT' if caught else 'SURVIVED'}  {why}")
        if not caught:
            survived.append(why)

    print()
    if survived:
        print(f"{len(survived)} mutation(s) SURVIVED -- the suite does not cover these:")
        for why in survived:
            print(f"  - {why}")
        return 1

    print(f"all {len(MUTATIONS)} mutations caught.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
