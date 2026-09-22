"""
tests/test_consumer.py

Unit tests for the Astro-Colibri Consumer.
confluent-kafka calls are mocked; no real broker is required.

Run:
    pytest tests/ -v
    pytest tests/ -v --cov=astrocolibri --cov-report=term-missing
"""

from __future__ import annotations

import itertools
import logging
from unittest.mock import MagicMock, patch

import pytest
from astrocolibri import TOPICS, Alert, Consumer
from astrocolibri.exceptions import (
    AstrocolibriAuthError,
    AstrocolibriConfigError,
    AstrocolibriKafkaError,
)
from confluent_kafka import KafkaException


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


def make_message(value: bytes = b'{"id": "AC-001"}', error=None) -> MagicMock:
    msg = MagicMock()
    msg.value.return_value = value
    msg.error.return_value = error
    msg.topic.return_value = "astrocolibri.all.JSON"
    msg.partition.return_value = 0
    msg.offset.return_value = 42
    msg.headers.return_value = None
    return msg


def make_kafka_error(code: int, retriable: bool = False) -> MagicMock:
    err = MagicMock()
    err.code.return_value = code
    err.retriable.return_value = retriable
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
    def test_consume_yields_decoded_alerts(self, consumer):
        msg = make_message(b'{"id": "AC-001"}')
        consumer._consumer.consume.side_effect = [[msg], []]
        result = list(consumer.consume(timeout=1.0))
        assert len(result) == 1
        alert = result[0]
        # What the user gets is the alert, not b'{"id": "AC-001"}'.
        assert isinstance(alert, Alert)
        assert alert.value() == {"id": "AC-001"}
        assert alert.message is msg

    def test_consume_yields_multiple_messages(self, consumer):
        msg1 = make_message(b'{"id": "a"}')
        msg2 = make_message(b'{"id": "b"}')
        consumer._consumer.consume.side_effect = [[msg1, msg2], []]
        result = list(consumer.consume(num_messages=2, timeout=1.0))
        assert [a.value() for a in result] == [{"id": "a"}, {"id": "b"}]

    def test_decode_false_yields_the_raw_message(self, mock_confluent):
        # Documented escape hatch for code that decodes the payload itself.
        c = Consumer(username="u", password="p", decode=False)
        msg = make_message()
        c._consumer.consume.side_effect = [[msg], []]
        result = list(c.consume(timeout=1.0))
        assert result == [msg]
        assert result[0].value() == b'{"id": "AC-001"}'

    def test_consume_stops_on_empty(self, consumer):
        consumer._consumer.consume.return_value = []
        result = list(consumer.consume(timeout=1.0))
        assert result == []

    def test_consume_skips_partition_eof(self, consumer):
        from confluent_kafka import KafkaError

        eof_error = make_kafka_error(KafkaError._PARTITION_EOF)
        eof_msg = make_message(error=eof_error)
        real_msg = make_message(b'{"id": "real"}')

        consumer._consumer.consume.side_effect = [[eof_msg, real_msg], []]
        result = list(consumer.consume(timeout=1.0))
        assert [a.message for a in result] == [real_msg]

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


class TestContinuousListening:
    """The default consume() is a listener, not a one-shot fetch."""

    def test_default_consume_keeps_waiting_through_idle_polls(self, consumer):
        # A quiet stretch on the broker must not end the loop: the two empty
        # polls here stand for hours with no alert.
        msg1 = make_message(b'{"id": "a"}')
        msg2 = make_message(b'{"id": "b"}')
        consumer._consumer.consume.side_effect = [[msg1], [], [], [msg2]]

        received = list(itertools.islice(consumer.consume(), 2))

        assert [a.value()["id"] for a in received] == ["a", "b"]
        assert consumer._consumer.consume.call_count == 4

    def test_default_consume_polls_in_slices_not_one_blocking_call(self, consumer):
        # Blocking librdkafka forever would swallow Ctrl-C, so the infinite
        # form polls in poll_interval slices instead of passing timeout=-1 on.
        consumer._consumer.consume.side_effect = [[], [make_message()]]
        next(consumer.consume())
        for call in consumer._consumer.consume.call_args_list:
            assert call.kwargs["timeout"] == 1.0

    def test_poll_interval_is_configurable(self, mock_confluent):
        c = Consumer(username="u", password="p", poll_interval=0.25)
        c._consumer.consume.side_effect = [[], [make_message()]]
        next(c.consume())
        assert c._consumer.consume.call_args.kwargs["timeout"] == 0.25

    def test_invalid_poll_interval(self, mock_confluent):
        with pytest.raises(AstrocolibriConfigError, match="poll_interval"):
            Consumer(username="u", password="p", poll_interval=0)

    def test_timeout_still_terminates_the_generator(self, consumer):
        # Batch mode keeps its documented behaviour: an idle timeout ends
        # the generator so the caller can do other work.
        consumer._consumer.consume.side_effect = [[make_message()], []]
        assert len(list(consumer.consume(timeout=5.0))) == 1

    def test_transient_error_does_not_kill_the_stream(self, consumer, caplog):
        # A broker connection dropping is routine over weeks of listening;
        # librdkafka reconnects, so the loop has to survive it.
        from confluent_kafka import KafkaError

        transport = make_kafka_error(KafkaError._TRANSPORT)
        bad = make_message(error=transport)
        good = make_message(b'{"id": "after-reconnect"}')
        consumer._consumer.consume.side_effect = [[bad], [good]]

        with caplog.at_level(logging.WARNING):
            received = list(itertools.islice(consumer.consume(), 1))

        assert received[0].value() == {"id": "after-reconnect"}
        assert "Transient Kafka condition" in caplog.text

    def test_error_flagged_retriable_by_librdkafka_is_survived(self, consumer):
        err = make_kafka_error(-1234, retriable=True)
        consumer._consumer.consume.side_effect = [
            [make_message(error=err)],
            [make_message()],
        ]
        assert len(list(itertools.islice(consumer.consume(), 1))) == 1

    def test_fatal_error_still_raises_in_the_infinite_form(self, consumer):
        # Never silently swallow something the client cannot recover from,
        # such as an ACL that does not cover the topic.
        from confluent_kafka import KafkaError

        err = make_kafka_error(KafkaError.TOPIC_AUTHORIZATION_FAILED)
        consumer._consumer.consume.side_effect = [[make_message(error=err)]]
        with pytest.raises(AstrocolibriKafkaError):
            next(consumer.consume())


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
