"""
astrocolibri/voevent.py

Parse VOEvent 2.0 XML documents into plain Python objects.

The Astro-COLIBRI broker's ``astrocolibri.*.VOEvent`` topics and
:meth:`Client.get_event_voevent` deliver VOEvent XML. :func:`parse_voevent`
turns such a document into a :class:`VOEvent`: the time as an aware
``datetime``, the position in degrees, and every ``Param`` with its value
converted according to its ``dataType``.

The parser follows the IVOA VOEvent 2.0 structure only, so it also reads the
notices GCN distributes (Swift, Fermi, LVK, SVOM, IceCube, ...). What those
notices' Params mean differs from instrument to instrument and is left to
you; their names are kept exactly as published.

It needs nothing beyond the standard library. ``Position.to_skycoord()``
uses astropy if you have it installed.

Example::

    from astrocolibri import parse_voevent

    event = parse_voevent(xml)
    print(event.ivorn, event.time, event.position)
    print(event.get("trigger_id"), event.get("far"))
"""

from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from .exceptions import AstrocolibriDecodeError

#: The VOEvent 2.0 XML namespace, carried by the root element.
VOEVENT_NAMESPACE = "http://www.ivoa.net/xml/VOEvent/v2.0"

#: ``AuthorIVORN`` of the documents Astro-COLIBRI publishes.
ASTRO_COLIBRI_AUTHOR_IVORN = "ivo://AstroCOLIBRI"

# "2023-05-18T12:59:08", with any number of fractional digits and an
# optional "Z" or offset. datetime.fromisoformat() only accepts 3 or 6
# fractional digits before Python 3.11, and GCN writes two ("22.50").
_ISO_TIME = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})[T ](?P<hms>\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<fraction>\d+))?"
    r"(?P<zone>Z|[+-]\d{2}:?\d{2})?$"
)


@dataclass(frozen=True)
class Param:
    """
    One ``<Param>`` of the ``What`` section.

    Attributes:
        name: The Param's ``name``, exactly as published.
        value: The value, converted by ``dataType``: ``int`` for
            ``dataType="int"``, ``float`` for ``"float"``, otherwise the
            text as ``str``. Most GCN notices declare no ``dataType``, so
            their numbers arrive as text: use ``float(param.value)``. In an
            Astro-COLIBRI document, lists and objects are JSON-encoded and
            come back decoded (``follow_up`` is a ``list``).
        raw: The value exactly as written in the XML.
        unit: The ``unit`` attribute, if any (``"deg"``, ``"yr^-1"``).
        ucd: The IVOA Unified Content Descriptor, if any.
        data_type: ``"int"``, ``"float"`` or ``"string"`` (the default).
        description: The Param's ``<Description>``, if any.
        references: URIs of the Param's ``<Reference>`` elements.
    """

    name: str
    value: Any
    raw: Optional[str]
    unit: Optional[str] = None
    ucd: Optional[str] = None
    data_type: str = "string"
    description: Optional[str] = None
    references: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Position:
    """
    Sky position from ``WhereWhen``, in degrees.

    Attributes:
        ra: Right ascension.
        dec: Declination.
        err: Radius of the error circle, or ``None`` when the document gives
            none. Astro-COLIBRI writes ``0`` when an event has no error
            radius, which also reads as ``None`` here. Gravitational waves
            and some neutrino and gamma-ray alerts are localized to regions
            far from circular; this radius is only a rough scale for them.
        system: The coordinate system ID, e.g. ``"UTC-FK5-GEO"`` or
            ``"UTC-ICRS-GEO"``.
    """

    ra: float
    dec: float
    err: Optional[float]
    system: Optional[str] = None

    def to_skycoord(self) -> Any:
        """
        The position as an :class:`astropy.coordinates.SkyCoord`.

        Uses the FK5 (J2000) or ICRS frame named by :attr:`system`, ICRS
        when it names neither. Requires astropy, which the SDK does not
        install for you.

        Raises:
            ImportError: If astropy is not installed.
        """
        # Imported here: astropy is optional, and only this method needs it.
        from astropy.coordinates import SkyCoord

        frame = "fk5" if self.system and "FK5" in self.system.upper() else "icrs"
        return SkyCoord(ra=self.ra, dec=self.dec, unit="deg", frame=frame)


