"""
tests/test_consumer.py

Unit tests for the Astro-Colibri Consumer.
confluent-kafka calls are mocked; no real broker is required.

Run:
    pytest tests/ -v
    pytest tests/ -v --cov=astrocolibri --cov-report=term-missing
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from confluent_kafka import KafkaException

from astrocolibri import Consumer, TOPICS
from astrocolibri.exceptions import (
    AstrocolibriAuthError,
    AstrocolibriConfigError,
    AstrocolibriKafkaError,
)


@pytest.fixture
def mock_confluent():
    """Replace the underlying confluent_kafka Consumer with a MagicMock."""
    with patch("astrocolibri.consumer._ConfluentConsumer") as mock_cls:
        yield mock_cls


@pytest.fixture
def consumer(mock_confluent):
    """Return a Consumer wired to the mocked confluent_kafka Consumer."""
    return Consumer(
        username="test-user",
        password="test-password",
        broker_url="localhost:9092",
    )


def make_message(value: bytes = b"alert", error=None) -> MagicMock:
    msg = MagicMock()
    msg.value.return_value = value
    msg.error.return_value = error
    msg.topic.return_value = "astrocolibri.all.JSON"
    msg.partition.return_value = 0
    msg.offset.return_value = 42
    return msg


def make_kafka_error(code: int) -> MagicMock:
    err = MagicMock()
    err.code.return_value = code
    return err


def test_official_topics_include_heartbeat():
    assert "astrocolibri.heartbeat" in TOPICS


class TestConsumerInit:
    def test_broker_url_default(self, mock_confluent):
        Consumer(username="u", password="p")
        cfg = mock_confluent.call_args[0][0]
        assert cfg["bootstrap.servers"] == Consumer.DEFAULT_BROKER_URL

    def test_broker_url_custom(self, mock_confluent):
        Consumer(username="u", password="p", broker_url="localhost:9092")
        cfg = mock_confluent.call_args[0][0]
        assert cfg["bootstrap.servers"] == "localhost:9092"

    def test_sasl_credentials(self, mock_confluent):
        Consumer(username="alice", password="wonderland")
        cfg = mock_confluent.call_args[0][0]
        assert cfg["sasl.username"] == "alice"
        assert cfg["sasl.password"] == "wonderland"
        assert cfg["sasl.mechanism"] == "SCRAM-SHA-512"

    def test_security_protocol_default(self, mock_confluent):
        Consumer(username="u", password="p")
        cfg = mock_confluent.call_args[0][0]
        assert cfg["security.protocol"] == "SASL_SSL"

    def test_security_protocol_ssl(self, mock_confluent):
        Consumer(username="u", password="p", security_protocol="SASL_SSL")
        cfg = mock_confluent.call_args[0][0]
        assert cfg["security.protocol"] == "SASL_SSL"

    def test_group_id_explicit(self, mock_confluent):
        Consumer(username="u", password="p", group_id="my-group")
        cfg = mock_confluent.call_args[0][0]
        assert cfg["group.id"] == "u.my-group"
        assert cfg["enable.auto.commit"] is True

    def test_group_id_is_not_prefixed_twice(self, mock_confluent):
        Consumer(username="u", password="p", group_id="u.my-group")
        cfg = mock_confluent.call_args[0][0]
        assert cfg["group.id"] == "u.my-group"

    def test_group_id_stable_when_none(self, mock_confluent):
        # No group_id means the account-derived default group, identical
        # across restarts, so offsets commit and the read position persists.
        Consumer(username="u", password="p")
        Consumer(username="u", password="p")
        cfg1 = mock_confluent.call_args_list[-2][0][0]
        cfg2 = mock_confluent.call_args_list[-1][0][0]
        assert cfg1["group.id"] == "u.default"
        assert cfg2["group.id"] == "u.default"
        assert cfg1["enable.auto.commit"] is True

    def test_separate_group_ids_do_not_collide(self, mock_confluent):
        # Two scripts on the same credentials each need their own group,
        # otherwise Kafka splits the partitions between them.
        Consumer(username="u", password="p", group_id="script-a")
        Consumer(username="u", password="p", group_id="script-b")
        cfg1 = mock_confluent.call_args_list[-2][0][0]
        cfg2 = mock_confluent.call_args_list[-1][0][0]
        assert cfg1["group.id"] == "u.script-a"
        assert cfg2["group.id"] == "u.script-b"
        assert cfg1["group.id"] != cfg2["group.id"]

    def test_start_at_earliest(self, mock_confluent):
        Consumer(username="u", password="p", start_at="earliest")
        cfg = mock_confluent.call_args[0][0]
        assert cfg["auto.offset.reset"] == "earliest"

    def test_start_at_latest(self, mock_confluent):
        Consumer(username="u", password="p", start_at="latest")
        cfg = mock_confluent.call_args[0][0]
        assert cfg["auto.offset.reset"] == "latest"

    def test_invalid_start_at(self, mock_confluent):
        with pytest.raises(AstrocolibriConfigError, match="start_at"):
            Consumer(username="u", password="p", start_at="middle")

    def test_extra_config_override(self, mock_confluent):
        Consumer(username="u", password="p", config={"session.timeout.ms": 99999})
        cfg = mock_confluent.call_args[0][0]
        assert cfg["session.timeout.ms"] == 99999

    def test_extra_config_cannot_escape_user_group_prefix(self, mock_confluent):
        Consumer(
            username="u",
            password="p",
            group_id="science",
            config={"group.id": "another-users-group"},
        )
        cfg = mock_confluent.call_args[0][0]
        assert cfg["group.id"] == "u.science"

    def test_extra_config_cannot_override_credentials(self, mock_confluent):
        # config= is a documented escape hatch for tuning, but it must never
        # be able to swap the identity the client authenticates with.
        Consumer(
            username="u",
            password="p",
            config={
                "sasl.username": "someone-else",
                "sasl.password": "their-password",
                "sasl.mechanism": "PLAIN",
            },
        )
        cfg = mock_confluent.call_args[0][0]
        assert cfg["sasl.username"] == "u"
        assert cfg["sasl.password"] == "p"
        assert cfg["sasl.mechanism"] == "SCRAM-SHA-512"

    def test_auth_error_when_broker_refuses_connection(self, mock_confluent):
        # Bad credentials are the most common user-facing failure, so the
        # confluent exception must surface as the documented SDK error.
        mock_confluent.side_effect = KafkaException("authentication failed")
        with pytest.raises(AstrocolibriAuthError) as excinfo:
            Consumer(username="u", password="wrong")
        # The message should name the broker the client actually tried.
        assert Consumer.DEFAULT_BROKER_URL in str(excinfo.value)

    def test_auth_error_is_an_astrocolibri_error(self, mock_confluent):
        from astrocolibri import AstrocolibriError

        mock_confluent.side_effect = KafkaException("nope")
        with pytest.raises(AstrocolibriError):
            Consumer(username="u", password="wrong")


class TestConsumerSubscribe:
    def test_subscribe_single_topic(self, consumer):
        consumer.subscribe(["astrocolibri.all.JSON"])
        consumer._consumer.subscribe.assert_called_once_with(["astrocolibri.all.JSON"])

    def test_subscribe_multiple_topics(self, consumer):
        topics = ["astrocolibri.important.JSON", "astrocolibri.important.VOEvent"]
        consumer.subscribe(topics)
        consumer._consumer.subscribe.assert_called_once_with(topics)

    def test_subscribe_with_callbacks(self, consumer):
        on_assign = MagicMock()
        on_revoke = MagicMock()
        consumer.subscribe(
            ["astrocolibri.all.JSON"],
            on_assign=on_assign,
            on_revoke=on_revoke,
        )
        consumer._consumer.subscribe.assert_called_once_with(
            ["astrocolibri.all.JSON"],
            on_assign=on_assign,
            on_revoke=on_revoke,
        )

    def test_subscribe_with_on_lost(self, consumer):
        # on_lost fires when partitions are taken away involuntarily, which is
        # how a consumer notices it dropped out of the group.
        on_lost = MagicMock()
        consumer.subscribe(["astrocolibri.all.JSON"], on_lost=on_lost)
        consumer._consumer.subscribe.assert_called_once_with(
            ["astrocolibri.all.JSON"],
            on_lost=on_lost,
        )

    def test_subscribe_omits_callbacks_not_given(self, consumer):
        # confluent-kafka rejects a None callback, so unset ones must not be
        # forwarded at all.
        consumer.subscribe(["astrocolibri.all.JSON"])
        consumer._consumer.subscribe.assert_called_once_with(
            ["astrocolibri.all.JSON"],
        )


class TestConsumerConsume:
    def test_consume_yields_message(self, consumer):
        msg = make_message(b'{"id": "AC-001"}')
        consumer._consumer.consume.side_effect = [[msg], []]
        result = list(consumer.consume(timeout=1.0))
        assert result == [msg]

    def test_consume_yields_multiple_messages(self, consumer):
        msg1 = make_message(b"alert-1")
        msg2 = make_message(b"alert-2")
        consumer._consumer.consume.side_effect = [[msg1, msg2], []]
        result = list(consumer.consume(num_messages=2, timeout=1.0))
        assert result == [msg1, msg2]

    def test_consume_stops_on_empty(self, consumer):
        consumer._consumer.consume.return_value = []
        result = list(consumer.consume(timeout=1.0))
        assert result == []

    def test_consume_skips_partition_eof(self, consumer):
        from confluent_kafka import KafkaError

        eof_error = make_kafka_error(KafkaError._PARTITION_EOF)
        eof_msg = make_message(error=eof_error)
        real_msg = make_message(b"real-alert")

        consumer._consumer.consume.side_effect = [[eof_msg, real_msg], []]
        result = list(consumer.consume(timeout=1.0))
        assert result == [real_msg]

    def test_consume_raises_on_kafka_error(self, consumer):
        from confluent_kafka import KafkaError

        err = make_kafka_error(KafkaError.UNKNOWN_TOPIC_OR_PART)
        bad_msg = make_message(error=err)
        consumer._consumer.consume.return_value = [bad_msg]

        with pytest.raises(AstrocolibriKafkaError, match="Kafka error"):
            list(consumer.consume(timeout=1.0))

    def test_consume_calls_underlying_with_params(self, consumer):
        consumer._consumer.consume.return_value = []
        list(consumer.consume(num_messages=5, timeout=2.5))
        consumer._consumer.consume.assert_called_once_with(num_messages=5, timeout=2.5)


class TestConsumerLifecycle:
    def test_close(self, consumer):
        consumer.close()
        consumer._consumer.close.assert_called_once()

    def test_context_manager_calls_close(self, mock_confluent):
        with Consumer(username="u", password="p", broker_url="localhost:9092") as c:
            inner = c._consumer
        inner.close.assert_called_once()

    def test_context_manager_closes_on_exception(self, mock_confluent):
        with pytest.raises(ValueError):
            with Consumer(username="u", password="p") as c:
                inner = c._consumer
                raise ValueError("boom")
        inner.close.assert_called_once()
