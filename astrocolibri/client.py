"""
astrocolibri/client.py

Astro-Colibri API client.

A synchronous, read-only wrapper around the public Astro-COLIBRI API at
https://astro-colibri.science. It looks up events and sources, and searches
for transients by time window or around a position. Results are the API's
own JSON as plain Python objects: unknown fields are preserved and nothing
is reshaped.

The client never retries a request on its own. A search can consume your
daily quota or start expensive processing on the server, so repeating one
is always your decision.
"""

from __future__ import annotations

import math
import numbers
import os
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union
from urllib.parse import quote, quote_plus

import requests

from ._parsing import (
    Angle,
    TimeLike,
    parse_dec,
    parse_ra,
    parse_radius,
    to_api_time_range,
)
from ._version import __version__
from .exceptions import (
    AstrocolibriAPIError,
    AstrocolibriAuthError,
    AstrocolibriConfigError,
    AstrocolibriNotFoundError,
    AstrocolibriRateLimitError,
    AstrocolibriTransportError,
)

#: Environment variable holding the user ID when ``uid`` is not passed.
UID_ENV_VAR = "ASTROCOLIBRI_UID"

#: Heavy event fields the API leaves out unless they are requested.
OPTIONAL_PARAMETERS = ("gw_contours", "archive")

# Where users find their user ID; linked from every UID-related error.
_ACCOUNT_URL = "https://astro-colibri.com/account"

# Sent when no filter is given: every event the account may access. Sending
# it explicitly, instead of leaving the filter out, keeps the request
# cacheable on the server and independent of any filters saved in the app.
_MATCH_ALL_FILTER = {
    "type": "TrueSpecification",
    "isActivated": True,
    "defaultState": False,
}

_RETURN_FORMATS = ("json", "url", "votable")
_MISSING_POLICIES = ("raise", "skip")
_MAX_CONTOUR_MARGIN = 20.0

# /source_details answers an unknown name with these values, not a 404.
_SOURCE_SENTINEL = -1000

# /event marks an identifier that matched nothing with this error text.
_EVENT_NOT_FOUND = "event not found"
_EVENT_FAILURE_KEYS = frozenset({"trigger_id", "error", "message", "internal_error"})

_RESET_TIME = re.compile(r"Renewal at\s+(.+?)\s*$")
_ENVELOPE_KEYS = frozenset({"message", "status_code", "error"})
_SNIPPET_LENGTH = 200
_NOT_JSON = object()

SearchResult = Union[Dict[str, Any], str]


