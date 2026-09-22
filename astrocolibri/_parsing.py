"""
astrocolibri/_parsing.py

Turn user input into what the Astro-COLIBRI API expects.

Coordinates become float degrees and times become timezone-explicit UTC
ISO 8601 strings, both *before* a request is sent. The conversion is not
cosmetic: the API only treats plain numbers as degrees, and it reads a time
without an offset in the server's own timezone, which would silently shift
a search window.
"""

from __future__ import annotations

import math
import numbers
import re
from datetime import datetime, timezone
from typing import Tuple, Union

from .exceptions import AstrocolibriConfigError

Angle = Union[str, float, int]
TimeLike = Union[datetime, str]

# ── Angles ───────────────────────────────────────────────────────────────────

_NOTATION_HINT = (
    "Use decimal degrees (83.63), hours (05h34m31.9s), degrees (22d00m52s "
    "or 22°00′52″) or colon notation (05:34:31.9)."
)

_PLAIN_NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")

# "05:34:31.94", "-00:30:00", "05 34 31.94", "05:34.5"
_SEPARATOR = r"(?:\s*:\s*|\s+)"
_SEPARATED = re.compile(
    r"^(?P<sign>[+-]?)\s*(?P<first>\d+)"
    + _SEPARATOR
    + r"(?P<second>\d+(?:\.\d*)?)"
    + r"(?:"
    + _SEPARATOR
    + r"(?P<third>\d+(?:\.\d*)?))?$"
)

# Position of each unit in a "<largest><middle><smallest>" angle. Slot 0 is
# hours or degrees; minutes and seconds follow whichever of the two it is.
_UNIT_SLOT = {
    "h": 0,
    "d": 0,
    "°": 0,
    "m": 1,
    "′": 1,
    "'": 1,
    "s": 2,
    "″": 2,
    '"': 2,
}
_UNIT_GROUP = re.compile(
    r"\s*(\d+(?:\.\d*)?|\.\d+)\s*([" + re.escape("".join(_UNIT_SLOT)) + r"])"
)


def parse_ra(value: Angle) -> float:
    """
    Right ascension in degrees, within ``[0, 360)``.

    Colon and whitespace notation is read as hours, minutes and seconds
    (``"05:34:31.9"``), as is conventional for right ascension.

    Raises:
        AstrocolibriConfigError: If the notation is malformed or ambiguous,
            or the angle falls outside ``[0, 360)``.
    """
    degrees = _parse_angle(value, name="ra", allow_hours=True)
    if not 0.0 <= degrees < 360.0:
        raise AstrocolibriConfigError(
            f"ra must be within [0, 360) degrees, got {degrees:g}{_origin(value)}."
        )
    return degrees


def parse_dec(value: Angle) -> float:
    """
    Declination in degrees, within ``[-90, 90]``.

    Colon and whitespace notation is read as degrees, arcminutes and
    arcseconds (``"-05:23:28"``). A leading sign applies to the whole
    angle, so ``"-00:30:00"`` is -0.5°.

    Raises:
        AstrocolibriConfigError: If the notation is malformed, uses hours,
            or the angle falls outside ``[-90, 90]``.
    """
    degrees = _parse_angle(value, name="dec", allow_hours=False)
    if not -90.0 <= degrees <= 90.0:
        raise AstrocolibriConfigError(
            f"dec must be within [-90, 90] degrees, got {degrees:g}{_origin(value)}."
        )
    return degrees


def parse_radius(value: Angle) -> float:
    """
    Search radius in degrees, within ``(0, 180]``.

    Accepts the same notation as :func:`parse_dec`, which makes arcminute
    radii natural to write: ``"30′"`` or ``"30'"`` is 0.5°.

    Raises:
        AstrocolibriConfigError: If the notation is malformed, uses hours,
            or the radius falls outside ``(0, 180]``.
    """
    degrees = _parse_angle(value, name="radius", allow_hours=False)
    if not 0.0 < degrees <= 180.0:
        raise AstrocolibriConfigError(
            f"radius must be within (0, 180] degrees, got {degrees:g}{_origin(value)}."
        )
    return degrees


