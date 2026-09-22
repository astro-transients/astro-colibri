"""
tests/test_client_events.py

Unit tests for event lookup: get_event, get_events and get_event_voevent.

The /event endpoint has three response shapes that are easy to confuse: a
bare object for one identifier that resolves, a list for anything else, and
HTTP 207 with failure entries mixed into that list. These tests pin each
shape to what the client returns.

Run:
    pytest tests/test_client_events.py -v
"""

from __future__ import annotations

import pytest
from astrocolibri.exceptions import (
    AstrocolibriAPIError,
    AstrocolibriAuthError,
    AstrocolibriConfigError,
    AstrocolibriNotFoundError,
)

from .helpers import FAKE_UID, sent

GRB = {
    "trigger_id": "922968",
    "source_name": "GRB 190829A",
    "ra": 44.5423,
    "dec": -8.9576,
    "err": 0.0016,
    "gw_contours": {"Parameter": "Not requested"},
    "archive": {"Parameter": "Not requested"},
    "field_added_next_year": {"nested": [1, 2]},
}
GBM = {
    "trigger_id": "588801358",
    "source_name": "GRB 190829A",
    "ra": 45.62,
    "dec": -7.06,
    "err": 2.21,
}
MISS = {"trigger_id": "NOPE", "error": "event not found"}
INTERNAL = {
    "trigger_id": "BROKEN",
    "message": "not found",
    "internal_error": "database timeout",
}


class TestGetEvent:
    def test_returns_the_event_with_every_field(self, client, respond):
        respond(200, GRB)
        assert client.get_event("GRB 190829A") == GRB

    def test_sends_the_identifier_as_trigger_id(self, client, session, respond):
        # The API resolves names from trigger_id too; a separate source_name
        # parameter would be discarded whenever trigger_id is present.
        respond(200, GRB)
        client.get_event("GRB 190829A")
        assert sent(session)[2]["params"] == [("trigger_id", "GRB 190829A")]

    def test_identifier_is_stripped(self, client, session, respond):
        respond(200, GRB)
        client.get_event("  GRB 190829A ")
        assert sent(session)[2]["params"] == [("trigger_id", "GRB 190829A")]

    def test_missing_event_raises_not_found(self, client, respond):
        respond(207, [MISS])
        with pytest.raises(AstrocolibriNotFoundError, match="NOPE"):
            client.get_event("NOPE")

    def test_one_element_failure_list_is_not_returned_as_the_event(
        self, client, respond
    ):
        # A single missing identifier comes back as a one-element list, not a
        # bare object. Treating "one result" as success would hand back the
        # failure entry as if it were an event.
        respond(207, [MISS])
        with pytest.raises(AstrocolibriNotFoundError):
            client.get_event("NOPE")

    def test_internal_failure_is_not_reported_as_not_found(self, client, respond):
        # The API labels server-side exceptions "not found" too; the real
        # cause is in internal_error, and it is not the user's typo.
        respond(207, [INTERNAL])
        with pytest.raises(AstrocolibriAPIError, match="database timeout") as excinfo:
            client.get_event("BROKEN")
        assert not isinstance(excinfo.value, AstrocolibriNotFoundError)

    def test_optional_parameters_are_repeated(self, client, session, respond):
        respond(200, GRB)
        client.get_event("X", optional_parameters=["gw_contours", "archive"])
        assert sent(session)[2]["params"] == [
            ("trigger_id", "X"),
            ("optional_parameters", "gw_contours"),
            ("optional_parameters", "archive"),
        ]

    def test_single_optional_parameter_string(self, client, session, respond):
        respond(200, GRB)
        client.get_event("X", optional_parameters="archive")
        assert ("optional_parameters", "archive") in sent(session)[2]["params"]

    def test_optional_parameters_none(self, client, session, respond):
        respond(200, GRB)
        client.get_event("X", optional_parameters=None)
        assert sent(session)[2]["params"] == [("trigger_id", "X")]

    def test_unknown_optional_parameter_is_rejected_before_sending(
        self, client, session
    ):
        # Sent to /event, a typo here comes back as "event not found" for a
        # perfectly valid event. Only client-side validation can say what
        # actually went wrong.
        with pytest.raises(AstrocolibriConfigError, match="'bogus'"):
            client.get_event("GRB 190829A", optional_parameters=["bogus"])
        session.request.assert_not_called()

    def test_simbad_flag(self, client, session, respond):
        respond(200, GRB)
        client.get_event("Crab", simbad=True)
        assert ("simbad", "true") in sent(session)[2]["params"]

    def test_simbad_is_not_sent_by_default(self, client, session, respond):
        # The API treats any non-empty simbad value as true, "false" included.
        respond(200, GRB)
        client.get_event("X")
        assert all(name != "simbad" for name, _ in sent(session)[2]["params"])

    def test_uid_is_not_sent_by_default(self, client, session, respond):
        # On /event the uid would travel in the query string, and it only
        # matters for custom events.
        respond(200, GRB)
        client.get_event("X")
        assert all(name != "uid" for name, _ in sent(session)[2]["params"])

    def test_uid_is_sent_for_custom_events(self, client, session, respond):
        respond(200, GRB)
        client.get_event("my-custom-event", include_custom_events=True)
        assert ("uid", FAKE_UID) in sent(session)[2]["params"]

    def test_custom_events_without_uid_sends_nothing(self, anonymous_client, session):
        with pytest.raises(AstrocolibriAuthError, match="ASTROCOLIBRI_UID"):
            anonymous_client.get_event("X", include_custom_events=True)
        session.request.assert_not_called()

    def test_lookups_work_without_uid(self, anonymous_client, respond):
        respond(200, GRB)
        assert anonymous_client.get_event("GRB 190829A") == GRB

    @pytest.mark.parametrize("value", ["false", 0, None])
    def test_flags_must_be_booleans(self, client, session, value):
        with pytest.raises(AstrocolibriConfigError, match="simbad"):
            client.get_event("X", simbad=value)
        session.request.assert_not_called()

    @pytest.mark.parametrize("value", ["", "   ", None, 42])
    def test_invalid_identifier(self, client, session, value):
        with pytest.raises(AstrocolibriConfigError, match="identifier"):
            client.get_event(value)
        session.request.assert_not_called()

    def test_unexpected_payload(self, client, respond):
        respond(200, "just a string")
        with pytest.raises(AstrocolibriAPIError, match="does not understand"):
            client.get_event("X")