class Client:
    """
    Astro-Colibri API client.

    Looks up events and sources, and searches for transients by time window
    or around a sky position, through the public Astro-COLIBRI API.

    Event and source lookups are free. The two searches,
    :meth:`latest_transients` and :meth:`cone_search`, need your
    Astro-COLIBRI user ID and count against a daily per-account quota (100
    requests at the time of writing). An identical search repeated within
    the same half hour is normally answered from the API's cache and does not
    count again.

    Get your user ID from https://astro-colibri.com/account, then either
    export it::

        export ASTROCOLIBRI_UID="your-user-id"

    or pass it to the constructor. The explicit argument wins.

    Quick start::

        from astrocolibri import Client

        with Client() as client:              # reads ASTROCOLIBRI_UID
            event = client.get_event("GRB 190829A")
            print(event["trigger_id"], event["ra"], event["dec"])

            results = client.latest_transients(
                start="2026-09-01T00:00:00Z",
                end="2026-09-02T00:00:00Z",
            )
            for transient in results["voevents"]:
                print(transient.get("source_name"), transient.get("type"))

    The user ID lives only in memory: it is never written to disk, never
    shown by ``repr()``, and replaced by ``<uid>`` in every error message.

    A ``Client`` holds a :class:`requests.Session`, which is not thread-safe.
    Use one ``Client`` per thread.
    """

    #: Base URL of the public Astro-COLIBRI API.
    API_URL: str = "https://astro-colibri.science"

    #: Seconds a request may take before it is abandoned, unless overridden.
    DEFAULT_TIMEOUT: float = 30.0

    def __init__(
        self,
        uid: Optional[str] = None,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        session: Optional[requests.Session] = None,
    ) -> None:
        """
        Create an API client.

        Args:
            uid:
                Your Astro-COLIBRI user ID, from
                https://astro-colibri.com/account. Surrounding whitespace is
                removed.

                - Omitted (default): read from the ``ASTROCOLIBRI_UID``
                  environment variable when the client is created. If the
                  variable is unset or empty the client has no user ID,
                  which is enough for event and source lookups.
                - Given: takes precedence over the environment variable. An
                  empty string is rejected, since it is almost always a
                  configuration mistake.
            timeout:
                Seconds a request may take before it is abandoned. Every
                method also accepts its own ``timeout``.
            session:
                A :class:`requests.Session` to send requests through, for
                example one configured with a proxy or a custom CA bundle.
                The client sets its own headers per request and leaves the
                session's settings untouched. A session you pass in is not
                closed by :meth:`close`: it belongs to you.

        Raises:
            AstrocolibriConfigError: If ``uid`` is given but empty or not a
                string, or ``timeout`` is not a positive number.

        Example::

            client = Client()                 # reads ASTROCOLIBRI_UID
            client = Client(uid=my_uid)       # explicit, wins over the variable
        """
        self._uid = _resolve_uid(uid)
        self._timeout = _positive_timeout(timeout)
        self._owns_session = session is None
        self._session = requests.Session() if session is None else session

    @property
    def has_uid(self) -> bool:
        """Whether a user ID is configured, without revealing it."""
        return self._uid is not None

    # ── Events ───────────────────────────────────────────────────────────────

    def get_event(
        self,
        identifier: str,
        *,
        optional_parameters: Union[str, Sequence[str], None] = (),
        simbad: bool = False,
        include_custom_events: bool = False,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve one event by trigger ID or name.

        The API matches ``identifier`` against trigger IDs, source names and
        discoverer designations, and tolerates spacing differences
        (``"GRB190829A"`` finds ``"GRB 190829A"``). When several events share
        a name, only one of them is returned, and not necessarily the
        best-localized one. To see every event recorded under a name, list
        them with :meth:`resolve_source` and fetch the one you want by its
        ``trigger_id``.

        Event lookups do not count against your API quota.

        Args:
            identifier:
                A trigger ID, source name or discoverer designation.
            optional_parameters:
                Heavy fields to include, ``"gw_contours"`` and/or
                ``"archive"``. Fields you do not request come back as
                ``{"Parameter": "Not requested"}``.
            simbad:
                Build the event from SIMBAD instead of the Astro-COLIBRI
                database. Intended for sources that
                :meth:`get_source_summary` reports with
                ``origin == "SIMBAD"``.
            include_custom_events:
                Also search the events you created yourself in the
                Astro-COLIBRI app. Needs a user ID, which is then sent with
                the request.
            timeout:
                Seconds before the request is abandoned. Defaults to the
                client's timeout.

        Returns:
            The event as a ``dict``, with every field the API returns.

        Raises:
            AstrocolibriNotFoundError: If no event matches ``identifier``.
            AstrocolibriConfigError: If an argument is invalid. Nothing is
                sent in that case.
            AstrocolibriAuthError: If ``include_custom_events`` is set and no
                user ID is configured.
            AstrocolibriAPIError: If the API fails to process the request.
            AstrocolibriTransportError: If the API cannot be reached.

        Example::

            event = client.get_event("GRB 190829A")
            print(event["trigger_id"], event["ra"], event["dec"], event["err"])

            event = client.get_event("GRB 190829A", optional_parameters=["archive"])
        """
        events = self._fetch_events(
            [identifier],
            optional_parameters=optional_parameters,
            simbad=simbad,
            include_custom_events=include_custom_events,
            missing="raise",
            timeout=timeout,
        )
        return events[0]

    def get_events(
        self,
        identifiers: Sequence[str],
        *,
        optional_parameters: Union[str, Sequence[str], None] = (),
        simbad: bool = False,
        include_custom_events: bool = False,
        missing: str = "raise",
        timeout: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve several events in a single request.

        Each identifier is resolved exactly as in :meth:`get_event`, and the
        events come back in the order the identifiers were given.

        Event lookups do not count against your API quota.

        Args:
            identifiers:
                Trigger IDs, source names or discoverer designations.
            missing:
                What to do when some identifiers match no event.

                - ``"raise"`` (default): raise
                  :exc:`AstrocolibriNotFoundError` naming them.
                - ``"skip"``: return only the events that were found.
            optional_parameters, simbad, include_custom_events, timeout:
                As in :meth:`get_event`.

        Returns:
            A list of event dicts.

        Raises:
            AstrocolibriNotFoundError: If ``missing="raise"`` and an
                identifier matches no event.
            AstrocolibriConfigError: If an argument is invalid. Nothing is
                sent in that case.
            AstrocolibriAuthError: If ``include_custom_events`` is set and no
                user ID is configured.
            AstrocolibriAPIError: If the API fails to process the request, or
                fails on one of the identifiers while ``missing="raise"``.
            AstrocolibriTransportError: If the API cannot be reached.

        Example::

            events = client.get_events(
                ["GRB 190829A", "922968", "not-an-event"],
                missing="skip",
            )
        """
        return self._fetch_events(
            identifiers,
            optional_parameters=optional_parameters,
            simbad=simbad,
            include_custom_events=include_custom_events,
            missing=missing,
            timeout=timeout,
        )

    def get_event_voevent(
        self,
        identifier: str,
        *,
        optional_parameters: Union[str, Sequence[str], None] = (),
        timeout: Optional[float] = None,
    ) -> str:
        """
        Retrieve one event as a VOEvent XML document.

        The event is resolved exactly as in :meth:`get_event`.

        Args:
            identifier:
                A trigger ID, source name or discoverer designation.
            optional_parameters, timeout:
                As in :meth:`get_event`.

        Returns:
            The VOEvent document as ``str``.

        Raises:
            AstrocolibriNotFoundError: If no event matches ``identifier``.
            AstrocolibriConfigError: If an argument is invalid.
            AstrocolibriAPIError: If the API fails to process the request.
            AstrocolibriTransportError: If the API cannot be reached.

        Example::

            xml = client.get_event_voevent("GRB 190829A")
            with open("GRB190829A.xml", "w") as f:
                f.write(xml)
        """
        name = _required_text(identifier, "identifier")
        params: List[Tuple[str, str]] = [("trigger_id", name)]
        params += [
            ("optional_parameters", key)
            for key in _optional_parameters(optional_parameters)
        ]
        return self._request_text(
            "GET",
            "/get_event_as_voevent",
            params=params,
            timeout=timeout,
            not_found=f"No event found for {name!r}.",
        )

    # ── Sources ──────────────────────────────────────────────────────────────

    def resolve_source(
        self, name: str, *, timeout: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        List every event recorded under a source name.

        One source often has several localizations, for example a GRB seen
        by both Swift/XRT and Fermi/GBM. This returns a short summary of
        each, best-localized first, so you can choose one and fetch it in
        full with :meth:`get_event`.

        Each summary has ``trigger_id``, ``ra``, ``dec``, ``err`` (the
        localization uncertainty, in degrees) and ``timestamp`` (milliseconds
        since the Unix epoch), plus ``observatory`` and ``instrument`` when
        they are known.

        Only transient events are searched. A catalog source (TeVCat, 4FGL,
        X-ray binaries), a bright star or an object known only to SIMBAD
        gives an empty list: use :meth:`get_source_summary` for those.

        Source lookups do not count against your API quota.

        Args:
            name:
                The source name, e.g. ``"GRB 190829A"``.
            timeout:
                Seconds before the request is abandoned. Defaults to the
                client's timeout.

        Returns:
            Event summaries sorted by ascending ``err``. An empty list when
            no transient event is recorded under ``name``.

        Raises:
            AstrocolibriConfigError: If ``name`` is empty.
            AstrocolibriAPIError: If the API fails to process the request.
            AstrocolibriTransportError: If the API cannot be reached.

        Example::

            summaries = client.resolve_source("GRB 190829A")
            for summary in summaries:
                print(summary["trigger_id"], summary.get("observatory"), summary["err"])

            best = client.get_event(summaries[0]["trigger_id"])
        """
        source = _required_text(name, "name")
        payload = self._request_json(
            "GET",
            "/source_details",
            params={"name": source, "all_events": "true"},
            timeout=timeout,
        )
        events = payload.get("events") if isinstance(payload, dict) else None
        if not isinstance(events, list):
            raise self._malformed("/source_details", payload)
        return events

    def get_source_summary(
        self, name: str, *, timeout: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Position of a source, from any catalog Astro-COLIBRI knows.

        Unlike :meth:`resolve_source`, this also covers catalog sources
        (TeVCat, 4FGL, X-ray binaries), bright stars and, as a last resort,
        SIMBAD. It returns a single summary: for a source with several
        localizations, the best-localized one.

        The summary includes the position (``ra``, ``dec``) and, depending
        on where the source was found, fields such as ``err``,
        ``trigger_id``, ``timestamp`` (milliseconds since the Unix epoch)
        and ``origin`` (``"Astro-COLIBRI"`` or ``"SIMBAD"``). For a SIMBAD
        source, ``get_event(name, simbad=True)`` builds a full event.

        A SIMBAD lookup can take much longer than the default timeout. When
        you expect one, pass a generous ``timeout``, e.g. ``timeout=300``.

        Source lookups do not count against your API quota.

        Args:
            name:
                The source name, e.g. ``"Crab"`` or ``"GRB 190829A"``.
            timeout:
                Seconds before the request is abandoned. Defaults to the
                client's timeout.

        Returns:
            The summary as a ``dict``, or ``None`` if no catalog knows
            ``name``.

        Raises:
            AstrocolibriConfigError: If ``name`` is empty.
            AstrocolibriAPIError: If the API fails to process the request.
            AstrocolibriTransportError: If the API cannot be reached.

        Example::

            summary = client.get_source_summary("Crab", timeout=300)
            if summary is None:
                print("unknown source")
            else:
                print(summary["ra"], summary["dec"], summary.get("origin"))
        """
        source = _required_text(name, "name")
        payload = self._request_json(
            "GET",
            "/source_details",
            params={"name": source},
            timeout=timeout,
        )
        if not isinstance(payload, dict):
            raise self._malformed("/source_details", payload)
        if (
            payload.get("ra") == _SOURCE_SENTINEL
            and payload.get("dec") == _SOURCE_SENTINEL
        ):
            return None
        return payload

    # ── Searches ─────────────────────────────────────────────────────────────

    def latest_transients(
        self,
        *,
        start: TimeLike,
        end: TimeLike,
        event_filter: Optional[Dict[str, Any]] = None,
        use_saved_filters: bool = False,
        optional_parameters: Union[str, Sequence[str], None] = (),
        include_watchlist: bool = False,
        return_format: str = "json",
        timeout: Optional[float] = None,
    ) -> SearchResult:
        """
        Search for transients within a time window.

        Needs a user ID and counts against your daily API quota. Fixed
        window bounds make repeated calls cacheable: a window ending at
        ``datetime.now()`` is a new search every time.

        By default every event your account may access is returned. Narrow
        the search with ``event_filter``, an API filter dictionary as
        documented at https://astro-colibri.science/apidoc, or apply the
        filters saved in your Astro-COLIBRI app with
        ``use_saved_filters=True``.

        Args:
            start, end:
                The search window, as timezone-aware datetimes or ISO 8601
                strings with a timezone (``"2026-09-01T00:00:00Z"``). Times
                without a timezone are rejected rather than guessed.
            event_filter:
                An API filter dictionary. Cannot be combined with
                ``use_saved_filters``.
            use_saved_filters:
                Apply the latest filters saved in the Astro-COLIBRI app for
                your account; the API fails if none were saved. Such a search
                is never answered from the API's cache, so every call counts
                against your quota.
            optional_parameters:
                Heavy event fields to include, ``"gw_contours"`` and/or
                ``"archive"``.
            include_watchlist:
                Also return the events on your watchlist, whether or not they
                match the search, under a separate ``"watchlist"`` key.
            return_format:
                - ``"json"`` (default): the results as a ``dict``.
                - ``"votable"``: a VOTable XML document embedding one VOEvent
                  per event, as ``str``.
                - ``"url"``: a link to the results stored as a JSON file, as
                  ``str``. Watchlist events are not included in that file.
            timeout:
                Seconds before the request is abandoned. Defaults to the
                client's timeout.

        Returns:
            With ``return_format="json"``, a dict whose ``"voevents"`` list
            holds the transient events, plus a ``"watchlist"`` list when
            ``include_watchlist`` is set. Unknown groups and fields are
            preserved.

        Raises:
            AstrocolibriAuthError: If no user ID is configured, or the API
                does not accept it.
            AstrocolibriRateLimitError: If the daily quota is exhausted.
            AstrocolibriConfigError: If an argument is invalid. Nothing is
                sent and no quota is used.
            AstrocolibriAPIError: If the API rejects the request, for
                example because of an invalid filter.
            AstrocolibriTransportError: If the API cannot be reached.

        Example::

            results = client.latest_transients(
                start="2026-09-01T00:00:00Z",
                end="2026-09-02T00:00:00Z",
            )
            for event in results["voevents"]:
                print(event.get("source_name"), event.get("type"), event.get("time"))
        """
        uid = self._require_uid("latest_transients()")
        return self._search(
            "/latest_transients",
            uid=uid,
            start=start,
            end=end,
            event_filter=event_filter,
            use_saved_filters=use_saved_filters,
            optional_parameters=optional_parameters,
            include_watchlist=include_watchlist,
            return_format=return_format,
            timeout=timeout,
        )

    def cone_search(
        self,
        *,
        ra: Angle,
        dec: Angle,
        radius: Angle,
        start: TimeLike,
        end: TimeLike,
        event_filter: Optional[Dict[str, Any]] = None,
        use_saved_filters: bool = False,
        contour_trigger_id: Optional[str] = None,
        contour_margin: Optional[float] = None,
        optional_parameters: Union[str, Sequence[str], None] = (),
        include_watchlist: bool = False,
        return_format: str = "json",
        timeout: Optional[float] = None,
    ) -> SearchResult:
        """
        Search for transients around a sky position within a time window.

        Needs a user ID and counts against your daily API quota.

        Angles accept decimal degrees or sexagesimal strings. The unit is
        read from the notation, never guessed from the size of the number:

        - numbers and plain numeric strings are degrees: ``83.63``, ``"83.63"``
        - ``h``/``m``/``s`` is an hour angle: ``"05h34m31.94s"``
        - ``d``/``m``/``s`` or ``°``/``′``/``″`` is degrees: ``"+22d00m52.2s"``
        - colon notation is hours for ``ra`` and degrees for ``dec`` and
          ``radius``: ``ra="05:34:31.94"``, ``dec="+22:00:52.2"``

        Args:
            ra:
                Right ascension of the search center, within [0, 360).
            dec:
                Declination of the search center, within [-90, 90].
            radius:
                Search radius, within (0, 180]. ``"30′"`` is 0.5°. The API
                sets no upper limit of its own, and a wide cone is an
                expensive query.
            start, end:
                The search window, as in :meth:`latest_transients`.
            contour_trigger_id:
                Search inside this event's 90% localization contour instead
                of the circle, for events with extended localizations such as
                gravitational waves, Fermi/GBM and IPN bursts, IceCube
                neutrinos or MAXI transients. If the event has no stored
                contour, the API falls back to the circle.
                ``"search_region"`` in the result says which was used.
            contour_margin:
                Degrees, within [0, 20], by which to widen the contour. Only
                valid together with ``contour_trigger_id``.
            event_filter, use_saved_filters, optional_parameters, return_format, timeout:
                As in :meth:`latest_transients`.
            include_watchlist:
                Also return the events on your watchlist that lie inside the
                search circle, whatever their date and whether or not they
                match the filter. They are merged into ``"voevents"``, each
                with its distance from the center in degrees as ``"sep"``.

        Returns:
            With ``return_format="json"``, a dict of result groups:
            ``"voevents"`` holds the transient events, ``"sources"``,
            ``"Xsources"`` and ``"icecat"`` hold catalog matches, and
            ``"search_region"`` is ``"circle"`` or ``"contour_90"``.
            Catalog sources are not constrained by the time window.

        Raises:
            AstrocolibriAuthError: If no user ID is configured, or the API
                does not accept it.
            AstrocolibriRateLimitError: If the daily quota is exhausted.
            AstrocolibriConfigError: If an argument is invalid, including a
                malformed or out-of-range angle. Nothing is sent and no quota
                is used.
            AstrocolibriAPIError: If the API rejects the request.
            AstrocolibriTransportError: If the API cannot be reached.

        Example::

            results = client.cone_search(
                ra="05h34m31.94s",
                dec="+22d00m52.2s",
                radius="30′",
                start="2026-09-01T00:00:00Z",
                end="2026-09-08T00:00:00Z",
            )
            print(results["search_region"], len(results["voevents"]))
        """
        uid = self._require_uid("cone_search()")
        properties: Dict[str, Any] = {
            "position": {"ra": parse_ra(ra), "dec": parse_dec(dec)},
            "radius": parse_radius(radius),
        }
        if contour_trigger_id is not None:
            properties["trigger_id"] = _required_text(
                contour_trigger_id, "contour_trigger_id"
            )
        if contour_margin is not None:
            if contour_trigger_id is None:
                raise AstrocolibriConfigError(
                    "contour_margin only applies together with contour_trigger_id; "
                    "without a contour the API would silently ignore it."
                )
            properties["margin"] = _contour_margin(contour_margin)

        return self._search(
            "/cone_search",
            uid=uid,
            start=start,
            end=end,
            event_filter=event_filter,
            use_saved_filters=use_saved_filters,
            optional_parameters=optional_parameters,
            include_watchlist=include_watchlist,
            return_format=return_format,
            timeout=timeout,
            properties=properties,
        )

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def close(self) -> None:
        """
        Release the client's network resources.

        Closes the underlying session if the client created it. A session
        passed to the constructor stays open.
        """
        if self._owns_session:
            self._session.close()

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.close()
        return False

    def __repr__(self) -> str:
        state = "set" if self._uid is not None else "unset"
        return f"<Client uid={state} timeout={self._timeout:g}s>"

    # ── Request building ─────────────────────────────────────────────────────

    def _fetch_events(
        self,
        identifiers: Sequence[str],
        *,
        optional_parameters: Union[str, Sequence[str], None],
        simbad: bool,
        include_custom_events: bool,
        missing: str,
        timeout: Optional[float],
    ) -> List[Dict[str, Any]]:
        if missing not in _MISSING_POLICIES:
            raise AstrocolibriConfigError(
                f"missing must be 'raise' or 'skip', got {missing!r}."
            )
        names = _identifiers(identifiers)
        params: List[Tuple[str, str]] = [("trigger_id", name) for name in names]
        params += [
            ("optional_parameters", key)
            for key in _optional_parameters(optional_parameters)
        ]
        if _flag(simbad, "simbad"):
            # The API treats any non-empty value as true, so only send it when set.
            params.append(("simbad", "true"))
        if _flag(include_custom_events, "include_custom_events"):
            params.append(("uid", self._require_uid("include_custom_events=True")))

        payload = self._request_json("GET", "/event", params=params, timeout=timeout)

        # One identifier that resolves comes back as a bare object; anything
        # else, including one identifier that does not, comes back as a list.
        entries = [payload] if isinstance(payload, dict) else payload
        if (
            not isinstance(entries, list)
            or len(entries) != len(names)
            or not all(isinstance(entry, dict) for entry in entries)
        ):
            raise self._malformed("/event", payload)

        events: List[Dict[str, Any]] = []
        not_found: List[str] = []
        failed: List[str] = []
        for requested, entry in zip(names, entries):
            if not _is_event_failure(entry):
                events.append(entry)
            elif entry.get("error") == _EVENT_NOT_FOUND:
                not_found.append(requested)
            else:
                detail = (
                    entry.get("internal_error")
                    or entry.get("error")
                    or entry.get("message")
                )
                failed.append(f"{requested!r} ({self._scrub(detail)})")

        if missing == "raise":
            if failed:
                raise AstrocolibriAPIError(
                    f"The API could not process {', '.join(failed)}.", endpoint="/event"
                )
            if not_found:
                raise AstrocolibriNotFoundError(
                    f"No event found for {', '.join(repr(name) for name in not_found)}.",
                    endpoint="/event",
                )
        return events

    def _search(
        self,
        path: str,
        *,
        uid: str,
        start: TimeLike,
        end: TimeLike,
        event_filter: Optional[Dict[str, Any]],
        use_saved_filters: bool,
        optional_parameters: Union[str, Sequence[str], None],
        include_watchlist: bool,
        return_format: str,
        timeout: Optional[float],
        properties: Optional[Dict[str, Any]] = None,
    ) -> SearchResult:
        time_min, time_max = to_api_time_range(start, end)
        if return_format not in _RETURN_FORMATS:
            raise AstrocolibriConfigError(
                f"return_format must be one of {', '.join(map(repr, _RETURN_FORMATS))}, "
                f"got {return_format!r}."
            )

        body: Dict[str, Any] = {
            "time_range": {"min": time_min, "max": time_max},
            "uid": uid,
            "return_format": return_format,
            "optional_parameters": list(_optional_parameters(optional_parameters)),
            "include_watchlist": _flag(include_watchlist, "include_watchlist"),
        }
        search_filter = _search_filter(
            event_filter, _flag(use_saved_filters, "use_saved_filters")
        )
        if search_filter is not None:
            body["filter"] = search_filter
        if properties is not None:
            body["properties"] = properties

        if return_format == "votable":
            return self._request_text("POST", path, json_body=body, timeout=timeout)

        payload = self._request_json("POST", path, json_body=body, timeout=timeout)
        if return_format == "url":
            url = payload.get("url") if isinstance(payload, dict) else None
            if not isinstance(url, str):
                raise self._malformed(path, payload)
            return url
        if not isinstance(payload, dict):
            raise self._malformed(path, payload)
        return payload

    def _require_uid(self, purpose: str) -> str:
        if self._uid is None:
            raise AstrocolibriAuthError(
                f"{purpose} needs your Astro-COLIBRI user ID. Pass Client(uid=...) "
                f"or set the {UID_ENV_VAR} environment variable; your user ID is "
                f"shown at {_ACCOUNT_URL}."
            )
        return self._uid

    # ── Transport ────────────────────────────────────────────────────────────

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: Any = None,
        json_body: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        not_found: Optional[str] = None,
    ) -> Any:
        response = self._send(
            method,
            path,
            params=params,
            json_body=json_body,
            timeout=timeout,
            accept="application/json",
        )
        payload = _decode_json(response)
        self._raise_for_error(response, payload, path, not_found=not_found)
        if payload is _NOT_JSON:
            raise self._malformed(path, response.text)
        return payload

    def _request_text(
        self,
        method: str,
        path: str,
        *,
        params: Any = None,
        json_body: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        not_found: Optional[str] = None,
    ) -> str:
        response = self._send(
            method,
            path,
            params=params,
            json_body=json_body,
            timeout=timeout,
            accept="application/xml",
        )
        # Success is XML, but failures still arrive as JSON envelopes.
        looks_like_json = response.text.lstrip()[:1] in ("{", "[")
        payload = _decode_json(response) if looks_like_json else _NOT_JSON
        self._raise_for_error(response, payload, path, not_found=not_found)
        return response.text

    def _send(
        self,
        method: str,
        path: str,
        *,
        params: Any,
        json_body: Optional[Dict[str, Any]],
        timeout: Optional[float],
        accept: str,
    ) -> requests.Response:
        seconds = self._timeout if timeout is None else _positive_timeout(timeout)
        headers = {
            "User-Agent": f"astro-colibri-python/{__version__}",
            "Accept": accept,
        }
        try:
            return self._session.request(
                method,
                f"{self.API_URL}{path}",
                params=params,
                json=json_body,
                headers=headers,
                timeout=seconds,
            )
        # `from None` throughout: the original exception text includes the
        # full URL, and with it any user ID sent as a query parameter.
        except requests.Timeout:
            raise AstrocolibriTransportError(
                f"{method} {path} timed out after {seconds:g} s. Pass a larger "
                f"timeout= if the request is expected to be slow."
            ) from None
        except requests.RequestException as exc:
            raise AstrocolibriTransportError(
                f"{method} {path} failed: {self._scrub(exc)}"
            ) from None

    def _raise_for_error(
        self,
        response: requests.Response,
        payload: Any,
        path: str,
        *,
        not_found: Optional[str] = None,
    ) -> None:
        status = response.status_code
        message: Optional[str] = None

        envelope = _error_envelope(payload)
        if envelope is not None:
            envelope_status, message = envelope
            if 200 <= status < 300:
                # Some endpoints serialize an error under HTTP 200: the body wins.
                status = envelope_status
        if 200 <= status < 300:
            return

        if not message:
            message = (
                _payload_message(payload)
                or _snippet(response.text)
                or response.reason
                or "request failed"
            )
        message = self._scrub(message)

        if status == 401:
            if self._uid is None:
                hint = (
                    f"Pass Client(uid=...) or set {UID_ENV_VAR}; your user ID is "
                    f"shown at {_ACCOUNT_URL}."
                )
            else:
                hint = f"Check the configured user ID against {_ACCOUNT_URL}."
            raise AstrocolibriAuthError(f"{path}: {_sentence(message)} {hint}")
        if status == 403:
            raise AstrocolibriAuthError(
                f"{path}: {_sentence(message)} The API does not accept the "
                f"configured user ID: copy it again from {_ACCOUNT_URL}."
            )
        if status == 404:
            raise AstrocolibriNotFoundError(
                not_found or message, status_code=404, endpoint=path
            )
        if status == 429:
            raise AstrocolibriRateLimitError(
                message, status_code=429, endpoint=path, reset_time=_reset_time(message)
            )
        raise AstrocolibriAPIError(message, status_code=status, endpoint=path)

    def _malformed(self, path: str, payload: Any) -> AstrocolibriAPIError:
        text = payload if isinstance(payload, str) else repr(payload)
        return AstrocolibriAPIError(
            f"The API returned a response this client does not understand: "
            f"{_snippet(self._scrub(text))}",
            endpoint=path,
        )

    def _scrub(self, text: Any) -> str:
        """``text`` with every form of the user ID replaced by ``<uid>``."""
        text = "" if text is None else str(text)
        if self._uid:
            # requests form-encodes query strings (a space becomes "+"); other
            # layers percent-encode. Cover the raw ID and both encodings.
            for form in {
                self._uid,
                quote(self._uid, safe=""),
                quote_plus(self._uid, safe=""),
            }:
                text = text.replace(form, "<uid>")
        return text


# ── Argument validation ──────────────────────────────────────────────────────


def _resolve_uid(uid: Optional[str]) -> Optional[str]:
    if uid is not None:
        if not isinstance(uid, str):
            raise AstrocolibriConfigError(
                f"uid must be a string, got {type(uid).__name__}."
            )
        stripped = uid.strip()
        if not stripped:
            raise AstrocolibriConfigError(
                f"uid was given but is empty. Pass your Astro-COLIBRI user ID "
                f"(shown at {_ACCOUNT_URL}), or leave uid out to read it from "
                f"{UID_ENV_VAR}."
            )
        return stripped
    # An empty variable counts as unset: CI templates often define them blank.
    return os.environ.get(UID_ENV_VAR, "").strip() or None


def _positive_timeout(value: Any) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, numbers.Real)
        or not math.isfinite(value)
        or value <= 0
    ):
        raise AstrocolibriConfigError(
            f"timeout must be a positive number of seconds, got {value!r}."
        )
    return float(value)


