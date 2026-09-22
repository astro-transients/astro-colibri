"""
tests/test_examples.py

Smoke tests for the scripts in examples/.

Examples rot quietly: an API change that breaks one is only noticed by the
next person who copies it. Each script's main() runs here against mocked
responses, so a renamed method, a changed return shape or a typo fails the
test suite instead.

Run:
    pytest tests/test_examples.py -v
"""

from __future__ import annotations

import importlib.util
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from .helpers import FAKE_UID, make_response

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

XRT = {
    "trigger_id": "922968",
    "source_name": "GRB 190829A",
    "type": "grb",
    "observatory": "swift",
    "instrument": "xrt",
    "time": "2019-08-29T19:56:44.600",
    "ra": 44.5423,
    "dec": -8.9576,
    "err": 0.0016,
}
ALL_EVENTS = {
    "name": "GRB 190829A",
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
GW = {
    "trigger_id": "S230518h",
    "source_name": "S230518h",
    "type": "gw",
    "time": "2023-05-18T12:59:08",
    "ra": 100.72265625,
    "dec": -22.1048,
    "err": -1.0,
}
MISS = [{"trigger_id": "NOPE", "error": "event not found"}]
RATE_LIMITED = {
    "message": "Rate limit exceeded. Renewal at 2026-09-13T08:00:00",
    "status_code": 429,
}
UNKNOWN_SOURCE = {
    "name": "QQQ",
    "ra": -1000,
    "dec": -1000,
    "err": -1000,
    "trigger_id": "",
    "timestamp": -1,
    "origin": "Astro-COLIBRI",
}


def load(name):
    """Import examples/<name>.py as a module, without running its __main__ block."""
    spec = importlib.util.spec_from_file_location(
        f"example_{name}", EXAMPLES / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def api():
    """The mocked session behind every Client an example creates."""
    with patch("astrocolibri.client.requests.Session") as session_cls:
        yield session_cls.return_value


@pytest.fixture
def uid(monkeypatch):
    monkeypatch.setenv("ASTROCOLIBRI_UID", FAKE_UID)


def test_every_example_is_covered():
    # A new script without a test class here would escape the smoke tests.
    scripts = {path.stem for path in EXAMPLES.glob("*.py")}
    assert scripts == {
        "get_event",
        "resolve_source",
        "latest_transients",
        "cone_search",
        "contour_search",
    }


class TestGetEvent:
    def test_prints_the_event(self, api, capsys):
        api.request.return_value = make_response(200, XRT)
        assert load("get_event").main("GRB 190829A") == 0
        out = capsys.readouterr().out
        assert "922968" in out
        assert "GRB 190829A" in out

    def test_needs_no_uid(self, api):
        api.request.return_value = make_response(200, XRT)
        assert load("get_event").main("GRB 190829A") == 0

    def test_missing_event(self, api, capsys):
        api.request.return_value = make_response(207, MISS)
        assert load("get_event").main("NOPE") == 1
        assert "No event matches 'NOPE'" in capsys.readouterr().out


class TestResolveSource:
    def test_lists_localizations_and_fetches_the_best(self, api, capsys):
        api.request.side_effect = [
            make_response(200, ALL_EVENTS),
            make_response(200, XRT),
        ]
        assert load("resolve_source").main("GRB 190829A") == 0
        out = capsys.readouterr().out
        assert "2 localization(s)" in out
        # Millisecond timestamps are converted, not misread as seconds.
        assert "2019-08-29 19:56:44 UTC" in out
        assert api.request.call_args_list[1][1]["params"] == [("trigger_id", "922968")]

    def test_catalog_source_falls_back_to_the_summary(self, api, capsys):
        api.request.side_effect = [
            make_response(200, {"name": "Crab", "events": []}),
            make_response(
                200,
                {"name": "Crab", "ra": 83.63, "dec": 22.01, "origin": "Astro-COLIBRI"},
            ),
        ]
        assert load("resolve_source").main("Crab") == 0
        assert "no transient events" in capsys.readouterr().out
        # A SIMBAD resolution can be slow; the fallback call allows for it.
        assert api.request.call_args_list[1][1]["timeout"] == 300.0

    def test_unknown_source(self, api, capsys):
        api.request.side_effect = [
            make_response(200, {"name": "QQQ", "events": []}),
            make_response(200, UNKNOWN_SOURCE),
        ]
        assert load("resolve_source").main("QQQ") == 1
        assert "No source named 'QQQ'" in capsys.readouterr().out


class TestLatestTransients:
    START = "2026-09-01T00:00:00Z"
    END = "2026-09-02T00:00:00Z"

    def test_prints_transients(self, api, uid, capsys):
        api.request.return_value = make_response(200, {"voevents": [XRT]})
        assert load("latest_transients").main(self.START, self.END) == 0
        assert "Trigger ID: 922968" in capsys.readouterr().out

    def test_empty_window(self, api, uid, capsys):
        api.request.return_value = make_response(200, {"voevents": []})
        assert load("latest_transients").main(self.START, self.END) == 0
        assert "No transients" in capsys.readouterr().out

    def test_default_window_is_the_previous_utc_day(self):
        start, end = load("latest_transients").previous_utc_day()
        assert end - start == timedelta(days=1)
        assert end.utcoffset() == timedelta(0)
        assert (end.hour, end.minute, end.second, end.microsecond) == (0, 0, 0, 0)

    def test_missing_uid_explains_the_setup(self, api, capsys):
        assert load("latest_transients").main(self.START, self.END) == 1
        assert "ASTROCOLIBRI_UID" in capsys.readouterr().out
        api.request.assert_not_called()

    def test_exhausted_quota(self, api, uid, capsys):
        api.request.return_value = make_response(429, RATE_LIMITED)
        assert load("latest_transients").main(self.START, self.END) == 1
        assert "renews at 2026-09-13 08:00:00" in capsys.readouterr().out

    def test_uid_is_never_printed(self, api, uid, capsys):
        api.request.return_value = make_response(
            403, {"message": "User does not exist", "status_code": 403}
        )
        assert load("latest_transients").main(self.START, self.END) == 1
        assert FAKE_UID not in capsys.readouterr().out


class TestConeSearch:
    RESULTS = {
        "voevents": [XRT],
        "sources": [{"source_name": "4FGL J0534.5+2201i", "assoc": "Crab Nebula"}],
        "Xsources": [],
        "icecat": [],
        "search_region": "circle",
    }

    def test_prints_transients_and_catalog_sources(self, api, uid, capsys):
        api.request.return_value = make_response(200, self.RESULTS)
        assert load("cone_search").main() == 0
        out = capsys.readouterr().out
        assert "GRB 190829A" in out
        assert "4FGL J0534.5+2201i" in out

    def test_sends_the_crab_position_in_degrees(self, api, uid):
        api.request.return_value = make_response(200, self.RESULTS)
        load("cone_search").main()
        position = api.request.call_args[1]["json"]["properties"]["position"]
        assert position["ra"] == pytest.approx(83.633083, abs=1e-6)
        assert position["dec"] == pytest.approx(22.0145, abs=1e-6)


class TestContourSearch:
    def test_searches_the_contour_in_the_week_after_the_merger(self, api, uid, capsys):
        api.request.side_effect = [
            make_response(200, GW),
            make_response(200, {"voevents": [], "search_region": "contour_90"}),
        ]
        assert load("contour_search").main("S230518h") == 0
        body = api.request.call_args_list[1][1]["json"]
        assert body["properties"]["trigger_id"] == "S230518h"
        assert body["properties"]["margin"] == 1.0
        assert body["time_range"] == {
            "min": "2023-05-18T12:59:08+00:00",
            "max": "2023-05-25T12:59:08+00:00",
        }
        assert "90% contour" in capsys.readouterr().out

    def test_reports_the_circle_fallback(self, api, uid, capsys):
        api.request.side_effect = [
            make_response(200, GW),
            make_response(200, {"voevents": [], "search_region": "circle"}),
        ]
        assert load("contour_search").main("S230518h") == 0
        assert "No contour is stored" in capsys.readouterr().out

    def test_unknown_event_spends_no_search(self, api, uid, capsys):
        api.request.return_value = make_response(207, MISS)
        assert load("contour_search").main("NOPE") == 1
        assert api.request.call_count == 1
