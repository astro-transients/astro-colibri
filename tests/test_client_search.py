"""
tests/test_client_search.py

Unit tests for latest_transients and cone_search.

Both searches spend the account's daily quota, so anything the client can
check locally must fail before a request goes out. Those tests end with
`session.request.assert_not_called()`.

Run:
    pytest tests/test_client_search.py -v
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest
from astrocolibri.exceptions import (
    AstrocolibriAPIError,
    AstrocolibriAuthError,
    AstrocolibriConfigError,
)

from .helpers import FAKE_UID, sent

START = "2026-09-01T00:00:00Z"
END = "2026-09-02T00:00:00Z"
UTC_RANGE = {"min": "2026-09-01T00:00:00+00:00", "max": "2026-09-02T00:00:00+00:00"}
MATCH_ALL = {"type": "TrueSpecification", "isActivated": True, "defaultState": False}
RESULTS = {
    "voevents": [
        {
            "trigger_id": "T1",
            "source_name": "AT 2026abc",
            "type": "OT",
            "time": "2026-09-01T03:04:05",
        }
    ],
    "sources": [],
    "Xsources": [],
    "icecat": [],
    "group_added_next_year": [{"x": 1}],
}
# Opaque to the client: it is forwarded, never interpreted.
SOME_FILTER = {
    "type": "FieldSpecification",
    "field": "type",
    "operator": "==",
    "value": "GRB",
}
XML = '<?xml version="1.0"?><VOTABLE version="1.4"/>'


def body(session):
    return sent(session)[2]["json"]


def crab(**overrides):
    arguments = dict(ra=83.633, dec=22.0145, radius=2, start=START, end=END)
    arguments.update(overrides)
    return arguments


class TestLatestTransientsRequest:
    def test_endpoint(self, client, session, respond):
        respond(200, RESULTS)
        client.latest_transients(start=START, end=END)
        method, url, _ = sent(session)
        assert (method, url) == (
            "POST",
            "https://astro-colibri.science/latest_transients",
        )

    def test_time_range_is_utc_with_an_explicit_offset(self, client, session, respond):
        # Without an offset the API would read the times in its own timezone.
        respond(200, RESULTS)
        client.latest_transients(start=START, end=END)
        assert body(session)["time_range"] == UTC_RANGE

    def test_other_timezones_are_converted(self, client, session, respond):
        cest = timezone(timedelta(hours=2))
        respond(200, RESULTS)
        client.latest_transients(
            start=datetime(2026, 9, 1, 2, tzinfo=cest),
            end=datetime(2026, 9, 2, 2, tzinfo=cest),
        )
        assert body(session)["time_range"] == UTC_RANGE

    def test_uid_is_in_the_body(self, client, session, respond):
        respond(200, RESULTS)
        client.latest_transients(start=START, end=END)
        assert body(session)["uid"] == FAKE_UID

    def test_defaults(self, client, session, respond):
        respond(200, RESULTS)
        client.latest_transients(start=START, end=END)
        sent_body = body(session)
        assert sent_body["return_format"] == "json"
        assert sent_body["optional_parameters"] == []
        assert sent_body["include_watchlist"] is False
        assert "properties" not in sent_body

    def test_default_filter_matches_everything(self, client, session, respond):
        # Sent explicitly rather than left out: without a filter the API
        # switches to the filters saved in the app and bypasses its cache.
        respond(200, RESULTS)
        client.latest_transients(start=START, end=END)
        assert body(session)["filter"] == MATCH_ALL

    def test_default_filter_is_a_fresh_copy(self, client, session, respond):
        respond(200, RESULTS)
        client.latest_transients(start=START, end=END)
        body(session)["filter"]["type"] = "Tampered"
        client.latest_transients(start=START, end=END)
        assert body(session)["filter"] == MATCH_ALL

    def test_explicit_filter_is_sent_as_given(self, client, session, respond):
        respond(200, RESULTS)
        client.latest_transients(start=START, end=END, event_filter=SOME_FILTER)
        assert body(session)["filter"] == SOME_FILTER

    def test_saved_filters_leave_the_filter_out(self, client, session, respond):
        respond(200, RESULTS)
        client.latest_transients(start=START, end=END, use_saved_filters=True)
        assert "filter" not in body(session)

    def test_saved_and_explicit_filters_conflict(self, client, session):
        with pytest.raises(AstrocolibriConfigError, match="not both"):
            client.latest_transients(
                start=START, end=END, event_filter=SOME_FILTER, use_saved_filters=True
            )
        session.request.assert_not_called()

    def test_empty_filter_sends_nothing(self, client, session):
        # The API reads {} as "no filter" and would quietly apply the saved
        # filters, spending quota on a different search than intended.
        with pytest.raises(AstrocolibriConfigError, match="empty"):
            client.latest_transients(start=START, end=END, event_filter={})
        session.request.assert_not_called()

    @pytest.mark.parametrize("value", ["type == GRB", ["GRB"], 42])
    def test_non_dict_filter_sends_nothing(self, client, session, value):
        with pytest.raises(AstrocolibriConfigError, match="event_filter"):
            client.latest_transients(start=START, end=END, event_filter=value)
        session.request.assert_not_called()

    def test_include_watchlist(self, client, session, respond):
        respond(200, RESULTS)
        client.latest_transients(start=START, end=END, include_watchlist=True)
        assert body(session)["include_watchlist"] is True

    def test_custom_events_are_never_sent(self, client, session, respond):
        # A frontend-only parameter the SDK must not expose or send.
        respond(200, RESULTS)
        client.latest_transients(start=START, end=END, include_watchlist=True)
        assert "custom_events" not in body(session)

    def test_optional_parameters_are_sent_as_a_list(self, client, session, respond):
        respond(200, RESULTS)
        client.latest_transients(
            start=START, end=END, optional_parameters=("gw_contours",)
        )
        assert body(session)["optional_parameters"] == ["gw_contours"]

    def test_unknown_optional_parameter_sends_nothing(self, client, session):
        with pytest.raises(AstrocolibriConfigError, match="optional_parameters"):
            client.latest_transients(
                start=START, end=END, optional_parameters=["contours"]
            )
        session.request.assert_not_called()

    @pytest.mark.parametrize("flag", ["include_watchlist", "use_saved_filters"])
    def test_flags_must_be_booleans(self, client, session, flag):
        with pytest.raises(AstrocolibriConfigError, match=flag):
            client.latest_transients(start=START, end=END, **{flag: "yes"})
        session.request.assert_not_called()

    def test_no_uid_sends_nothing(self, anonymous_client, session):
        with pytest.raises(AstrocolibriAuthError, match="astro-colibri.com/account"):
            anonymous_client.latest_transients(start=START, end=END)
        session.request.assert_not_called()

    def test_uid_is_checked_before_other_arguments(self, anonymous_client, session):
        # A first-time user should hear about the missing user ID first.
        with pytest.raises(AstrocolibriAuthError):
            anonymous_client.latest_transients(start="not-a-date", end=END)

    def test_naive_datetime_sends_nothing(self, client, session):
        with pytest.raises(AstrocolibriConfigError, match="no timezone"):
            client.latest_transients(start=datetime(2026, 9, 1), end=END)
        session.request.assert_not_called()

    def test_reversed_window_sends_nothing(self, client, session):
        with pytest.raises(AstrocolibriConfigError, match="before end"):
            client.latest_transients(start=END, end=START)
        session.request.assert_not_called()


class TestLatestTransientsResponse:
    def test_json_returns_every_group(self, client, respond):
        respond(200, RESULTS)
        assert client.latest_transients(start=START, end=END) == RESULTS

    def test_votable_returns_xml_text(self, client, session, respond):
        respond(200, text=XML, content_type="application/xml")
        assert (
            client.latest_transients(start=START, end=END, return_format="votable")
            == XML
        )
        assert sent(session)[2]["headers"]["Accept"] == "application/xml"
        assert body(session)["return_format"] == "votable"

    def test_votable_failure_is_raised(self, client, respond):
        respond(400, {"message": "Invalid filter format : bad field"})
        with pytest.raises(AstrocolibriAPIError, match="Invalid filter format"):
            client.latest_transients(start=START, end=END, return_format="votable")

    def test_url_returns_the_bare_url(self, client, respond):
        url = "https://storage.googleapis.com/bucket/abc.json"
        respond(200, {"url": url})
        assert (
            client.latest_transients(start=START, end=END, return_format="url") == url
        )

    def test_url_response_without_a_url(self, client, respond):
        respond(200, RESULTS)
        with pytest.raises(AstrocolibriAPIError, match="does not understand"):
            client.latest_transients(start=START, end=END, return_format="url")

    def test_unknown_return_format_sends_nothing(self, client, session):
        with pytest.raises(AstrocolibriConfigError, match="return_format"):
            client.latest_transients(start=START, end=END, return_format="xml")
        session.request.assert_not_called()

    def test_non_dict_json(self, client, respond):
        respond(200, ["unexpected"])
        with pytest.raises(AstrocolibriAPIError, match="does not understand"):
            client.latest_transients(start=START, end=END)


class TestConeSearchRequest:
    def test_endpoint(self, client, session, respond):
        respond(200, RESULTS)
        client.cone_search(**crab())
        method, url, _ = sent(session)
        assert (method, url) == ("POST", "https://astro-colibri.science/cone_search")

    def test_decimal_degrees(self, client, session, respond):
        respond(200, RESULTS)
        client.cone_search(**crab())
        assert body(session)["properties"] == {
            "position": {"ra": 83.633, "dec": 22.0145},
            "radius": 2.0,
        }

    def test_sexagesimal_is_sent_as_float_degrees(self, client, session, respond):
        # The API only reads JSON numbers as degrees; a string would be a 400.
        respond(200, RESULTS)
        client.cone_search(**crab(ra="05h34m31.94s", dec="+22d00m52.2s", radius="30′"))
        properties = body(session)["properties"]
        ra, dec, radius = (
            properties["position"]["ra"],
            properties["position"]["dec"],
            properties["radius"],
        )
        assert ra == pytest.approx(83.633083, abs=1e-6)
        assert dec == pytest.approx(22.0145, abs=1e-6)
        assert radius == pytest.approx(0.5)
        assert all(isinstance(value, float) for value in (ra, dec, radius))

    def test_colon_notation(self, client, session, respond):
        respond(200, RESULTS)
        client.cone_search(
            **crab(ra="05:34:31.94", dec="+22:00:52.2", radius="00:30:00")
        )
        properties = body(session)["properties"]
        assert properties["position"]["ra"] == pytest.approx(83.633083, abs=1e-6)
        assert properties["position"]["dec"] == pytest.approx(22.0145, abs=1e-6)
        assert properties["radius"] == pytest.approx(0.5)

    @pytest.mark.parametrize(
        "overrides",
        [
            dict(ra=360),
            dict(dec=-91),
            dict(radius=0),
            dict(ra="5h34d"),
            dict(dec="5h"),
            dict(radius="abc"),
        ],
    )
    def test_invalid_position_sends_nothing(self, client, session, overrides):
        with pytest.raises(AstrocolibriConfigError):
            client.cone_search(**crab(**overrides))
        session.request.assert_not_called()

    def test_circle_by_default(self, client, session, respond):
        respond(200, RESULTS)
        client.cone_search(**crab())
        properties = body(session)["properties"]
        assert "trigger_id" not in properties
        assert "margin" not in properties

    def test_contour_trigger_id(self, client, session, respond):
        respond(200, RESULTS)
        client.cone_search(**crab(contour_trigger_id="S230518h"))
        properties = body(session)["properties"]
        assert properties["trigger_id"] == "S230518h"
        assert "margin" not in properties

    def test_contour_margin(self, client, session, respond):
        respond(200, RESULTS)
        client.cone_search(**crab(contour_trigger_id="S230518h", contour_margin=5))
        assert body(session)["properties"]["margin"] == 5.0

    @pytest.mark.parametrize("margin", [0, 20])
    def test_contour_margin_bounds_are_inclusive(
        self, client, session, respond, margin
    ):
        respond(200, RESULTS)
        client.cone_search(**crab(contour_trigger_id="S230518h", contour_margin=margin))
        assert body(session)["properties"]["margin"] == float(margin)

    def test_margin_without_contour_sends_nothing(self, client, session):
        # The API would accept it and silently search the plain circle.
        with pytest.raises(AstrocolibriConfigError, match="contour_trigger_id"):
            client.cone_search(**crab(contour_margin=5))
        session.request.assert_not_called()

    @pytest.mark.parametrize("margin", [-0.1, 20.1, "5", True, math.nan])
    def test_invalid_margin_sends_nothing(self, client, session, margin):
        with pytest.raises(AstrocolibriConfigError, match="contour_margin"):
            client.cone_search(
                **crab(contour_trigger_id="S230518h", contour_margin=margin)
            )
        session.request.assert_not_called()

    @pytest.mark.parametrize("trigger_id", ["", "   ", 42])
    def test_invalid_contour_trigger_id_sends_nothing(
        self, client, session, trigger_id
    ):
        with pytest.raises(AstrocolibriConfigError, match="contour_trigger_id"):
            client.cone_search(**crab(contour_trigger_id=trigger_id))
        session.request.assert_not_called()

    def test_shares_the_search_body(self, client, session, respond):
        respond(200, RESULTS)
        client.cone_search(
            **crab(include_watchlist=True, optional_parameters=["archive"])
        )
        sent_body = body(session)
        assert sent_body["uid"] == FAKE_UID
        assert sent_body["filter"] == MATCH_ALL
        assert sent_body["time_range"] == UTC_RANGE
        assert sent_body["include_watchlist"] is True
        assert sent_body["optional_parameters"] == ["archive"]
        assert "custom_events" not in sent_body

    def test_no_uid_sends_nothing(self, anonymous_client, session):
        with pytest.raises(AstrocolibriAuthError, match="cone_search"):
            anonymous_client.cone_search(**crab())
        session.request.assert_not_called()


class TestConeSearchResponse:
    @pytest.mark.parametrize("region", ["contour_90", "circle"])
    def test_search_region_is_passed_through(self, client, respond, region):
        # A contour search that fell back to the circle is a valid result,
        # not an error: search_region is how the caller finds out.
        respond(200, dict(RESULTS, search_region=region))
        result = client.cone_search(**crab(contour_trigger_id="S230518h"))
        assert result["search_region"] == region

    def test_every_group_is_preserved(self, client, respond):
        payload = dict(RESULTS, search_region="circle")
        respond(200, payload)
        assert client.cone_search(**crab()) == payload

    def test_votable(self, client, respond):
        respond(200, text=XML, content_type="application/xml")
        assert client.cone_search(**crab(return_format="votable")) == XML