def _identifiers(values: Iterable[str]) -> List[str]:
    if isinstance(values, str):
        raise AstrocolibriConfigError(
            "identifiers must be a list of strings, not a single string. "
            "Use get_event() to look up one identifier."
        )
    try:
        items = list(values)
    except TypeError:
        raise AstrocolibriConfigError(
            f"identifiers must be a list of strings, got {type(values).__name__}."
        ) from None
    if not items:
        raise AstrocolibriConfigError("identifiers is empty.")
    return [_required_text(item, "identifier") for item in items]


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AstrocolibriConfigError(
            f"{name} must be a non-empty string, got {value!r}."
        )
    return value.strip()


def _optional_parameters(values: Union[str, Sequence[str], None]) -> Tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = (values,)
    try:
        keys = tuple(values)
    except TypeError:
        raise AstrocolibriConfigError(
            f"optional_parameters must be a list of strings, got {type(values).__name__}."
        ) from None
    # Checked here because the API does not reject an unknown key: on /event
    # it reports the whole event as not found instead.
    unknown = [key for key in keys if key not in OPTIONAL_PARAMETERS]
    if unknown:
        raise AstrocolibriConfigError(
            f"optional_parameters accepts {', '.join(map(repr, OPTIONAL_PARAMETERS))}, "
            f"got {', '.join(map(repr, unknown))}."
        )
    return keys