@dataclass(frozen=True)
class Citation:
    """One ``<EventIVORN>`` of the ``Citations`` section."""

    ivorn: str
    cite: Optional[str]  # "followup", "supersedes" or "retraction"


@dataclass(frozen=True)
class VOEvent:
    """
    A parsed VOEvent 2.0 document.

    Attributes:
        ivorn: The document's IVORN, its unique identifier.
        role: ``"observation"``, ``"test"``, ``"utility"`` or
            ``"prediction"``. Skip ``"test"`` documents in production code.
        version: The VOEvent version, ``"2.0"``.
        author_ivorn: ``Who/AuthorIVORN``; ``"ivo://AstroCOLIBRI"`` for the
            documents Astro-COLIBRI publishes.
        author: ``Who/Author``'s short name, else its contact name.
        date: ``Who/Date``, when the document was written.
        time: When the event happened (``WhereWhen``'s ``ISOTime``), as an
            aware UTC ``datetime``. For a time scale other than UTC (the
            system ID starts with ``TT`` or ``TDB``, for example) it is
            returned naive, since it is not a UTC time.
        position: Where it happened, or ``None`` if the document gives no
            usable position (GCN writes RA = Dec = -1 for "unavailable").
        params: The ``What`` Params outside any Group, by name.
        groups: The ``What`` Groups by name, each a ``dict`` of its Params
            by name. Astro-COLIBRI documents keep every Param in a Group.
        importance: ``Why/@importance``, from 0 to 1.
        probability: The first ``Why/Inference/@probability``.
        concepts: Every ``Why/Inference/Concept``, such as
            ``"process.variation.burst;em.gamma"``.
        name: The first ``Why/Inference/Name``; the event's display name in
            Astro-COLIBRI documents.
        description: The document's top-level ``<Description>``.
        references: URIs of the ``How/Reference`` elements.
        citations: The ``Citations/EventIVORN`` entries: the earlier
            documents this one follows up, supersedes or retracts.
        root: The parsed XML tree, with namespaces removed from every tag,
            for anything the fields above do not cover.
    """

    ivorn: str
    role: str
    version: Optional[str]
    author_ivorn: Optional[str]
    author: Optional[str]
    date: Optional[datetime]
    time: Optional[datetime]
    position: Optional[Position]
    params: Dict[str, Param]
    groups: Dict[str, Dict[str, Param]]
    importance: Optional[float]
    probability: Optional[float]
    concepts: Tuple[str, ...]
    name: Optional[str]
    description: Optional[str]
    references: Tuple[str, ...]
    citations: Tuple[Citation, ...]
    root: ET.Element = field(repr=False, compare=False)

    @property
    def is_test(self) -> bool:
        """``True`` for a test document (``role="test"``)."""
        return self.role == "test"

    @property
    def is_astro_colibri(self) -> bool:
        """``True`` if Astro-COLIBRI wrote this document."""
        return self.author_ivorn == ASTRO_COLIBRI_AUTHOR_IVORN

    def iter_params(self) -> Iterator[Param]:
        """Every Param in document order: ungrouped ones first, then each Group's."""
        yield from self.params.values()
        for group in self.groups.values():
            yield from group.values()

    def param(self, name: str) -> Optional[Param]:
        """
        The Param called ``name``, wherever it is, or ``None``.

        Ungrouped Params are searched first, then the Groups in document
        order. If a name occurs in more than one Group, pick the one you
        mean through :attr:`groups`.
        """
        for param in self.iter_params():
            if param.name == name:
                return param
        return None

    def get(self, name: str, default: Any = None) -> Any:
        """
        The converted value of the Param called ``name``, or ``default``.

        Example::

            event.get("far")            # 0.0101... (float)
            event.get("trigger_id")     # "S230518h"
        """
        param = self.param(name)
        return default if param is None else param.value

    def to_dict(self) -> Dict[str, Any]:
        """
        Every Param's value in one flat ``dict`` keyed by name.

        Handy for building a table of events. When a name occurs more than
        once, the first occurrence wins, as in :meth:`get`.
        """
        values: Dict[str, Any] = {}
        for param in self.iter_params():
            values.setdefault(param.name, param.value)
        return values

    def to_colibri_event(self) -> Dict[str, Any]:
        """
        The event in Astro-COLIBRI's own JSON structure.

        The inverse of the conversion Astro-COLIBRI applies when it publishes
        a VOEvent: the result has the same field names and value types as an
        alert on the ``astrocolibri.*.JSON`` topics and an event returned by
        the API, so code (and an :class:`~astrocolibri.EventFilter`) written
        for one works on the other.

        The VOEvent leaves out what it cannot or should not carry, so neither
        does the result:

        - fields that are unset: a negative numeric placeholder (``-1``) or
          an empty text. Code that reads ``event.get("redshift", -1)`` sees
          the same value either way. An event without a usable position gets
          ``ra``, ``dec`` and ``err`` set to ``-1.0``, as on the JSON topics.
        - ``gw_contours`` and ``archive``, which are large: ask the API for
          them with ``optional_parameters``.
        - ``time`` is rounded to the millisecond, and ``timestamp`` is
          derived from it.

        Returns:
            A new ``dict`` on every call.

        Raises:
            AstrocolibriDecodeError: If the document was not written by
                Astro-COLIBRI, such as a GCN notice: those have no
                Astro-COLIBRI event behind them.

        Example::

            event = alert.voevent().to_colibri_event()
            print(event["trigger_id"], event["type"], event["ra"], event["dec"])
        """
        if not self.is_astro_colibri:
            raise AstrocolibriDecodeError(
                f"{self.ivorn} was not written by Astro-COLIBRI "
                f"(author {self.author_ivorn or 'unknown'}), so it has no "
                f"Astro-COLIBRI event to convert back to"
            )

        event: Dict[str, Any] = {}
        map_areas: Dict[str, Any] = {}
        for param in self.iter_params():
            name, value = param.name, param.value
            if name == "original_ivorn":
                name = "ivorn"
            elif name.startswith(_AREA_PREFIX):
                map_areas.setdefault(name[len(_AREA_PREFIX) :], value)
                continue
            elif name in _BOOLEAN_FIELDS and isinstance(value, str):
                value = value.strip().lower() == "true"
            event.setdefault(name, value)
            if name == "transient_flux" and param.unit:
                event.setdefault("transient_flux_units", param.unit)
        if map_areas:
            event["map_areas"] = map_areas

        if self.position is not None:
            event["ra"] = self.position.ra
            event["dec"] = self.position.dec
            if "err" not in event and self.position.err is not None:
                event["err"] = self.position.err
        else:
            event["ra"] = event["dec"] = -1.0
        event.setdefault("err", -1.0)

        iso_time = _text(
            self.root.find(
                "WhereWhen/ObsDataLocation/ObservationLocation/AstroCoords"
                "/Time/TimeInstant/ISOTime"
            )
        )
        if iso_time is not None:
            event["time"] = iso_time
        if self.time is not None and self.time.tzinfo is not None:
            event["timestamp"] = float(round(self.time.timestamp() * 1000.0))

        comment = _text(self.root.find("Why/Inference/Description"))
        if comment is not None:
            event.setdefault("comment", comment)
        return event


