"""
tests/test_filtering.py

Unit tests for EventFilter, Client.get_saved_filters() and
Consumer.consume(event_filter=...): applying Astro-COLIBRI filters to events
and to the broker stream.

The filter engine itself is tested in test_vendored_filters.py; this file
covers how subscribers reach it. Kafka and the API are mocked.

Run:
    pytest tests/test_filtering.py -v
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from astrocolibri import (
    Alert,
    AstrocolibriAPIError,
    AstrocolibriAuthError,
    AstrocolibriConfigError,
    AstrocolibriDecodeError,
    AstrocolibriNotFoundError,
    AstrocolibriRateLimitError,
    Consumer,
    EventFilter,
    parse_voevent,
)

from .helpers import FAKE_UID, make_response, sent

VOEVENTS = Path(__file__).resolve().parent / "data" / "voevents"

GRB_ONLY = {
    "type": "FieldSpecification",
    "field": "type",
    "operation": "==",
    "typeField": "string",
    "value": "grb",
}

#: Optical supernovae brighter than magnitude 18 in ZTF g at the last detection.
BRIGHT_SN = {
    "type": "AndSpecification",
    "specs": [
        {
            "type": "FieldSpecification",
            "field": "type",
            "operation": "==",
            "typeField": "string",
            "value": "ot_sn",
        },
        {
            "type": "FieldSpecification",
            "field": "photometry.ztf_g.last.mag",
            "operation": "<=",
            "typeField": "maps_float",
            "value": "18.5",
        },
    ],
}


def message(payload, topic="astrocolibri.all.JSON"):
    """A confluent_kafka.Message stand-in carrying ``payload``."""
    if isinstance(payload, dict):
        payload = json.dumps(payload).encode("utf-8")
    msg = MagicMock()
    msg.value.return_value = payload
    msg.topic.return_value = topic
    msg.partition.return_value = 0
    msg.offset.return_value = 7
    msg.key.return_value = b"key"
    msg.headers.return_value = None
    msg.error.return_value = None
    return msg


def sn_voevent() -> bytes:
    return (VOEVENTS / "astrocolibri_ot_photometry.xml").read_bytes()


class TestConstruction:
    def test_a_filter_dictionary(self):
        assert EventFilter(GRB_ONLY).matches({"type": "GRB"})

    def test_a_request_body_or_saved_filters_response(self):
        my_filter = EventFilter({"filter": GRB_ONLY, "version": "filters_v2_32_0"})
        assert my_filter.to_dict() == GRB_ONLY

    def test_the_callers_dictionary_is_left_alone(self):
        spec = json.loads(json.dumps(BRIGHT_SN))
        EventFilter(spec)
        # The engine fills in defaults (isActivated, ...) where it reads them.
        assert spec == BRIGHT_SN

    @pytest.mark.parametrize(
        "spec, message_part",
        [
            ({"type": "SoonSpecification"}, "Unknown specification name"),
            ({**GRB_ONLY, "operation": "~"}, "Unknown filter operation"),
            ({"type": "FieldSpecification", "field": "ra"}, "Missing value"),
            ({}, "empty"),
            ("grb", "must be a dictionary"),
        ],
        ids=["unknown-type", "bad-operator", "missing-value", "empty", "not-a-dict"],
    )
    def test_invalid_filters_raise_a_config_error(self, spec, message_part):
        with pytest.raises(AstrocolibriConfigError, match=message_part):
            EventFilter(spec)

    def test_from_file_reads_the_app_export(self, tmp_path):
        path = tmp_path / "Astro-COLIBRI_filters.json"
        # Written with a BOM, as some editors do.
        path.write_text(json.dumps(BRIGHT_SN, indent=2), encoding="utf-8-sig")
        assert EventFilter.from_file(path).to_dict() == BRIGHT_SN
        assert EventFilter.from_file(str(path)).to_dict() == BRIGHT_SN

    def test_from_file_that_is_not_json(self, tmp_path):
        path = tmp_path / "filters.json"
        path.write_text("type: grb", encoding="utf-8")
        with pytest.raises(AstrocolibriConfigError, match="not a JSON file"):
            EventFilter.from_file(path)

    def test_from_file_that_does_not_exist(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            EventFilter.from_file(tmp_path / "missing.json")

    def test_repr_names_the_top_specification(self):
        assert repr(EventFilter(BRIGHT_SN)) == "<EventFilter AndSpecification>"


class TestSavedFilters:
    def test_client_posts_the_uid_in_the_body(self, client, respond):
        respond(200, {"filter": GRB_ONLY, "version": "filters_v2_32_0"})

        assert client.get_saved_filters() == GRB_ONLY

        method, url, kwargs = sent(client._session)
        assert (method, url) == ("POST", "https://astro-colibri.science/saved_filters")
        assert kwargs["json"] == {"uid": FAKE_UID}
        assert kwargs["params"] is None

    def test_from_saved_filters_with_a_client(self, client, respond):
        respond(200, {"filter": BRIGHT_SN, "version": "filters_v2_32_0"})
        assert EventFilter.from_saved_filters(client=client).to_dict() == BRIGHT_SN

    def test_from_saved_filters_reads_the_environment(self, monkeypatch, session):
        monkeypatch.setenv("ASTROCOLIBRI_UID", FAKE_UID)
        session.request.return_value = make_response(200, {"filter": GRB_ONLY})
        with patch("astrocolibri.client.requests.Session", return_value=session):
            my_filter = EventFilter.from_saved_filters()
        assert my_filter.to_dict() == GRB_ONLY
        assert session.request.call_args.kwargs["json"] == {"uid": FAKE_UID}
        session.close.assert_called_once()

    def test_no_saved_filters(self, client, respond):
        respond(404, {"message": "No saved filters for this user", "status_code": 404})
        with pytest.raises(
            AstrocolibriNotFoundError, match="Set them up in the Astro-COLIBRI app"
        ):
            EventFilter.from_saved_filters(client=client)

    def test_quota_exhausted(self, client, respond):
        respond(
            429,
            {
                "message": "Rate limit exceeded. Renewal at 2026-10-15 08:00:00",
                "status_code": 429,
            },
        )
        with pytest.raises(AstrocolibriRateLimitError):
            client.get_saved_filters()

    def test_unknown_user(self, client, respond):
        respond(403, {"message": "User does not exist", "status_code": 403})
        with pytest.raises(AstrocolibriAuthError):
            client.get_saved_filters()

    @pytest.mark.parametrize("body", [{"version": "x"}, {"filter": {}}, ["x"]])
    def test_malformed_response(self, client, respond, body):
        respond(200, body)
        with pytest.raises(AstrocolibriAPIError, match="does not understand"):
            client.get_saved_filters()

    def test_no_uid_sends_nothing(self, anonymous_client, session):
        with pytest.raises(AstrocolibriAuthError, match="get_saved_filters"):
            EventFilter.from_saved_filters(client=anonymous_client)
        session.request.assert_not_called()

    def test_uid_and_client_together(self, client):
        with pytest.raises(AstrocolibriConfigError, match="not both"):
            EventFilter.from_saved_filters(FAKE_UID, client=client)


class TestMatches:
    def test_an_event_dictionary(self):
        my_filter = EventFilter(GRB_ONLY)
        assert my_filter.matches({"type": "grb"})
        assert not my_filter.matches({"type": "gw"})

    def test_the_same_event_from_both_kinds_of_topic(self):
        my_filter = EventFilter(BRIGHT_SN)
        voevent_alert = Alert(message(sn_voevent(), topic="astrocolibri.all.VOEvent"))
        json_alert = Alert(message(voevent_alert.event()))
        assert my_filter.matches(voevent_alert)
        assert my_filter.matches(json_alert)

    def test_a_parsed_voevent(self):
        document = parse_voevent(sn_voevent())
        assert EventFilter(BRIGHT_SN).matches(document)
        assert not EventFilter(GRB_ONLY).matches(document)

    def test_a_value_that_cannot_be_compared_does_not_pass(self):
        numeric = {
            "type": "FieldSpecification",
            "field": "redshift",
            "operation": ">",
            "typeField": "float",
            "value": "0.1",
        }
        assert not EventFilter(numeric).matches({"redshift": "unknown"})

    def test_an_undecodable_alert_raises(self):
        with pytest.raises(AstrocolibriDecodeError):
            EventFilter(GRB_ONLY).matches(Alert(message(b"{not json")))

    def test_something_else_is_refused(self):
        with pytest.raises(AstrocolibriConfigError, match="takes an event dictionary"):
            EventFilter(GRB_ONLY).matches("grb")


class TestFilter:
    def test_keeps_matching_alerts_in_order(self):
        alerts = [
            Alert(message({"trigger_id": "A", "type": "grb"})),
            Alert(message({"trigger_id": "B", "type": "gw"})),
            Alert(message({"trigger_id": "C", "type": "GRB"})),
        ]
        kept = list(EventFilter(GRB_ONLY).filter(alerts))
        assert [alert.event()["trigger_id"] for alert in kept] == ["A", "C"]

    def test_heartbeats_always_pass(self):
        heartbeat = Alert(message({"status": "alive"}, topic="astrocolibri.heartbeat"))
        assert list(EventFilter(GRB_ONLY).filter([heartbeat])) == [heartbeat]

    def test_an_undecodable_alert_passes_with_a_warning(self, caplog):
        broken = Alert(message(b"{not json"))
        with caplog.at_level(logging.WARNING, logger="astrocolibri.filtering"):
            assert list(EventFilter(GRB_ONLY).filter([broken])) == [broken]
        assert "could not be filtered" in caplog.text

    def test_raw_messages_come_out_raw(self):
        grb, gw = message({"type": "grb"}), message({"type": "gw"})
        assert list(EventFilter(GRB_ONLY).filter([grb, gw])) == [grb]

    def test_api_results(self):
        results = [
            {"type": "grb", "trigger_id": "A"},
            {"type": "gw", "trigger_id": "B"},
        ]
        assert list(EventFilter(GRB_ONLY).filter(results)) == [results[0]]

    def test_is_lazy(self):
        def endless():
            while True:
                yield {"type": "grb"}

        stream = EventFilter(GRB_ONLY).filter(endless())
        assert next(stream) == {"type": "grb"}


@pytest.fixture
def consumer():
    with patch("astrocolibri.consumer._ConfluentConsumer"):
        yield Consumer(username="test-user", password="test-password")


class TestConsumeWithFilter:
    def test_only_matching_alerts_are_yielded(self, consumer):
        grb = message({"trigger_id": "A", "type": "grb"})
        gw = message({"trigger_id": "B", "type": "gw"})
        sn = message(sn_voevent(), topic="astrocolibri.all.VOEvent")
        consumer._consumer.consume.side_effect = [[grb, gw, sn], []]

        kept = list(consumer.consume(timeout=0.1, event_filter=EventFilter(GRB_ONLY)))

        assert [alert.message for alert in kept] == [grb]

    def test_a_filter_dictionary_is_accepted(self, consumer):
        sn = message(sn_voevent(), topic="astrocolibri.all.VOEvent")
        consumer._consumer.consume.side_effect = [[sn], []]

        kept = list(consumer.consume(timeout=0.1, event_filter=BRIGHT_SN))

        assert [alert.event()["trigger_id"] for alert in kept] == ["TNS2025mq"]

    def test_an_invalid_filter_fails_at_the_call(self, consumer):
        with pytest.raises(AstrocolibriConfigError):
            consumer.consume(event_filter={"type": "SoonSpecification"})
        consumer._consumer.consume.assert_not_called()

    def test_raw_mode_yields_raw_messages(self):
        with patch("astrocolibri.consumer._ConfluentConsumer"):
            raw = Consumer(username="u", password="p", decode=False)
        grb, gw = message({"type": "grb"}), message({"type": "gw"})
        raw._consumer.consume.side_effect = [[grb, gw], []]

        assert list(raw.consume(timeout=0.1, event_filter=GRB_ONLY)) == [grb]

    def test_without_a_filter_nothing_changes(self, consumer):
        grb, gw = message({"type": "grb"}), message({"type": "gw"})
        consumer._consumer.consume.side_effect = [[grb, gw], []]

        assert [alert.message for alert in consumer.consume(timeout=0.1)] == [grb, gw]
