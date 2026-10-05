"""Fixtures A1-A7 from the kit's language-agnostic Inertia server contract.

The contract is `.ai/plans/polyglot/specs/fancy-inertia.md` section 7, and it was
derived by reading the `@inertiajs/core` client source rather than the Inertia
docs. These are transcribed from it one test per fixture, with the fixture number
in the name so a failure names the clause it broke.

Two of them exist because the spec says they are the things that silently break:

* **A5** -- `useAppUpdate` pings with `X-Inertia-Partial-Data:
  __app_update_ping__`, a prop no page declares. An adapter that 500s on an
  unknown partial key turns the update detector into a permanent no-op, or into
  noise. The spec calls this "the single most likely thing to break on a
  hand-rolled adapter".
* **A3 vs A7** -- a stale asset version is a BARE 409. `409 +
  X-Inertia-Location` is the external-redirect branch, and `isLocationVisit()`
  in the client is literally `hasStatus(409) && hasHeader("x-inertia-location")`.
  Conflating them is the reading the protocol docs invite, and it is wrong: the
  app-update banner would never appear, because every stale-version response
  would be taken as a redirect instead.

A8 (`X-Inertia-Partial-Except` / `X-Inertia-Reset`) is deliberately out of scope
for 0.1.0 -- see `test_partial_except.py`, which asserts the part of A8 that
cannot be left unimplemented without INVERTING its meaning.
"""

from __future__ import annotations

import json

import pytest

from fancy_inertia_server import Inertia, InertiaConfig

from .asgi import Client

COMPONENT = "Packages/Show"
URL = "/packages/react-fancy"
VERSION = "v1-abc"


def make_app(props: dict | None = None, *, version: str = VERSION):
    """A minimal ASGI app that renders one Inertia page."""
    config = InertiaConfig(version=version, root_template=_root_template)
    page_props = props if props is not None else {"name": "react-fancy", "stars": 10}

    async def app(scope, receive, send):
        inertia = Inertia.from_scope(scope)
        response = inertia.render(COMPONENT, dict(page_props))
        await response(scope, receive, send)

    from fancy_inertia_server import InertiaMiddleware

    return Client(InertiaMiddleware(app, config))


def _root_template(page_json: str) -> str:
    # The mount element and its data-page attribute are the whole of A1.
    return (
        "<!DOCTYPE html><html><head></head><body>"
        f"<div id=\"app\" data-page='{page_json}'></div>"
        "</body></html>"
    )


# ---------------------------------------------------------------------------
# A1 -- first byte, no X-Inertia
# ---------------------------------------------------------------------------


def test_a1_html_document_carries_the_page_object_in_data_page():
    response = make_app().get(URL)

    assert response.status == 200
    assert "text/html" in response.header("content-type")

    page = response.data_page()
    assert page["component"] == COMPONENT
    assert page["url"] == URL
    assert page["version"] == VERSION
    assert page["props"]["name"] == "react-fancy"


# ---------------------------------------------------------------------------
# A2 -- X-Inertia with the current version
# ---------------------------------------------------------------------------


def test_a2_inertia_request_with_current_version_returns_the_page_as_json():
    response = make_app().get(URL, headers={"X-Inertia": "true", "X-Inertia-Version": VERSION})

    assert response.status == 200
    assert response.header("x-inertia") == "true"
    assert "application/json" in response.header("content-type")

    page = json.loads(response.body)
    assert page == {
        "component": COMPONENT,
        "props": {"name": "react-fancy", "stars": 10},
        "url": URL,
        "version": VERSION,
    }


# ---------------------------------------------------------------------------
# A3 -- stale version is a BARE 409
# ---------------------------------------------------------------------------


def test_a3_stale_version_returns_409_without_an_inertia_location_header():
    response = make_app().get(URL, headers={"X-Inertia": "true", "X-Inertia-Version": "stale"})

    assert response.status == 409
    # The whole point. With this header the client takes it as an external
    # redirect and the app-update banner never fires.
    assert response.header("x-inertia-location") is None


# ---------------------------------------------------------------------------
# A4 -- the ping against a stale version
# ---------------------------------------------------------------------------


def test_a4_app_update_ping_against_a_stale_version_is_409_and_never_5xx():
    response = make_app().get(
        URL,
        headers={
            "X-Inertia": "true",
            "X-Inertia-Version": "stale",
            "X-Inertia-Partial-Component": COMPONENT,
            "X-Inertia-Partial-Data": "__app_update_ping__",
        },
    )

    assert response.status == 409
    assert response.status < 500


def test_a4_the_version_check_runs_before_any_prop_is_resolved():
    """Spec 3.4 requirement 3: the ping must not cost a full page render.

    Asserted by making prop resolution EXPLODE. If the 409 still comes back, the
    version check demonstrably ran first; if the adapter resolved props before
    comparing versions, this raises instead.
    """

    def detonate():
        raise AssertionError("props were resolved before the version was checked")

    config = InertiaConfig(version=VERSION, root_template=_root_template)

    async def app(scope, receive, send):  # pragma: no cover - must never run
        detonate()

    from fancy_inertia_server import InertiaMiddleware

    client = Client(InertiaMiddleware(app, config))
    response = client.get(
        URL,
        headers={
            "X-Inertia": "true",
            "X-Inertia-Version": "stale",
            "X-Inertia-Partial-Data": "__app_update_ping__",
        },
    )

    assert response.status == 409


# ---------------------------------------------------------------------------
# A5 -- the ping against the CURRENT version
# ---------------------------------------------------------------------------