# Astro-COLIBRI writes each credible-region area of ``map_areas`` as its own
# Param, ``area_<level>`` (``area_90``).
_AREA_PREFIX = "area_"

# Booleans travel as "true"/"false" text: VOEvent Params have no boolean type.
_BOOLEAN_FIELDS = frozenset({"slew"})


def parse_voevent(document: Union[str, bytes]) -> VOEvent:
    """
    Parse a VOEvent 2.0 XML document.

    Accepts the documents Astro-COLIBRI publishes on its VOEvent topics and
    returns from :meth:`Client.get_event_voevent`, and VOEvents from other
    sources such as GCN notices.

    Args:
        document: The XML, as ``str`` or ``bytes``.

    Returns:
        The parsed :class:`VOEvent`.

    Raises:
        AstrocolibriDecodeError: If ``document`` is not well-formed XML, or
            its root element is not a VOEvent.

    Example::

        for alert in consumer.consume():
            event = parse_voevent(alert.value())
            if event.is_test:
                continue
            print(event.name, event.time, event.position)
    """
    try:
        root = ET.fromstring(document)
    except ET.ParseError as exc:
        raise AstrocolibriDecodeError(f"not a well-formed XML document: {exc}") from exc

    # Only the root is namespaced in a valid VOEvent 2.0 document, but
    # stripping every namespace also reads documents that qualify the
    # children, as Astro-COLIBRI did before 2026-09.
    for element in root.iter():
        if isinstance(element.tag, str) and element.tag.startswith("{"):
            element.tag = element.tag.split("}", 1)[1]
    if root.tag != "VOEvent":
        raise AstrocolibriDecodeError(f"root element is <{root.tag}>, not <VOEvent>")

    ivorn = root.get("ivorn")
    if not ivorn:
        raise AstrocolibriDecodeError("VOEvent has no ivorn attribute")

    author_ivorn = _text(root.find("Who/AuthorIVORN"))
    astro_colibri = author_ivorn == ASTRO_COLIBRI_AUTHOR_IVORN

    params: Dict[str, Param] = {}
    groups: Dict[str, Dict[str, Param]] = {}
    what = root.find("What")
    if what is not None:
        for element in what.findall("Param"):
            param = _param(element, decode_json=astro_colibri)
            params[param.name] = param
        for index, group in enumerate(what.findall("Group")):
            group_name = group.get("name") or f"group_{index}"
            members = groups.setdefault(group_name, {})
            for element in group.findall("Param"):
                param = _param(element, decode_json=astro_colibri)
                members[param.name] = param

    coords = root.find("WhereWhen/ObsDataLocation/ObservationLocation/AstroCoords")
    system = coords.get("coord_system_id") if coords is not None else None
    inferences = root.findall("Why/Inference")

    return VOEvent(
        ivorn=ivorn,
        role=root.get("role") or "observation",
        version=root.get("version"),
        author_ivorn=author_ivorn,
        author=_text(root.find("Who/Author/shortName"))
        or _text(root.find("Who/Author/contactName")),
        date=_parse_time(_text(root.find("Who/Date")), utc=True),
        time=_event_time(coords, system),
        position=_position(coords, system),
        params=params,
        groups=groups,
        importance=_float(root.find("Why"), "importance"),
        probability=_float(inferences[0], "probability") if inferences else None,
        concepts=_texts(root.findall("Why/Inference/Concept")),
        name=next(iter(_texts(root.findall("Why/Inference/Name"))), None),
        description=_text(root.find("Description")),
        references=_uris(root.findall("How/Reference")),
        citations=tuple(
            Citation(ivorn=_text(cited), cite=cited.get("cite"))
            for cited in root.findall("Citations/EventIVORN")
            if _text(cited)
        ),
        root=root,
    )