def _flag(value: Any, name: str) -> bool:
    # Strict on purpose: bool("false") is True.
    if not isinstance(value, bool):
        raise AstrocolibriConfigError(f"{name} must be True or False, got {value!r}.")
    return value


def _contour_margin(value: Any) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, numbers.Real)
        or not math.isfinite(value)
        or not 0.0 <= value <= _MAX_CONTOUR_MARGIN
    ):
        raise AstrocolibriConfigError(
            f"contour_margin must be a number of degrees within [0, "
            f"{_MAX_CONTOUR_MARGIN:g}], got {value!r}."
        )
    return float(value)


def _search_filter(
    event_filter: Optional[Dict[str, Any]], use_saved_filters: bool
) -> Optional[Dict[str, Any]]:
    """The ``filter`` to send, or ``None`` to let the API load the saved filters."""
    if use_saved_filters:
        if event_filter is not None:
            raise AstrocolibriConfigError(
                "Pass either event_filter or use_saved_filters=True, not both."
            )
        return None
    if event_filter is None:
        return dict(_MATCH_ALL_FILTER)
    if not isinstance(event_filter, dict):
        raise AstrocolibriConfigError(
            f"event_filter must be an API filter dictionary, got {type(event_filter).__name__}."
        )
    if not event_filter:
        # The API reads an empty filter as "no filter" and would quietly
        # switch to the filters saved in the app.
        raise AstrocolibriConfigError(
            "event_filter is empty. Leave it out to search every event you may "
            "access, or pass use_saved_filters=True to apply your saved filters."
        )
    return event_filter