def _parse_angle(value: Angle, *, name: str, allow_hours: bool) -> float:
    """Convert a number or angle string to degrees, inferring units from notation."""
    # bool is an int subclass, and True would otherwise read as 1°.
    if isinstance(value, bool) or not isinstance(value, (numbers.Real, str)):
        raise AstrocolibriConfigError(
            f"{name} must be a number in degrees or an angle string, got "
            f"{type(value).__name__}. For an astropy angle pass its .deg value."
        )

    if isinstance(value, numbers.Real):
        return _finite(float(value), name=name, original=value)

    text = value.strip()
    if not text:
        raise AstrocolibriConfigError(f"{name} is an empty string. {_NOTATION_HINT}")

    if _PLAIN_NUMBER.match(text):
        return _finite(float(text), name=name, original=value)

    lowered = text.lower()
    if any(unit in lowered for unit in _UNIT_SLOT):
        return _parse_unit_marked(
            lowered, name=name, allow_hours=allow_hours, original=value
        )

    match = _SEPARATED.match(lowered)
    if match:
        return _parse_separated(match, name=name, as_hours=allow_hours, original=value)

    raise AstrocolibriConfigError(f"{name}: could not read {value!r}. {_NOTATION_HINT}")


def _parse_unit_marked(
    text: str, *, name: str, allow_hours: bool, original: str
) -> float:
    """Read an angle whose components carry explicit units, e.g. ``5h34m31.9s``."""
    negative, body = _split_sign(text)

    groups = []
    position = 0
    while position < len(body):
        match = _UNIT_GROUP.match(body, position)
        if not match:
            raise AstrocolibriConfigError(
                f"{name}: could not read {original!r} near "
                f"{body[position:].strip()!r}. {_NOTATION_HINT}"
            )
        groups.append((match.group(1), match.group(2)))
        position = match.end()

    base = None  # "h" or "d", once the largest unit has been seen
    last_slot = -1
    sub_unit_letters = False
    total = 0.0
    for index, (number, unit) in enumerate(groups):
        slot = _UNIT_SLOT[unit]

        if slot == 0:
            this_base = "h" if unit == "h" else "d"
            if base is not None and base != this_base:
                raise AstrocolibriConfigError(
                    f"{name}: {original!r} mixes hour and degree notation."
                )
            base = this_base
        if slot <= last_slot:
            raise AstrocolibriConfigError(
                f"{name}: the units in {original!r} must run from largest to "
                f"smallest, each used at most once."
            )
        if "." in number and index < len(groups) - 1:
            raise AstrocolibriConfigError(
                f"{name}: only the last component of {original!r} may have a "
                f"fractional part."
            )

        amount = float(number)
        # Minutes and seconds only wrap at 60 when a larger unit precedes
        # them: "90m" on its own is a perfectly good 1.5° radius.
        if slot > 0 and last_slot >= 0 and amount >= 60.0:
            raise AstrocolibriConfigError(
                f"{name}: {number}{unit} in {original!r} must be below 60."
            )
        if unit in ("m", "s"):
            sub_unit_letters = True

        total += amount / 60.0**slot
        last_slot = slot

    if base == "h" and not allow_hours:
        raise AstrocolibriConfigError(
            f"{name}: {original!r} is in hours, which only right ascension uses. "
            f"Give {name} in degrees."
        )
    if base is None and allow_hours and sub_unit_letters:
        # For right ascension a bare "30m" could be minutes of time (7.5°)
        # or arcminutes (0.5°). Refuse to guess.
        raise AstrocolibriConfigError(
            f"{name}: {original!r} is ambiguous: 'm' and 's' could be minutes "
            f"of time or of arc. Add the hours ('0h30m') or degrees ('0d30m'), "
            f"or use ′ and ″ for arcminutes and arcseconds."
        )

    degrees = total * 15.0 if base == "h" else total
    return -degrees if negative else degrees