# ── Helpers ──────────────────────────────────────────────────────────────────


def _text(element: Optional[ET.Element]) -> Optional[str]:
    """An element's stripped text, ``None`` if absent or blank."""
    if element is None or element.text is None:
        return None
    text = element.text.strip()
    return text or None


def _texts(elements: List[ET.Element]) -> Tuple[str, ...]:
    """The non-blank texts of ``elements``, in order."""
    return tuple(text for text in map(_text, elements) if text)


def _uris(references: List[ET.Element]) -> Tuple[str, ...]:
    return tuple(ref.get("uri") for ref in references if ref.get("uri"))


def _float(element: Optional[ET.Element], attribute: str) -> Optional[float]:
    if element is None:
        return None
    return _to_float(element.get(attribute))


def _to_float(text: Optional[str]) -> Optional[float]:
    if text is None:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _param(element: ET.Element, *, decode_json: bool) -> Param:
    raw = element.get("value")
    if raw is None:
        # The schema also allows the value as a <Value> child.
        value_element = element.find("Value")
        raw = value_element.text if value_element is not None else None
    data_type = element.get("dataType") or "string"
    return Param(
        name=element.get("name") or "",
        value=_convert(raw, data_type, decode_json=decode_json),
        raw=raw,
        unit=element.get("unit"),
        ucd=element.get("ucd"),
        data_type=data_type,
        description=_text(element.find("Description")),
        references=_uris(element.findall("Reference")),
    )