def test_a5_app_update_ping_with_current_version_is_200_and_omits_every_prop():
    response = make_app().get(
        URL,
        headers={
            "X-Inertia": "true",
            "X-Inertia-Version": VERSION,
            "X-Inertia-Partial-Component": COMPONENT,
            "X-Inertia-Partial-Data": "__app_update_ping__",
        },
    )

    assert response.status == 200

    page = json.loads(response.body)
    # "a props object that omits everything (the point of the ping is that it is
    # tiny)" -- asserted as empty rather than small, because a partial request
    # for a prop that does not exist has nothing legitimate to return.
    assert page["props"] == {}
    assert page["component"] == COMPONENT


def test_a5_an_unknown_partial_prop_does_not_raise_for_any_name():
    # The ping name is not special-cased: ANY unknown partial key must be
    # tolerated, or the next hook the client adds breaks the server.
    response = make_app().get(
        URL,
        headers={
            "X-Inertia": "true",
            "X-Inertia-Version": VERSION,
            "X-Inertia-Partial-Component": COMPONENT,
            "X-Inertia-Partial-Data": "no_such_prop_at_all",
        },
    )

    assert response.status == 200
    assert json.loads(response.body)["props"] == {}


def test_a5_a_known_partial_prop_returns_only_that_prop():
    response = make_app().get(
        URL,
        headers={
            "X-Inertia": "true",
            "X-Inertia-Version": VERSION,
            "X-Inertia-Partial-Component": COMPONENT,
            "X-Inertia-Partial-Data": "stars",
        },
    )

    assert json.loads(response.body)["props"] == {"stars": 10}


def test_a5_a_partial_request_for_a_different_component_returns_everything():
    # Inertia scopes a partial reload to the component it was requested from.
    # A mismatch means the user navigated, so the full props are correct.
    response = make_app().get(
        URL,
        headers={
            "X-Inertia": "true",
            "X-Inertia-Version": VERSION,
            "X-Inertia-Partial-Component": "Some/Other",
            "X-Inertia-Partial-Data": "stars",
        },
    )

    assert json.loads(response.body)["props"] == {"name": "react-fancy", "stars": 10}


# ---------------------------------------------------------------------------
# A6 -- validation errors are a FLAT map
# ---------------------------------------------------------------------------


def test_a6_errors_are_a_flat_record_of_field_to_one_string():
    from fancy_inertia_server import InertiaMiddleware

    config = InertiaConfig(version=VERSION, root_template=_root_template)

    async def app(scope, receive, send):
        inertia = Inertia.from_scope(scope)
        response = inertia.back(
            errors={
                "email": "The email field is required.",
                "address.city": "The city is invalid.",
            }
        )
        await response(scope, receive, send)

    client = Client(InertiaMiddleware(app, config))
    response = client.get(
        URL,
        headers={"X-Inertia": "true", "X-Inertia-Version": VERSION, "Referer": "/form"},
    )

    errors = json.loads(response.body)["props"]["errors"]

    assert errors == {
        "email": "The email field is required.",
        "address.city": "The city is invalid.",
    }
    # One string per field, never a list: `<Input error={…}>` renders
    # "[object Array]" otherwise, and it type-checks nowhere.
    for value in errors.values():
        assert isinstance(value, str)


def test_a6_a_list_of_messages_is_flattened_to_the_first():
    # Framework validators emit Record<field, list[str]>. Flattening is the
    # adapter's job; leaving it to the caller is how the list reaches React.
    from fancy_inertia_server import flatten_errors

    assert flatten_errors({"email": ["Required.", "Also invalid."]}) == {"email": "Required."}
    assert flatten_errors({"email": "Required."}) == {"email": "Required."}
    assert flatten_errors({"address.city": ["Bad."]}) == {"address.city": "Bad."}


# ---------------------------------------------------------------------------
# A7 -- external redirect is 409 WITH the location header
# ---------------------------------------------------------------------------


def test_a7_external_redirect_is_409_with_x_inertia_location():
    from fancy_inertia_server import InertiaMiddleware

    config = InertiaConfig(version=VERSION, root_template=_root_template)
    target = "https://example.test/sso"

    async def app(scope, receive, send):
        inertia = Inertia.from_scope(scope)
        response = inertia.location(target)
        await response(scope, receive, send)

    client = Client(InertiaMiddleware(app, config))
    response = client.get(URL, headers={"X-Inertia": "true", "X-Inertia-Version": VERSION})

    assert response.status == 409
    assert response.header("x-inertia-location") == target


def test_a7_a_location_visit_is_distinguishable_from_a_stale_version():
    """The two 409s must not be confusable -- that is the entire point of A3+A7.

    `isLocationVisit()` in @inertiajs/core is
    `hasStatus(409) && hasHeader("x-inertia-location")`, so the ONLY thing
    telling them apart is the header's presence.
    """
    stale = make_app().get(URL, headers={"X-Inertia": "true", "X-Inertia-Version": "stale"})

    assert stale.status == 409
    assert stale.header("x-inertia-location") is None


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_a3_the_version_check_applies_to_GET_only(method):
    """Inertia's asset-version 409 is a GET concern.

    A 409 on a POST would make a stale tab unable to submit anything, which is
    the opposite of the intended behaviour: the client cannot retry a mutation
    it has already sent.
    """
    response = make_app().request(
        method, URL, headers={"X-Inertia": "true", "X-Inertia-Version": "stale"}
    )

    assert response.status != 409