# ── Response parsing ─────────────────────────────────────────────────────────


def _decode_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return _NOT_JSON


def _is_event_failure(entry: Dict[str, Any]) -> bool:
    """Whether a /event list entry reports a failure rather than an event."""
    return ("error" in entry or "internal_error" in entry) and set(
        entry
    ) <= _EVENT_FAILURE_KEYS


def _error_envelope(payload: Any) -> Optional[Tuple[int, str]]:
    """``(status, message)`` if ``payload`` is one of the API's error envelopes."""
    # [{"message": ..., "status_code": 401}, 401]: a Flask error tuple that
    # reached the client serialized as JSON, typically under HTTP 200.
    if isinstance(payload, list) and len(payload) == 2 and isinstance(payload[0], dict):
        status = _as_status(payload[1])
        if status is not None and status >= 400:
            return status, _payload_message(payload[0]) or ""
    if (
        isinstance(payload, dict)
        and "status_code" in payload
        and set(payload) <= _ENVELOPE_KEYS
    ):
        status = _as_status(payload["status_code"])
        if status is not None and status >= 400:
            return status, _payload_message(payload) or ""
    return None


def _as_status(value: Any) -> Optional[int]:
    # Envelopes carry the status as an int or as a string, depending on the
    # endpoint that built them.
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _payload_message(payload: Any) -> Optional[str]:
    if isinstance(payload, dict):
        for key in ("message", "error"):
            if isinstance(payload.get(key), str) and payload[key].strip():
                return payload[key].strip()
    return None


def _reset_time(message: str) -> Optional[datetime]:
    match = _RESET_TIME.search(message or "")
    if not match:
        return None
    try:
        return datetime.fromisoformat(match.group(1))
    except ValueError:
        return None


def _snippet(text: Optional[str]) -> str:
    text = (text or "").strip()
    if len(text) > _SNIPPET_LENGTH:
        return text[:_SNIPPET_LENGTH] + "…"
    return text


def _sentence(text: str) -> str:
    return text.rstrip(". ") + "."