def _convert(raw: Optional[str], data_type: str, *, decode_json: bool) -> Any:
    if raw is None:
        return None
    text = raw.strip()
    try:
        if data_type == "int":
            return int(text)
        if data_type == "float":
            return float(text)
    except ValueError:
        # A value that contradicts its dataType stays readable as text.
        return raw
    if decode_json and text[:1] in ("[", "{"):
        try:
            return json.loads(text)
        except ValueError:
            return raw
    return raw


def _event_time(
    coords: Optional[ET.Element], system: Optional[str]
) -> Optional[datetime]:
    if coords is None:
        return None
    time_scale = (system or "UTC").split("-", 1)[0].upper()
    text = _text(coords.find("Time/TimeInstant/ISOTime"))
    return _parse_time(text, utc=time_scale == "UTC")


def _parse_time(text: Optional[str], *, utc: bool) -> Optional[datetime]:
    """
    ISO 8601 text as a ``datetime``; aware UTC when ``utc`` is true.

    VOEvent times carry no offset and are in the time scale of the
    coordinate system, so a missing offset means UTC for a UTC system.
    """
    if not text:
        return None
    match = _ISO_TIME.match(text)
    if match is None:
        return None
    try:
        moment = datetime.strptime(
            f"{match['date']}T{match['hms']}", "%Y-%m-%dT%H:%M:%S"
        )
    except ValueError:
        return None
    fraction = match["fraction"]
    if fraction:
        # Microsecond resolution: "5" is 500000 us, "1234567" truncates.
        moment = moment.replace(microsecond=int(fraction[:6].ljust(6, "0")))

    zone = match["zone"]
    if zone and zone != "Z":
        sign = -1 if zone[0] == "-" else 1
        digits = zone[1:].replace(":", "")
        offset = timedelta(hours=int(digits[:2]), minutes=int(digits[2:]))
        return moment.replace(tzinfo=timezone(sign * offset)).astimezone(timezone.utc)
    if zone == "Z" or utc:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def _position(
    coords: Optional[ET.Element], system: Optional[str]
) -> Optional[Position]:
    if coords is None:
        return None
    position = coords.find("Position2D")
    if position is None:
        return None
    ra = _to_float(_text(position.find("Value2/C1")))
    dec = _to_float(_text(position.find("Value2/C2")))
    # GCN marks an unavailable position with RA = Dec = -1.
    if ra is None or dec is None or not 0.0 <= ra <= 360.0 or not -90.0 <= dec <= 90.0:
        return None
    err = _to_float(_text(position.find("Error2Radius")))
    return Position(
        ra=ra,
        dec=dec,
        err=err if err is not None and err > 0 else None,
        system=system,
    )


__all__: List[str] = [
    "ASTRO_COLIBRI_AUTHOR_IVORN",
    "Citation",
    "Param",
    "Position",
    "VOEvent",
    "VOEVENT_NAMESPACE",
    "parse_voevent",
]