class TestGetEvents:
    def test_sends_repeated_trigger_ids(self, client, session, respond):
        respond(200, [GRB, GBM])
        client.get_events(["922968", "588801358"])
        assert sent(session)[2]["params"] == [
            ("trigger_id", "922968"),
            ("trigger_id", "588801358"),
        ]

    def test_returns_events_in_request_order(self, client, respond):
        respond(200, [GRB, GBM])
        assert client.get_events(["922968", "588801358"]) == [GRB, GBM]

    def test_single_identifier_still_returns_a_list(self, client, respond):
        # With one identifier the API answers with a bare object.
        respond(200, GRB)
        assert client.get_events(["922968"]) == [GRB]

    def test_partial_miss_raises_naming_only_the_missing(self, client, respond):
        respond(207, [GRB, MISS])
        with pytest.raises(AstrocolibriNotFoundError) as excinfo:
            client.get_events(["922968", "NOPE"])
        assert "'NOPE'" in str(excinfo.value)
        assert "922968" not in str(excinfo.value)

    def test_partial_miss_skip_returns_the_found(self, client, respond):
        respond(207, [GRB, MISS, GBM])
        assert client.get_events(["922968", "NOPE", "588801358"], missing="skip") == [
            GRB,
            GBM,
        ]

    def test_internal_failure_raises_api_error(self, client, respond):
        respond(207, [GRB, INTERNAL])
        with pytest.raises(AstrocolibriAPIError, match="BROKEN") as excinfo:
            client.get_events(["922968", "BROKEN"])
        assert not isinstance(excinfo.value, AstrocolibriNotFoundError)

    def test_internal_failure_is_skipped_with_skip(self, client, respond):
        respond(207, [GRB, INTERNAL])
        assert client.get_events(["922968", "BROKEN"], missing="skip") == [GRB]

    def test_all_missing_with_skip_is_an_empty_list(self, client, respond):
        respond(207, [MISS, MISS])
        assert client.get_events(["A", "B"], missing="skip") == []

    def test_invalid_missing_policy(self, client, session):
        with pytest.raises(AstrocolibriConfigError, match="missing"):
            client.get_events(["X"], missing="ignore")
        session.request.assert_not_called()

    def test_a_single_string_is_rejected(self, client, session):
        # Iterating "GRB" would silently look up "G", "R" and "B".
        with pytest.raises(AstrocolibriConfigError, match="not a single string"):
            client.get_events("GRB 190829A")
        session.request.assert_not_called()

    def test_empty_list_is_rejected(self, client):
        with pytest.raises(AstrocolibriConfigError, match="empty"):
            client.get_events([])

    def test_non_iterable_is_rejected(self, client):
        with pytest.raises(AstrocolibriConfigError, match="list of strings"):
            client.get_events(42)

    def test_response_length_mismatch_is_malformed(self, client, respond):
        respond(200, [GRB])
        with pytest.raises(AstrocolibriAPIError, match="does not understand"):
            client.get_events(["922968", "588801358"])


class TestGetEventVoevent:
    XML = '<?xml version="1.0"?><voe:VOEvent ivorn="ivo://test"/>'

    def test_returns_xml_text(self, client, respond):
        respond(200, text=self.XML, content_type="application/xml")
        assert client.get_event_voevent("GRB 190829A") == self.XML

    def test_endpoint_and_params(self, client, session, respond):
        respond(200, text=self.XML, content_type="application/xml")
        client.get_event_voevent("GRB 190829A", optional_parameters=["archive"])
        method, url, kwargs = sent(session)
        assert (method, url) == (
            "GET",
            "https://astro-colibri.science/get_event_as_voevent",
        )
        assert kwargs["params"] == [
            ("trigger_id", "GRB 190829A"),
            ("optional_parameters", "archive"),
        ]

    def test_missing_event_raises_not_found_naming_it(self, client, respond):
        respond(404, {"message": "not found", "status_code": "404"})
        with pytest.raises(AstrocolibriNotFoundError, match="GRB 999999Z") as excinfo:
            client.get_event_voevent("GRB 999999Z")
        assert excinfo.value.status_code == 404

    def test_bad_request_raises_api_error(self, client, respond):
        respond(
            400,
            {"message": "Please provide exactly one trigger_id", "status_code": "400"},
        )
        with pytest.raises(AstrocolibriAPIError, match="exactly one"):
            client.get_event_voevent("X")

    def test_unknown_optional_parameter_is_rejected(self, client, session):
        with pytest.raises(AstrocolibriConfigError):
            client.get_event_voevent("X", optional_parameters=["bogus"])
        session.request.assert_not_called()
