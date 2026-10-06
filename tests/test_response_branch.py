"""The Starlette branch of `make_response`, which the conformance suite misses.

## Why this file exists

`response.py` soft-imports Starlette so FastAPI gets a type it recognises. Which
branch runs therefore depends on what is installed — and Starlette is NOT
installed in this repository's test environment, so the whole conformance suite
exercised the raw-ASGI branch only.

That is the branch **gene will never use**: FastAPI depends on Starlette, so the
first consumer runs the half that nothing had tested. "17 passed" was true and
covered the wrong path.

Installing Starlette to test the real thing needs an owner approval for a test
dependency, which has not been given. So these tests inject a stub module with
the real `Response` signature and assert the BRANCHING CONTRACT: that Starlette
is preferred when importable, and that it is called with arguments the real
class accepts.

**This is deliberately weaker than the real thing, and the weakness is named in
AGENTS.md.** A stub proves we call Starlette correctly as documented; it cannot
prove Starlette behaves as documented. Running the conformance suite against
real Starlette and FastAPI is the open item.
"""

from __future__ import annotations

import sys
import types

import pytest

import fancy_inertia_server.response as response_module


@pytest.fixture
def stub_starlette(monkeypatch):
    """A fake `starlette.responses` recording how Response was constructed."""
    calls: list[dict] = []

    class Response:
        # The real signature, from starlette.responses.Response.
        def __init__(
            self,
            content=None,
            status_code: int = 200,
            headers=None,
            media_type=None,
            background=None,
        ) -> None:
            calls.append(
                {
                    "content": content,
                    "status_code": status_code,
                    "headers": dict(headers or {}),
                    "media_type": media_type,
                }
            )
            self.status_code = status_code
            self.body = content
            self.headers = dict(headers or {})

    starlette = types.ModuleType("starlette")
    responses = types.ModuleType("starlette.responses")
    responses.Response = Response
    starlette.responses = responses

    monkeypatch.setitem(sys.modules, "starlette", starlette)
    monkeypatch.setitem(sys.modules, "starlette.responses", responses)

    # The resolution is cached after the first call, so reset it or this test
    # inherits whatever an earlier one decided.
    monkeypatch.setattr(response_module, "_starlette_response", None)
    monkeypatch.setattr(response_module, "_checked", False)

    return calls, Response


def test_prefers_starlette_when_it_is_importable(stub_starlette):
    calls, Response = stub_starlette

    result = response_module.make_response(409, b"", {"x-inertia-location": "/sso"})

    assert isinstance(result, Response), "FastAPI only passes through a starlette Response"
    assert calls == [
        {
            "content": b"",
            "status_code": 409,
            "headers": {"x-inertia-location": "/sso"},
            "media_type": None,
        }
    ]


def test_does_not_set_content_length_on_the_starlette_branch(stub_starlette):
    """Starlette computes content-length itself; ours would duplicate the header.

    The raw-ASGI branch MUST set it (nothing else will) and the Starlette branch
    must NOT. That asymmetry is easy to lose in a refactor that "tidies" the two
    branches into one.
    """
    calls, _ = stub_starlette

    response_module.make_response(200, b'{"a":1}', {"content-type": "application/json"})

    assert "content-length" not in calls[0]["headers"]


def test_falls_back_to_raw_asgi_when_starlette_is_absent(monkeypatch):
    # BOTH entries, and the second is the one that matters.
    #
    # `sys.modules["starlette"] = None` alone makes `import starlette` raise --
    # but this package imports `from starlette.responses import Response`, which
    # resolves straight out of `sys.modules["starlette.responses"]` when anything
    # has already imported it. So with starlette actually installed the fallback
    # was never taken and this test asserted nothing.
    #
    # It passed for two weeks because starlette was ABSENT from the environment:
    # the test was measuring the machine, not the code. Adding starlette as a
    # test dependency is what exposed it.
    monkeypatch.setitem(sys.modules, "starlette", None)
    monkeypatch.setitem(sys.modules, "starlette.responses", None)
    monkeypatch.setattr(response_module, "_starlette_response", None)
    monkeypatch.setattr(response_module, "_checked", False)

    result = response_module.make_response(200, b"hi", {})

    assert isinstance(result, response_module.ASGIResponse)
    # The raw branch owns content-length, because no framework will add it.
    assert result.headers["content-length"] == "2"


def test_raw_asgi_response_emits_a_valid_message_pair():
    """A hand-rolled ASGI response is easy to get subtly wrong."""
    import asyncio

    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    asyncio.run(response_module.ASGIResponse(204, b"", {"x-test": "1"})({}, None, send))

    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 204
    assert (b"x-test", b"1") in sent[0]["headers"]
    assert sent[1] == {"type": "http.response.body", "body": b""}
