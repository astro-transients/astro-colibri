"""
astrocolibri/filtering.py

Filter Astro-COLIBRI events and broker alerts the way the app and the API do.

An :class:`EventFilter` holds an Astro-COLIBRI filter: the JSON structure the
app exports ("Astro-COLIBRI_filters.json"), the API accepts as ``filter`` in
its searches, and the app saves for your account. It is evaluated by the
API's own filter engine, copied into this package, so an event passes here
exactly when ``/latest_transients`` would return it.

Example::

    from astrocolibri import Consumer, EventFilter

    my_filter = EventFilter.from_saved_filters()      # reads ASTROCOLIBRI_UID

    with Consumer(username="...", password="...") as consumer:
        consumer.subscribe(["astrocolibri.all.JSON"])
        for alert in consumer.consume(event_filter=my_filter):
            event = alert.event()
            print(event["trigger_id"], event["type"])
"""

from __future__ import annotations

import copy
import json
import logging
import os
from typing import Any, Dict, Iterable, Iterator, Mapping, Optional, TypeVar, Union

from ._filters.filter import BaseClassExceptionFilterParsing, BaseFilter
from .alert import Alert
from .exceptions import AstrocolibriConfigError, AstrocolibriDecodeError
from .voevent import VOEvent

logger = logging.getLogger(__name__)

#: Topics that carry broker status rather than events; never filtered out.
_STATUS_TOPICS = frozenset({"astrocolibri.heartbeat", "heartbeat"})

T = TypeVar("T")


