"""
tests/test_client_sources.py

Unit tests for source-name resolution: resolve_source and get_source_summary.

Both call /source_details, which never answers 404. An unknown name comes
back as HTTP 200 with -1000 sentinel coordinates, and the multi-event mode
returns an empty list for anything that is not a transient event.

Run:
    pytest tests/test_client_sources.py -v
"""

from __future__ import annotations

import pytest
from astrocolibri.exceptions import AstrocolibriAPIError, AstrocolibriConfigError

from .helpers import sent

# Live /source_details responses for GRB190829A.
ALL_EVENTS = {
    "name": "GRB190829A",
    "events": [
        {
            "trigger_id": "922968",
            "ra": 44.5423,
            "dec": -8.9576,
            "err": 0.0016,
            "timestamp": 1567108604600.0,
            "observatory": "swift",
            "instrument": "xrt",
        },
        {
            "trigger_id": "588801358",
            "ra": 45.62,
            "dec": -7.06,
            "err": 2.21,
            "timestamp": 1567108553130.0,
            "observatory": "fermi",
            "instrument": "gbm",
        },
    ],
}
SUMMARY = {
    "dec": -8.9576,
    "err": 0.0016,
    "name": "GRB190829A",
    "origin": "Astro-COLIBRI",
    "ra": 44.5423,
    "timestamp": 1567108604600.0,
    "trigger_id": "922968",
}
UNKNOWN = {
    "name": "QQQ_NOT_A_REAL_SOURCE",
    "ra": -1000,
    "dec": -1000,
    "err": -1000,
    "trigger_id": "",
    "timestamp": -1,
}


class TestResolveSource:
    def test_endpoint(self, client, session, respond):
        respond(200, ALL_EVENTS)
        client.resolve_source("GRB190829A")
        method, url, _ = sent(session)
        assert (method, url) == ("GET", "https://astro-colibri.science/source_details")

    def test_requests_every_event(self, client, session, respond):
        # Only the literal string "true" switches the API to multi-event mode.
        respond(200, ALL_EVENTS)
        client.resolve_source("GRB190829A")
        assert sent(session)[2]["params"] == {
            "name": "GRB190829A",
            "all_events": "true",
        }

    def test_name_is_stripped(self, client, session, respond):
        respond(200, ALL_EVENTS)
        client.resolve_source("  GRB190829A ")
        assert sent(session)[2]["params"]["name"] == "GRB190829A"

    def test_returns_events_in_server_order(self, client, respond):
        # The API sorts best-localized first; reordering would lose that.
        respond(200, ALL_EVENTS)
        result = client.resolve_source("GRB190829A")
        assert result == ALL_EVENTS["events"]
        assert [summary["trigger_id"] for summary in result] == ["922968", "588801358"]

    def test_timestamps_stay_in_milliseconds(self, client, respond):
        respond(200, ALL_EVENTS)
        assert client.resolve_source("GRB190829A")[0]["timestamp"] == 1567108604600.0

    def test_no_transient_events_is_an_empty_list(self, client, respond):
        # This mode skips catalog sources, so an empty list is a valid answer.
        respond(200, {"name": "Crab", "events": []})
        assert client.resolve_source("Crab") == []

    def test_works_without_uid(self, anonymous_client, respond):
        respond(200, ALL_EVENTS)
        assert len(anonymous_client.resolve_source("GRB190829A")) == 2

    @pytest.mark.parametrize(
        "payload",
        [{"name": "X"}, {"name": "X", "events": "none"}, ["not", "a", "dict"]],
    )
    def test_malformed_payload(self, client, respond, payload):
        respond(200, payload)
        with pytest.raises(AstrocolibriAPIError, match="does not understand"):
            client.resolve_source("X")

    @pytest.mark.parametrize("value", ["", "   ", None, 42])
    def test_invalid_name_sends_nothing(self, client, session, value):
        with pytest.raises(AstrocolibriConfigError, match="name"):
            client.resolve_source(value)
        session.request.assert_not_called()


class TestGetSourceSummary:
    def test_returns_the_summary(self, client, respond):
        respond(200, SUMMARY)
        assert client.get_source_summary("GRB190829A") == SUMMARY

    def test_does_not_request_every_event(self, client, session, respond):
        respond(200, SUMMARY)
        client.get_source_summary("GRB190829A")
        assert sent(session)[2]["params"] == {"name": "GRB190829A"}

    def test_unknown_source_is_none(self, client, respond):
        # HTTP 200 with sentinel coordinates: returning it would hand the
        # caller a position at RA -1000°.
        respond(200, UNKNOWN)
        assert client.get_source_summary("QQQ_NOT_A_REAL_SOURCE") is None

    def test_float_sentinels_are_recognized(self, client, respond):
        respond(200, dict(UNKNOWN, ra=-1000.0, dec=-1000.0))
        assert client.get_source_summary("QQQ_NOT_A_REAL_SOURCE") is None

    def test_simbad_origin_is_preserved(self, client, respond):
        respond(200, dict(SUMMARY, name="Vega", origin="SIMBAD", trigger_id=""))
        assert client.get_source_summary("Vega")["origin"] == "SIMBAD"

    def test_works_without_uid(self, anonymous_client, respond):
        respond(200, SUMMARY)
        assert anonymous_client.get_source_summary("GRB190829A") == SUMMARY

    def test_malformed_payload(self, client, respond):
        respond(200, ["unexpected"])
        with pytest.raises(AstrocolibriAPIError, match="does not understand"):
            client.get_source_summary("X")

    def test_invalid_name_sends_nothing(self, client, session):
        with pytest.raises(AstrocolibriConfigError, match="name"):
            client.get_source_summary("")
        session.request.assert_not_called()
