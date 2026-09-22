"""
astrocolibri/alert.py

Decoded Astro-Colibri alert.

Kafka carries raw bytes, so a `confluent_kafka.Message` hands back
`b'{"id": "..."}'` rather than anything you can work with. `Alert` wraps
that message and gives you the payload already decoded: a `dict` for the
JSON topics, an XML `str` for the VOEvent topics.

The accessors keep the `confluent_kafka.Message` method names
(`value()`, `key()`, `topic()`, ...), so existing code keeps working — it
simply stops seeing bytes.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple, Union

from confluent_kafka import Message

from .exceptions import AstrocolibriDecodeError

#: Payload is Astro-Colibri JSON; `value()` returns the parsed object.
FORMAT_JSON = "json"

#: Payload is a VOEvent XML document; `value()` returns it as `str`.
FORMAT_VOEVENT = "voevent"

#: Payload could not be attributed to either format; `value()` returns `str`.
FORMAT_UNKNOWN = "unknown"


def _format_for_topic(topic: Optional[str]) -> Optional[str]:
    """Announced format of `topic`, from the Astro-Colibri naming convention."""
    if not topic:
        return None
    if topic.endswith(".VOEvent"):
        return FORMAT_VOEVENT
    if topic.endswith(".JSON"):
        return FORMAT_JSON
    # `heartbeat` and the internal `test` topic sit outside the
    # `<stream>.<format>` convention and are JSON.
    if topic in ("astrocolibri.heartbeat", "heartbeat", "test"):
        return FORMAT_JSON
    return None


def _sniff_format(payload: bytes) -> str:
    """Fallback format detection for a topic that does not announce one."""
    head = payload.lstrip(b"\xef\xbb\xbf \t\r\n")[:1]
    if head in (b"{", b"["):
        return FORMAT_JSON
    if head == b"<":
        return FORMAT_VOEVENT
    return FORMAT_UNKNOWN


class Alert:
    """
    One alert received from the Astro-Colibri broker, payload decoded.

    Wraps a :class:`confluent_kafka.Message`. Decoding is lazy and cached:
    it happens on the first call to :meth:`value`, :meth:`text` or
    :meth:`json`, so a malformed payload raises where you read it rather
    than killing the consume loop.

    Example::

        for alert in consumer.consume():
            data = alert.value()        # dict on a .JSON topic
            print(data["id"], data["ra"], data["dec"])

        for alert in consumer.consume():
            xml = alert.value()         # str on a .VOEvent topic
            print(xml)

    The original message stays reachable through :attr:`message`, and the
    payload exactly as published through :attr:`raw`.
    """

    __slots__ = ("_message", "_format", "_text", "_value", "_decoded")

    def __init__(self, message: Message) -> None:
        self._message = message
        self._format: Optional[str] = None
        self._text: Optional[str] = None
        self._value: Any = None
        self._decoded = False

    # ── confluent_kafka.Message-compatible accessors ─────────────────────────

    def value(self) -> Union[Dict[str, Any], list, str, None]:
        """
        The alert payload, decoded.

        Returns:
            - ``dict`` (or ``list``) on a JSON topic — the parsed payload
            - ``str`` on a VOEvent topic — the XML document
            - ``None`` if the message carries no payload

        Raises:
            AstrocolibriDecodeError: If the payload is not valid UTF-8, or
                if a JSON topic carries something that is not valid JSON.
        """
        if self._decoded:
            return self._value

        payload = self._message.value()
        if payload is None:
            self._value = None
            self._decoded = True
            return None

        text = self.text()
        if self.format == FORMAT_JSON:
            try:
                self._value = json.loads(text)
            except ValueError as exc:
                raise AstrocolibriDecodeError(
                    f"{self._where()}: payload is not valid JSON: {exc}"
                ) from exc
        else:
            self._value = text

        self._decoded = True
        return self._value

    def key(self) -> Optional[str]:
        """
        The message key, decoded — the Astro-Colibri event id.

        Every update of one event carries the same key, which is what keeps
        those updates on one partition and therefore in order.
        """
        key = self._message.key()
        if key is None:
            return None
        if isinstance(key, str):
            return key
        return key.decode("utf-8", errors="replace")

    def headers(self) -> Dict[str, str]:
        """
        Kafka headers as a decoded ``dict``.

        The broker attaches ``event_id``, ``dedupe_key``, ``event_version``,
        ``update_type``, ``important`` and ``changed_fields`` (a JSON list)
        to every alert. ``dedupe_key`` is the one to key on if you need
        consumer-side idempotency.
        """
        raw_headers = self._message.headers()
        if not raw_headers:
            return {}
        decoded: Dict[str, str] = {}
        for name, value in raw_headers:
            if isinstance(name, bytes):
                name = name.decode("utf-8", errors="replace")
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="replace")
            decoded[name] = "" if value is None else value
        return decoded

    def topic(self) -> Optional[str]:
        """Topic the alert was received from."""
        return self._message.topic()

    def partition(self) -> Optional[int]:
        """Kafka partition the alert was read from."""
        return self._message.partition()

    def offset(self) -> Optional[int]:
        """Kafka offset of the alert within its partition."""
        return self._message.offset()

    def timestamp(self) -> Tuple[int, int]:
        """``(timestamp_type, timestamp_ms)`` as reported by Kafka."""
        return self._message.timestamp()

    def error(self) -> None:
        """Always ``None``: erroring messages never reach you as an Alert."""
        return None

    # ── Decoded views ────────────────────────────────────────────────────────

    def text(self) -> str:
        """
        The payload as text, whatever its format.

        Useful when you want the JSON exactly as published rather than the
        parsed object, or to hand a VOEvent to an XML parser.

        Raises:
            AstrocolibriDecodeError: If the payload is not valid UTF-8.
        """
        if self._text is not None:
            return self._text

        payload = self._message.value()
        if payload is None:
            self._text = ""
            return self._text
        if isinstance(payload, str):
            self._text = payload
            return self._text

        try:
            # utf-8-sig is plain UTF-8 plus tolerance for a leading BOM,
            # which json.loads() rejects outright.
            self._text = payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise AstrocolibriDecodeError(
                f"{self._where()}: payload is not valid UTF-8: {exc}"
            ) from exc
        return self._text

    def json(self) -> Any:
        """
        The payload parsed as JSON, whatever the topic announces.

        Raises:
            AstrocolibriDecodeError: If the payload is not valid UTF-8 or
                not valid JSON.
        """
        text = self.text()
        try:
            return json.loads(text)
        except ValueError as exc:
            raise AstrocolibriDecodeError(
                f"{self._where()}: payload is not valid JSON: {exc}"
            ) from exc

    @property
    def format(self) -> str:
        """
        ``"json"``, ``"voevent"`` or ``"unknown"``.

        Taken from the topic name, falling back to the first byte of the
        payload for topics outside the ``<stream>.<format>`` convention.
        """
        if self._format is None:
            announced = _format_for_topic(self._message.topic())
            if announced is not None:
                self._format = announced
            else:
                payload = self._message.value()
                if payload is None:
                    self._format = FORMAT_UNKNOWN
                elif isinstance(payload, str):
                    self._format = _sniff_format(payload.encode("utf-8", "replace"))
                else:
                    self._format = _sniff_format(payload)
        return self._format

    @property
    def raw(self) -> Optional[bytes]:
        """The payload exactly as published, undecoded."""
        return self._message.value()

    @property
    def message(self) -> Message:
        """The underlying :class:`confluent_kafka.Message`."""
        return self._message

    # ── Introspection ────────────────────────────────────────────────────────

    def _where(self) -> str:
        return (
            f"{self._message.topic()}"
            f"[partition={self._message.partition()}, "
            f"offset={self._message.offset()}]"
        )

    def __len__(self) -> int:
        payload = self._message.value()
        return 0 if payload is None else len(payload)

    def __repr__(self) -> str:
        return (
            f"<Alert {self._message.topic()}"
            f"[{self._message.partition()}]@{self._message.offset()} "
            f"format={self.format} bytes={len(self)}>"
        )