class EventFilter:
    """
    An Astro-COLIBRI event filter.

    Build one from any of the three places filters come from:

    - :meth:`from_saved_filters`: the filters saved in the Astro-COLIBRI app
      for your account, fetched with your user ID;
    - :meth:`from_file`: a filter file, such as the
      ``Astro-COLIBRI_filters.json`` the app exports;
    - ``EventFilter(spec)``: a filter dictionary, in the format the API
      documents at https://astro-colibri.science/apidoc.

    Then test events with :meth:`matches`, or keep the matching ones from
    any stream with :meth:`filter`. ``Consumer.consume(event_filter=...)``
    applies it to the broker stream directly.

    Events in Astro-COLIBRI's JSON structure, :class:`~astrocolibri.Alert`
    objects from either the JSON or the VOEvent topics, and parsed
    :class:`~astrocolibri.VOEvent` documents are all accepted: VOEvents are
    converted back to the JSON structure first
    (:meth:`VOEvent.to_colibri_event`), so one filter gives the same answer
    on both kinds of topic.

    Filters about time since a detection ("last detection within 7 days")
    are measured from the moment you evaluate them. Replaying old alerts
    (``start_at="earliest"``) judges them against today, not against the day
    they were published.

    Example::

        my_filter = EventFilter({
            "type": "FieldSpecification",
            "field": "type",
            "operation": "==",
            "typeField": "string",
            "value": "grb",
        })
        my_filter.matches({"type": "GRB", "trigger_id": "GRB 190829A"})   # True
    """

    def __init__(self, spec: Mapping[str, Any]) -> None:
        """
        Create a filter from a filter dictionary.

        Args:
            spec:
                The filter. A search request body or a ``/saved_filters``
                response, which hold it under ``"filter"``, is accepted too.

        Raises:
            AstrocolibriConfigError: If ``spec`` is not a valid filter. The
                message is the API's own description of the problem.
        """
        if not isinstance(spec, Mapping):
            raise AstrocolibriConfigError(
                f"A filter must be a dictionary, got {type(spec).__name__}."
            )
        if "type" not in spec and isinstance(spec.get("filter"), Mapping):
            spec = spec["filter"]
        if not spec:
            raise AstrocolibriConfigError(
                'The filter is empty. To keep every event, use {"type": "TrueSpecification"}.'
            )

        self._spec: Dict[str, Any] = copy.deepcopy(dict(spec))
        try:
            # The engine fills in defaults in the dictionary it reads; give it
            # a copy so neither the caller's filter nor ours changes.
            self._engine = BaseFilter.create_from_dict(copy.deepcopy(self._spec))
        except BaseClassExceptionFilterParsing as exc:
            raise AstrocolibriConfigError(
                f"Invalid filter: {exc.generate_error_message_user()}."
            ) from None
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise AstrocolibriConfigError(f"Invalid filter: {exc!r}.") from None

    # ── Construction ─────────────────────────────────────────────────────────

    @classmethod
    def from_file(cls, path: Union[str, "os.PathLike[str]"]) -> "EventFilter":
        """
        Load a filter from a JSON file.

        Reads the ``Astro-COLIBRI_filters.json`` that the "Download Filters"
        button in the app's filter menu saves, or any file holding a filter
        dictionary.

        Raises:
            OSError: If the file cannot be read.
            AstrocolibriConfigError: If it does not hold a valid filter.

        Example::

            my_filter = EventFilter.from_file("Astro-COLIBRI_filters.json")
        """
        with open(path, encoding="utf-8-sig") as handle:
            try:
                spec = json.load(handle)
            except ValueError as exc:
                raise AstrocolibriConfigError(
                    f"{os.fspath(path)} is not a JSON file: {exc}."
                ) from None
        return cls(spec)

    @classmethod
    def from_saved_filters(
        cls,
        uid: Optional[str] = None,
        *,
        client: Optional[Any] = None,
        timeout: Optional[float] = None,
    ) -> "EventFilter":
        """
        The filters saved in the Astro-COLIBRI app for your account.

        Fetched once, now: filters you change in the app later apply after
        you call this again. Counts once against your daily API quota.

        Args:
            uid:
                Your Astro-COLIBRI user ID, from
                https://astro-colibri.com/account. Omitted: read from the
                ``ASTROCOLIBRI_UID`` environment variable.
            client:
                A :class:`~astrocolibri.Client` to fetch them with, instead
                of a temporary one. Cannot be combined with ``uid``.
            timeout:
                Seconds before the request is abandoned.

        Raises:
            AstrocolibriAuthError: If no user ID is configured, or the API
                does not accept it.
            AstrocolibriNotFoundError: If no filters were ever saved in the
                app for this account.
            AstrocolibriConfigError: If both ``uid`` and ``client`` are given.
            AstrocolibriRateLimitError, AstrocolibriAPIError,
            AstrocolibriTransportError: As for any API request.

        Example::

            my_filter = EventFilter.from_saved_filters()     # ASTROCOLIBRI_UID
        """
        if client is not None:
            if uid is not None:
                raise AstrocolibriConfigError(
                    "Pass either uid or client to from_saved_filters(), not both: "
                    "the client already has its user ID."
                )
            return cls(client.get_saved_filters(timeout=timeout))

        # Imported here: the Client is only needed for this way of building one.
        from .client import Client

        with Client(uid=uid) as own_client:
            return cls(own_client.get_saved_filters(timeout=timeout))

    # ── Evaluation ───────────────────────────────────────────────────────────

    def matches(self, event: Union[Mapping[str, Any], Alert, VOEvent]) -> bool:
        """
        Whether ``event`` passes the filter.

        Args:
            event:
                An event in Astro-COLIBRI's JSON structure (a JSON-topic
                payload, or an event returned by the API), an
                :class:`~astrocolibri.Alert` from either kind of topic, or a
                parsed Astro-COLIBRI :class:`~astrocolibri.VOEvent`.

        Returns:
            ``True`` if the event passes. A field the filter compares but
            the event lacks, or holds in an unexpected form, does not pass,
            as in the API.

        Raises:
            AstrocolibriDecodeError: If an alert's payload cannot be decoded
                into an event, or a VOEvent was not written by Astro-COLIBRI.
            AstrocolibriConfigError: If ``event`` is none of the above.
        """
        if isinstance(event, Alert):
            event = event.event()
        elif isinstance(event, VOEvent):
            event = event.to_colibri_event()
        elif not isinstance(event, Mapping):
            raise AstrocolibriConfigError(
                f"matches() takes an event dictionary, an Alert or a VOEvent, "
                f"got {type(event).__name__}."
            )

        try:
            return bool(self._engine.apply_filter(event))
        except (TypeError, ValueError, KeyError, IndexError, AttributeError) as exc:
            # A value of the wrong type for its filter (text where a number is
            # compared, say): the API rejects such an event, and so do we.
            logger.debug(
                "Event does not pass the filter, it cannot be compared: %r", exc
            )
            return False

    def filter(self, items: Iterable[T]) -> Iterator[T]:
        """
        The items of ``items`` that pass the filter, lazily and in order.

        Takes anything :meth:`matches` takes, and the raw
        :class:`confluent_kafka.Message` objects of a ``decode=False``
        consumer. Items come out exactly as they went in.

        Two kinds of alert are passed on without being filtered:

        - heartbeats, which report on the broker rather than an event;
        - alerts whose payload cannot be decoded. They are logged as a
          warning and raise where you read them, as any alert does, rather
          than disappearing unseen.

        Example::

            for alert in my_filter.filter(consumer.consume()):
                handle(alert.event())

            results = client.latest_transients(start=start, end=end)
            grbs = list(grb_filter.filter(results["voevents"]))
        """
        for item in items:
            candidate: Any = item
            if not isinstance(item, (Mapping, Alert, VOEvent)) and hasattr(
                item, "topic"
            ):
                candidate = Alert(item)

            if isinstance(candidate, Alert) and candidate.topic() in _STATUS_TOPICS:
                yield item
                continue

            try:
                keep = self.matches(candidate)
            except AstrocolibriDecodeError as exc:
                logger.warning(
                    "Passing on an alert that could not be filtered: %s", exc
                )
                keep = True
            if keep:
                yield item

    # ── Introspection ────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """
        The filter dictionary, as given.

        Pass it as ``event_filter`` to ``Client.latest_transients()`` or
        ``Client.cone_search()`` to search the archive with the same filter,
        or ``json.dump`` it to keep it.
        """
        return copy.deepcopy(self._spec)

    def __repr__(self) -> str:
        return f"<EventFilter {self._spec.get('type', '?')}>"


__all__ = ["EventFilter"]
