"""
tests/test_integration_broker.py

Round-trip integration test against the REAL Astro-COLIBRI production broker.

Unlike every other test in this suite, nothing here is mocked. The test asks the
production API to update a designated test event with `broker_test: true`, then
consumes the resulting message back off the broker's dedicated `test` topic
through the public SDK. That round trip is the only way to exercise what the
mocked tests cannot: the real SASL_SSL handshake, the per-user ACLs, the topic
actually existing, and the live publish path.

Side effects on every run, by design:
  - One update is applied to the designated test event through
    /update_voevent_db_from_triggerid_test, which forces `is_test = True` and
    the `VoEvents_test` collection. The live event collections are untouched.
  - One message is published to the broker's `test` topic. The public
    `astrocolibri.*` streams are never touched.

Required environment. The test SKIPS, and never fails, when any is missing:
  KAFKA_USERNAME / KAFKA_PASSWORD  broker SCRAM credentials for a principal
                                   allowed to READ the `test` topic. That
                                   topic sits outside the `astrocolibri.`
                                   prefix granted to ordinary users, so an
                                   ordinary account cannot read it. Create a
                                   dedicated least-privilege principal with
                                   `create_user.py --test-consumer` rather
                                   than using the `admin` superuser here.
  user_account   / user_password   HTTP basic auth for the API
  ASTROCOLIBRI_TEST_TRIGGER_ID     trigger_id of an event that already exists
                                   in the VoEvents_test collection
  ASTROCOLIBRI_API_URL             optional, defaults to production

Run with:
    pytest tests/ -m integration
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone

import pytest

from astrocolibri import Consumer

requests = pytest.importorskip(
    "requests", reason="requests is required to drive the API round trip"
)

pytestmark = pytest.mark.integration

# Dedicated test topic on the production broker. Deliberately outside the
# `astrocolibri.` namespace so it can never be confused with a public stream.
TEST_TOPIC = "test"

DEFAULT_API_URL = "https://astro-colibri.science"
UPDATE_PATH = "/update_voevent_db_from_triggerid_test"

# The broker publishes via MongoDB change streams, so leave generous headroom
# rather than racing the pipeline.
ASSIGNMENT_TIMEOUT = 60.0
DELIVERY_TIMEOUT = 180.0
POLL_INTERVAL = 1.0


def _env(*names: str) -> str | None:
    """First non-empty value among `names`, tolerating mixed-case CI variables."""
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


@pytest.fixture(scope="module")
def config() -> dict:
    cfg = {
        "kafka_user": _env("KAFKA_USERNAME", "ASTROCOLIBRI_KAFKA_USERNAME"),
        "kafka_password": _env("KAFKA_PASSWORD", "ASTROCOLIBRI_KAFKA_PASSWORD"),
        "api_user": _env("user_account", "USER_ACCOUNT", "ASTROCOLIBRI_API_USER"),
        "api_password": _env(
            "user_password", "USER_PASSWORD", "ASTROCOLIBRI_API_PASSWORD"
        ),
        "trigger_id": _env("ASTROCOLIBRI_TEST_TRIGGER_ID"),
        "api_url": _env("ASTROCOLIBRI_API_URL") or DEFAULT_API_URL,
    }
    missing = [key for key, value in cfg.items() if not value]
    if missing:
        pytest.skip(
            "broker round-trip test needs credentials; missing: "
            + ", ".join(sorted(missing))
        )
    return cfg


def _await_assignment(consumer: Consumer) -> bool:
    """Subscribe and pump the client until partitions are actually assigned.

    Necessary because the consumer starts at `latest`: triggering the update
    before the assignment lands would drop the message we are waiting for.
    """
    assigned = threading.Event()

    def _on_assign(_consumer, _partitions):
        assigned.set()

    consumer.subscribe([TEST_TOPIC], on_assign=_on_assign)

    deadline = time.time() + ASSIGNMENT_TIMEOUT
    while not assigned.is_set() and time.time() < deadline:
        # Draining the generator drives librdkafka, which fires the callback.
        for _ in consumer.consume(timeout=POLL_INTERVAL):
            pass
    return assigned.is_set()


def _trigger_update(cfg: dict, marker: str):
    """Update the designated test event, tagged for the broker's test topic.

    Only last_modified is written. Nothing identifying is touched, so the
    designated event keeps its real source_name and stays recognisable to
    anyone else looking at the test collection, however often this runs.
    """
    payload = {
        "trigger_id": cfg["trigger_id"],
        # Routes this update to the broker's `test` topic instead of the
        # production streams (see VoeventDatabase._build_outbox_document).
        "broker_test": True,
        # Doubles as the change that makes the update real and as this run's
        # marker on a topic that other runs may also be publishing to.
        "last_modified": marker,
    }
    return requests.post(
        cfg["api_url"] + UPDATE_PATH,
        json=payload,
        auth=requests.auth.HTTPBasicAuth(cfg["api_user"], cfg["api_password"]),
        timeout=60,
    )


def _consume_until(consumer: Consumer, marker: str, deadline: float):
    """Return the message carrying `marker`, or (None, None) once time is up."""
    needle = marker.encode()
    while time.time() < deadline:
        for message in consumer.consume(timeout=POLL_INTERVAL):
            raw = message.value()
            if raw is None or needle not in raw:
                # Traffic from another run on the shared test topic: not ours.
                continue
            return message, json.loads(raw.decode("utf-8"))
    return None, None


def test_api_update_arrives_on_the_broker_test_topic(config):
    # Second resolution is enough to be unique: CI serialises these runs
    # through a resource_group, and the whole test lasts a few minutes.
    marker = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    consumer = Consumer(
        username=config["kafka_user"],
        password=config["kafka_password"],
        # A throwaway group per run, so the test never competes with a real
        # consumer for partitions and never resumes a stale offset.
        group_id=f"sdk-itest-{uuid.uuid4().hex[:8]}",
        start_at="latest",
    )

    try:
        assert _await_assignment(consumer), (
            f"no partition assigned on '{TEST_TOPIC}' within "
            f"{ASSIGNMENT_TIMEOUT:.0f}s: check this account's broker ACLs"
        )

        response = _trigger_update(config, marker)
        assert response.status_code in (200, 201), (
            f"update failed: HTTP {response.status_code} {response.text[:300]}"
        )

        message, payload = _consume_until(
            consumer, marker, time.time() + DELIVERY_TIMEOUT
        )

        assert message is not None, (
            f"the API accepted the update but it never reached the "
            f"'{TEST_TOPIC}' topic within {DELIVERY_TIMEOUT:.0f}s"
        )
        assert message.topic() == TEST_TOPIC
        assert payload.get("trigger_id") == config["trigger_id"]
        assert payload.get("last_modified") == marker
    finally:
        consumer.close()

