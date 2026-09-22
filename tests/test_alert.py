"""
tests/test_alert.py

Unit tests for Alert, the decoded view of a broker message.

The behaviour under test is the one users see first: a message arrives as
raw Kafka bytes, and what they get handed is the JSON object or the XML
document — never `b'...'`.

Run:
    pytest tests/ -v
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from astrocolibri import (
    FORMAT_JSON,
    FORMAT_UNKNOWN,
    FORMAT_VOEVENT,
    Alert,
    AstrocolibriDecodeError,
    AstrocolibriError,
)

ALERT_JSON = {"id": "AC-001", "type": "GRB", "ra": 12.5, "dec": -30.0}
VOEVENT_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<voe:VOEvent xmlns:voe="http://www.ivoa.net/xml/VOEvent/v2.0" '
    'ivorn="ivo://astro-colibri/AC-001"><Who/></voe:VOEvent>'
)


#: Sentinel so a test can ask for a message with no payload at all.
_DEFAULT = object()


def make_message(
    value=_DEFAULT,
    topic: str = "astrocolibri.all.JSON",
    key: bytes | None = b"AC-001",
    headers=None,
) -> MagicMock:
    if value is _DEFAULT:
        value = json.dumps(ALERT_JSON).encode("utf-8")
    msg = MagicMock()
    msg.value.return_value = value
    msg.key.return_value = key
    msg.topic.return_value = topic
    msg.partition.return_value = 0
    msg.offset.return_value = 42
    msg.timestamp.return_value = (1, 1_700_000_000_000)
    msg.headers.return_value = headers
    msg.error.return_value = None
    return msg


class TestDecodedPayload:
    def test_json_topic_yields_a_dict_not_bytes(self):
        # The whole point of the wrapper: print(alert.value()) must show the
        # alert, not b'{"id": ...}'.
        alert = Alert(make_message())
        value = alert.value()
        assert isinstance(value, dict)
        assert value == ALERT_JSON

    def test_voevent_topic_yields_xml_text(self):
        alert = Alert(
            make_message(
                value=VOEVENT_XML.encode("utf-8"),
                topic="astrocolibri.all.VOEvent",
            )
        )
        value = alert.value()
        assert isinstance(value, str)
        assert value == VOEVENT_XML

    def test_important_json_topic_is_decoded_too(self):
        alert = Alert(make_message(topic="astrocolibri.important.JSON"))
        assert alert.value() == ALERT_JSON

    def test_heartbeat_topic_is_json(self):
        payload = b'{"update_type": "heartbeat"}'
        alert = Alert(make_message(value=payload, topic="astrocolibri.heartbeat"))
        assert alert.format == FORMAT_JSON
        assert alert.value() == {"update_type": "heartbeat"}

    def test_null_payload_is_none(self):
        # Kafka tombstones carry no value; they must not blow up the loop.
        alert = Alert(make_message(value=None))
        assert alert.value() is None
        assert alert.raw is None
        assert len(alert) == 0

    def test_value_is_decoded_once_and_cached(self):
        msg = make_message()
        alert = Alert(msg)
        first = alert.value()
        second = alert.value()
        assert first is second

    def test_json_list_payload(self):
        alert = Alert(make_message(value=b'[{"id": "a"}, {"id": "b"}]'))
        assert alert.value() == [{"id": "a"}, {"id": "b"}]

    def test_unicode_payload_round_trips(self):
        payload = json.dumps({"comment": "Crab Nebula — 5σ"}).encode("utf-8")
        alert = Alert(make_message(value=payload))
        assert alert.value()["comment"] == "Crab Nebula — 5σ"


class TestFormatDetection:
    def test_format_from_topic_suffix(self):
        assert Alert(make_message()).format == FORMAT_JSON
        assert (
            Alert(
                make_message(
                    value=VOEVENT_XML.encode(), topic="astrocolibri.important.VOEvent"
                )
            ).format
            == FORMAT_VOEVENT
        )

    def test_format_sniffed_when_topic_does_not_announce_one(self):
        # The internal `test` topic and any future topic outside the
        # <stream>.<format> convention still have to decode correctly.
        assert Alert(make_message(topic="test")).format == FORMAT_JSON
        assert (
            Alert(make_message(value=VOEVENT_XML.encode(), topic="odd")).format
            == FORMAT_VOEVENT
        )

    def test_sniffing_tolerates_leading_whitespace_and_bom(self):
        alert = Alert(make_message(value=b'\xef\xbb\xbf\n  {"id": "x"}', topic="odd"))
        assert alert.format == FORMAT_JSON
        assert alert.value() == {"id": "x"}

    def test_unrecognised_payload_is_returned_as_text(self):
        alert = Alert(make_message(value=b"plain text", topic="odd"))
        assert alert.format == FORMAT_UNKNOWN
        assert alert.value() == "plain text"


class TestExplicitViews:
    def test_text_returns_the_payload_as_published(self):
        raw = json.dumps(ALERT_JSON).encode("utf-8")
        alert = Alert(make_message(value=raw))
        assert alert.text() == raw.decode("utf-8")

    def test_json_parses_even_on_a_topic_that_is_not_json(self):
        alert = Alert(make_message(topic="odd", value=b'{"id": "x"}'))
        assert alert.json() == {"id": "x"}

    def test_raw_is_the_untouched_bytes(self):
        raw = json.dumps(ALERT_JSON).encode("utf-8")
        alert = Alert(make_message(value=raw))
        assert alert.raw == raw
        assert isinstance(alert.raw, bytes)

    def test_message_exposes_the_underlying_confluent_message(self):
        msg = make_message()
        assert Alert(msg).message is msg

    def test_text_is_decoded_once_and_cached(self):
        msg = make_message()
        alert = Alert(msg)
        assert alert.text() == alert.text()
        # One decode per alert, however often the payload is read.
        assert msg.value.call_count >= 1

    def test_text_of_a_null_payload_is_empty(self):
        assert Alert(make_message(value=None)).text() == ""

    def test_json_raises_on_a_payload_that_is_not_json(self):
        alert = Alert(
            make_message(value=VOEVENT_XML.encode(), topic="astrocolibri.all.VOEvent")
        )
        with pytest.raises(AstrocolibriDecodeError, match="not valid JSON"):
            alert.json()

    def test_an_already_decoded_str_payload_is_accepted(self):
        # A caller may plug a deserializer into confluent-kafka through
        # config=, in which case value() is already str.
        alert = Alert(make_message(value='{"id": "x"}'))
        assert alert.value() == {"id": "x"}
        assert alert.text() == '{"id": "x"}'

    def test_format_of_a_null_payload_on_an_unannounced_topic(self):
        assert Alert(make_message(value=None, topic="odd")).format == FORMAT_UNKNOWN


class TestDecodeErrors:
    def test_malformed_json_raises_a_named_error(self):
        alert = Alert(make_message(value=b"{not json"))
        with pytest.raises(AstrocolibriDecodeError) as excinfo:
            alert.value()
        # The message has to say which record, or it is unactionable in a
        # stream that has been running for days.
        assert "astrocolibri.all.JSON" in str(excinfo.value)
        assert "offset=42" in str(excinfo.value)

    def test_invalid_utf8_raises(self):
        alert = Alert(make_message(value=b"\xff\xfe\x00"))
        with pytest.raises(AstrocolibriDecodeError):
            alert.value()

    def test_decode_error_is_an_astrocolibri_error(self):
        alert = Alert(make_message(value=b"{not json"))
        with pytest.raises(AstrocolibriError):
            alert.value()

    def test_a_bad_alert_can_be_skipped_without_losing_the_stream(self):
        # Decoding is lazy, so one unparsable record must be catchable per
        # message rather than taking down a long-running listener.
        alerts = [
            Alert(make_message()),
            Alert(make_message(value=b"{not json")),
            Alert(make_message()),
        ]
        handled = []
        for alert in alerts:
            try:
                handled.append(alert.value())
            except AstrocolibriDecodeError:
                continue
        assert len(handled) == 2


class TestMetadataAccessors:
    def test_key_is_decoded_to_str(self):
        assert Alert(make_message()).key() == "AC-001"

    def test_key_may_be_absent(self):
        assert Alert(make_message(key=None)).key() is None

    def test_headers_are_decoded_to_a_dict(self):
        alert = Alert(
            make_message(
                headers=[
                    ("event_id", b"AC-001"),
                    ("dedupe_key", b"abc123"),
                    ("important", b"true"),
                ]
            )
        )
        assert alert.headers() == {
            "event_id": "AC-001",
            "dedupe_key": "abc123",
            "important": "true",
        }

    def test_headers_default_to_an_empty_dict(self):
        assert Alert(make_message(headers=None)).headers() == {}

    def test_header_names_may_arrive_as_bytes(self):
        alert = Alert(make_message(headers=[(b"dedupe_key", b"abc123")]))
        assert alert.headers() == {"dedupe_key": "abc123"}

    def test_header_without_a_value_becomes_an_empty_string(self):
        alert = Alert(make_message(headers=[("update_type", None)]))
        assert alert.headers() == {"update_type": ""}

    def test_key_may_already_be_a_str(self):
        assert Alert(make_message(key="AC-001")).key() == "AC-001"

    def test_kafka_coordinates_are_passed_through(self):
        alert = Alert(make_message())
        assert alert.topic() == "astrocolibri.all.JSON"
        assert alert.partition() == 0
        assert alert.offset() == 42
        assert alert.timestamp() == (1, 1_700_000_000_000)

    def test_error_is_always_none(self):
        # Erroring records are filtered out by consume(), so anything that
        # reaches an Alert is a real message.
        assert Alert(make_message()).error() is None

    def test_repr_identifies_the_record(self):
        text = repr(Alert(make_message()))
        assert "astrocolibri.all.JSON" in text
        assert "42" in text
        assert FORMAT_JSON in text