def _parse_separated(
    match: "re.Match[str]", *, name: str, as_hours: bool, original: str
) -> float:
    """Read colon- or whitespace-separated notation: HMS for RA, DMS otherwise."""
    first = float(match.group("first"))
    second_text = match.group("second")
    third_text = match.group("third")

    if third_text is not None and "." in second_text:
        raise AstrocolibriConfigError(
            f"{name}: only the last component of {original!r} may have a "
            f"fractional part."
        )

    second = float(second_text)
    third = float(third_text) if third_text is not None else 0.0
    if second >= 60.0 or third >= 60.0:
        raise AstrocolibriConfigError(
            f"{name}: minutes and seconds in {original!r} must be below 60."
        )

    magnitude = first + second / 60.0 + third / 3600.0
    degrees = magnitude * 15.0 if as_hours else magnitude
    return -degrees if match.group("sign") == "-" else degrees


def _split_sign(text: str) -> Tuple[bool, str]:
    if text[:1] in ("+", "-"):
        return text[0] == "-", text[1:].lstrip()
    return False, text


def _finite(degrees: float, *, name: str, original: object) -> float:
    if not math.isfinite(degrees):
        raise AstrocolibriConfigError(
            f"{name} must be a finite number, got {original!r}."
        )
    return degrees


def _origin(value: Angle) -> str:
    """`` (from '05:34:31.9')`` when the input was a string, for error messages."""
    return f" (from {value!r})" if isinstance(value, str) else ""


# ── Times ────────────────────────────────────────────────────────────────────


def to_api_time(value: TimeLike, *, name: str) -> str:
    """
    A moment as the API expects it: ISO 8601, UTC, explicit ``+00:00``.

    Accepts a timezone-aware :class:`datetime` or an ISO 8601 string that
    carries an offset (a trailing ``Z`` is fine). The instant is converted
    to UTC, never relabelled.

    ``+00:00`` is emitted rather than ``Z`` because the API parses times with
    ``datetime.fromisoformat``, which rejects ``Z`` before Python 3.11.

    Raises:
        AstrocolibriConfigError: If the value has no timezone, is not an
            ISO 8601 string, or is of another type (such as an epoch number,
            where seconds and milliseconds cannot be told apart).
    """
    return _to_utc(value, name=name).isoformat()


def to_api_time_range(start: TimeLike, end: TimeLike) -> Tuple[str, str]:
    """
    Normalize a search window with :func:`to_api_time` and check its order.

    The comparison is between instants, so a ``start`` written in one
    timezone and an ``end`` written in another are ordered correctly.

    Raises:
        AstrocolibriConfigError: If either bound is invalid, or ``start`` is
            not strictly before ``end``.
    """
    start_utc = _to_utc(start, name="start")
    end_utc = _to_utc(end, name="end")
    if start_utc >= end_utc:
        raise AstrocolibriConfigError(
            f"start must be before end, got start={start_utc.isoformat()} "
            f"and end={end_utc.isoformat()} (UTC)."
        )
    return start_utc.isoformat(), end_utc.isoformat()


def _to_utc(value: TimeLike, *, name: str) -> datetime:
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str):
        text = value.strip()
        if text[-1:] in ("Z", "z"):
            text = text[:-1] + "+00:00"
        try:
            moment = datetime.fromisoformat(text)
        except ValueError:
            raise AstrocolibriConfigError(
                f"{name}: could not read {value!r} as an ISO 8601 timestamp. "
                f"Use a form like '2026-09-01T00:00:00Z'."
            ) from None
    else:
        raise AstrocolibriConfigError(
            f"{name} must be a timezone-aware datetime or an ISO 8601 string "
            f"with a timezone, got {type(value).__name__}."
        )

    if moment.tzinfo is None or moment.utcoffset() is None:
        raise AstrocolibriConfigError(
            f"{name} has no timezone, so the search window would depend on the "
            f"server's clock. Use an aware datetime such as "
            f"datetime.now(timezone.utc), or an ISO string ending in 'Z' or "
            f"'+00:00'."
        )
    return moment.astimezone(timezone.utc)
