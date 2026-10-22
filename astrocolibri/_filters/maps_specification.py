# GENERATED FILE - DO NOT EDIT.
# Copied verbatim from Colibri_v2/colibri_flask_api/app/api_folder/controller/maps_specification.py
# by colibri_client/sync_api_filters.py. Change the API file, then re-run
# `python sync_api_filters.py` in colibri_client/.

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Union


def get_converted_field_value(
    colibri_event: Dict[str, Any], field_name: str, type_field: str, sep="."
) -> Optional[Union[float, int]]:
    """
    Computes a derived field value from a Colibri event based on the specified type.

    Parameters
    ----------
    colibri_event : dict
        The input event data.
    field_name : str
        A field path string or a formatted specification string.
    type_field : str
        The type of conversion or computation to apply.

    Returns
    -------
    Optional[float or int]
        The computed or parsed value, or None if computation fails or input is invalid.
    """
    if type_field == "maps_fast_rising_transient":
        raw_value = get_magnitude_slope_per_day(colibri_event, field_name, sep)
        min_slope = get_min_value(raw_value)
        return abs(min_slope) if min_slope is not None and min_slope < 0 else None

    elif type_field == "maps_fast_fading_transient":
        raw_value = get_magnitude_slope_per_day(colibri_event, field_name, sep)
        # ---Walrus operator (compact, and advanced for pthon3.8+) ---
        # return greatest_slope if (greatest_slope := get_max_value(raw_value)) is not None and greatest_slope > 0 else None
        greatest_slope = get_max_value(raw_value)
        return (
            greatest_slope
            if greatest_slope is not None and greatest_slope > 0
            else None
        )

    elif type_field == "date_range_difference":
        raw_value = get_delta_time_between_fields(colibri_event, field_name, sep)

        if not raw_value:
            return None
        return get_max_value(raw_value)

    elif type_field == "maps_float":
        raw_value = get_nested_event_value(colibri_event, field_name, sep)
        return _try_parse_float(raw_value)

    elif type_field == "maps_int":
        raw_value = get_nested_event_value(colibri_event, field_name, sep)
        if raw_value is None:
            return None
        try:
            return int(raw_value)
        except (ValueError, TypeError):
            return None

    elif type_field == "maps_value_min":
        raw_value = get_nested_event_value(colibri_event, field_name, sep)
        if isinstance(raw_value, list):
            return get_min_value(raw_value)
        return _try_parse_float(raw_value)

    elif type_field == "maps_value_max":
        raw_value = get_nested_event_value(colibri_event, field_name, sep)
        if isinstance(raw_value, list):
            return get_max_value(raw_value)
        return _try_parse_float(raw_value)

    elif type_field == "maps_days_ago":
        raw_value = get_nested_event_value(colibri_event, field_name, sep)
        return days_ago(raw_value)

    elif type_field == "maps_days_since_earliest_date":
        raw_value = get_nested_event_value(colibri_event, field_name, sep)
        if isinstance(raw_value, list):
            earliest = get_earliest_date(raw_value)
            return days_ago(earliest)
        return days_ago(raw_value)

    elif type_field == "maps_days_since_latest_date":
        raw_value = get_nested_event_value(colibri_event, field_name, sep)
        if isinstance(raw_value, list):
            latest = get_latest_date(raw_value)
            return days_ago(latest)
        return days_ago(raw_value)

    elif type_field == "maps_days_since_peak_date":
        raw_value = get_nested_event_value(colibri_event, field_name, sep)
        if isinstance(raw_value, list):
            peak_date = get_latest_date(raw_value)
            return days_ago(peak_date)
        return days_ago(raw_value)

    else:
        return None


def get_nested_event_value(data: Any, path: str, sep: str = ".") -> Any:
    """
    Return the value at *path* in *data*.

    • Dot-separated keys, '*' wildcards, list indices
    • Falls back to "value" in dicts when needed
    • Returns None if the path can’t be resolved

    Parameters
    ----------
    data : Any
        The root object (dict, list, or scalar).
    path : str
        Dot-separated path (supports ``*`` wildcards).
    sep  : str, default ``"."``
        Path separator; change it if your keys contain dots.

    Returns
    -------
    any
        The nested value found at the specified path, or `None` if not found or invalid.

    Examples
    --------
    >>> data = {'photometry': {'ztf_g': {'last': {'mag': 17.3}}}}
    >>> get_nested_event_value(data, 'photometry.ztf_g.last.mag')
    17.3

    >>> data = {
    ...     "photometry": {
    ...         "ztf_g": {"last": {"mag": 17.3}},
    ...         "ztf_r": {"last": {"mag": 18.1}},
    ...         "ATLAS_o": {"last": {"mag": 16.2}},
    ...     }
    ... }
    >>> get_nested_event_value(data, "photometry.*.last.mag")
    [17.3, 18.1, 16.2]
    """
    keys = path.split(sep)
    return _retrieve_json_path(data, keys)


def _retrieve_json_path(current: Any, keys: List[str]) -> Any:
    """
    Recursively navigate *current* (a nested ``dict``/``list``/scalar)
    following *keys* until the requested value is reached.

    Special description
    -------------------
    • **Wildcard ``*``**
      When the current container is a ``dict`` or a ``list`` and the
      next key is ``*``, the function walks through *all* children and
      concatenates the results in a single flat list.

    • **Value fallback**
      If *current* is a ``dict`` that **doesn’t** contain the requested
      key but **does** contain a ``"value"`` field (sometimes included in colibri),
      the search falls.

    • **List indices**
      Numerical keys are interpreted as positional indices when the
      current object is a list.

    Parameters
    ----------
    current : any
           The current object being processed (dict, list, or other).
    keys : list of str
        The remaining path keys to follow.

    Returns
    -------
    Any
        The found value.
        A flattened ``list`` of values if one or more wildcards were
          used.
        ``None`` if the path is invalid.
    """

    if not keys:
        return current

    key, *remaining = keys

    # ---------- Value-fallback ---------
    # this is only useful in the frontend case,
    # where a value is the key for all the parameters included "photometry"
    if isinstance(current, dict) and key not in current and "value" in current:
        current = current["value"]
        if current is None:
            return None

    # ---------- Wildcard ---------------
    if key == "*":
        results: List[Any] = []

        iterable: Optional[Iterable[Any]]
        if isinstance(current, list):
            iterable = current
        elif isinstance(current, dict):
            iterable = current.values()
        else:
            iterable = None

        if iterable is None:
            return None

        for item in iterable:
            res = _retrieve_json_path(item, remaining)
            if res is not None:
                results.extend(res if isinstance(res, list) else [res])
        return results

    # ---------- Dict -------------------
    if isinstance(current, dict) and key in current:
        return _retrieve_json_path(current[key], remaining)

    # ---------- List -------------------
    if isinstance(current, list):
        try:
            idx = int(key)
            if 0 <= idx < len(current):
                return _retrieve_json_path(current[idx], remaining)
        except ValueError:
            return None

    # ---------- Invalid path -----------
    return None


def _try_parse_float(value: Any) -> Optional[float]:
    """
    Attempt to convert a dynamic value to a float.

    This function tries to safely parse values that might be integers, floats,
    or strings representing numbers. If the conversion fails, it returns None.

    Parameters
    ----------
    value : any
        The input value to convert (e.g., int, float, str).

    Returns
    -------
    float or None
        The float representation of the input if successful, otherwise None.

    Examples
    --------
    >>> _try_parse_float(42)
    42.0

    >>> _try_parse_float("3.14")
    3.14

    >>> _try_parse_float("not a number")
    None

    >>> _try_parse_float(None)
    None
    """
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (ValueError, TypeError):
        return None


def _parse_and_filter_doubles(values: List[Any]) -> List[float]:
    """
    Convert a list of dynamic values to floats, filtering out non-numeric entries.

    Parameters
    ----------
    values : list of any
        A list of values (e.g., ints, floats, numeric strings) to parse.

    Returns
    -------
    list of float
        A list of successfully parsed float values.

    Examples
    --------
    >>> _parse_and_filter_doubles([1, "2.5", None, "abc", 4])
    [1.0, 2.5, 4.0]

    >>> _parse_and_filter_doubles(["NaN", "3", "bad", 5])
    [3.0, 5.0]
    """
    return [
        v
        for v in (_try_parse_float(val) for val in values)
        if v is not None and not math.isnan(v)
    ]


def get_min_value(values: List[Any]) -> Optional[float]:
    """
    Return the minimum numeric value from a list of dynamic values.

    We try to convert each element in the input list to a float,
    filtering out invalid entries such as None, non-numeric strings, and NaN.
    It then returns the largest valid float value. If no valid numeric values
    are found, the function returns None.

    Parameters
    ----------
    values : list of any
        A list containing values of type int, float, or numeric strings.

    Returns
    -------
    float or None
        The smallest float value, or None if no valid values are found.

    Examples
    --------
    >>> get_min_value([3, "2.5", None, "abc"])
    2.5

    >>> get_min_value(["NaN", "bad", None])
    None
    """
    parsed = _parse_and_filter_doubles(values)
    return min(parsed) if parsed else None


def get_max_value(values: List[Any]) -> Optional[float]:
    """
    Return the maximum numeric value from a list of dynamic values.

    We try to convert each element in the input list to a float,
    filtering out invalid entries such as None, non-numeric strings, and NaN.
    It then returns the largest valid float value. If no valid numeric values
    are found, the function returns None.

    Parameters
    ----------
    values : list of any
        A list containing values of type int, float, or numeric strings.

    Returns
    -------
    float or None
        The largest float value, or None if no valid values are found.

    Examples
    --------
    >>> get_max_value([3, "2.5", None, "abc"])
    3.0

    >>> get_max_value(["NaN", "bad", None])
    None

    >>> get_max_value(["5.5", 1, 3.2])
    5.5
    """
    parsed = _parse_and_filter_doubles(values)
    return max(parsed) if parsed else None


def get_value_difference(a: Any, b: Any) -> Optional[List[Optional[float]]]:
    """
    Compute the difference (b - a), element-wise if inputs are lists.

    Parameters
    ----------
    a : Any
        A single numeric value or a list of values (int, float, str, or None).
    b : Any
        A single numeric value or a list of values (int, float, str, or None).

    Returns
    -------
    list of Optional[float] or None
        A list of differences (b - a), or None if the inputs are mismatched or fully invalid.
        Individual differences will be None if either element is not numeric.

    Examples
    --------
    >>> get_value_difference(2, 5)
    [3.0]

    >>> get_value_difference(["1.5", "2.5"], [3, 5])
    [1.5, 2.5]

    >>> get_value_difference([None, "2.0"], [5, "3.0"])
    [None, 1.0]

    >>> get_value_difference([1, 2], None)
    None
    """
    a_list = _to_list(a)
    b_list = _to_list(b)
    length = min(len(a_list), len(b_list))
    results = []
    for i in range(length):
        x = _try_parse_float(a_list[i])
        y = _try_parse_float(b_list[i])
        results.append(y - x if x is not None and y is not None else None)

    return results


def get_value_division(
    numerator: Any, denominator: Any
) -> Optional[List[Optional[float]]]:
    """
    Compute the division b / a, element-wise if inputs are lists.

    Parameters
    ----------
    numerator : Any
        A single numeric value or a list (divisor).
    denominator : Any
        A single numeric value or a list (dividend).

    Returns
    -------
    list of Optional[float] or None
        A list of division results, or None if inputs are invalid or division by zero occurs.

    Examples
    --------
    >>> get_value_division(2, 10)
    [5.0]

    >>> get_value_division(["2", "5"], [10, 20])
    [5.0, 4.0]

    >>> get_value_division(0, 3)
    [None]
    """
    num_list = _to_list(numerator)
    den_list = _to_list(denominator)

    length = min(len(num_list), len(den_list))

    results = []
    for i in range(length):
        n = _try_parse_float(num_list[i])
        d = _try_parse_float(den_list[i])
        if n is None or d is None or d == 0:
            results.append(None)
        else:
            result = n / d
            if result == float("inf") or result == float("-inf"):
                results.append(None)
            else:
                results.append(result)

    return results


def _parse_date(input_value: Any) -> Optional[datetime]:
    """
    Parse a dynamic input into a datetime object.

    Parameters
    ----------
    input_value : Any
        A datetime object or a string in ISO format (e.g., '2023-01-01T12:30:00').

    Returns
    -------
    datetime or None
        Parsed datetime object, or None if parsing fails.

    Examples
    --------
    >>> _parse_date("2025-05-13T17:16:00")
     -datetime.datetime(2025, 5, 13, 17, 16)

    >>> _parse_date("2025-05")
    None
    """
    if isinstance(input_value, datetime):
        return input_value
    try:
        return datetime.fromisoformat(str(input_value))
    except Exception:
        return None


def days_ago(date: Any) -> Optional[float]:
    """
    Compute the number of days between the input date and now.

    Parameters
    ----------
    date : Any
        A datetime object or a string in ISO format.

    Returns
    -------
    float or None
        Number of days as a float, or None if parsing fails.

    Examples
    --------
    >>> days_ago("2025-05-13T00:00:00")  # Result will depend on current date
     0.7240361227546296  # example output

    >>> days_ago("2025-05-45T00:00:00")
    None
    """
    parsed_date = _parse_date(date)
    if not parsed_date:
        return None
    delta = datetime.now() - parsed_date
    return delta.total_seconds() / 86400  # seconds in a day


def _parse_and_sort_dates(dates: List[Any]) -> List[datetime]:
    """
    Parses and sorts a list of dates.

    Args:
        dates:  A list containing datetime objects or date/time strings (e.g., "2025-01-01T10:00:00")

    Returns:
        A sorted list of datetime objects.

    Examples
    --------
    >>> _parse_and_sort_dates(["2023-05-01T14:00:00", datetime(2022, 1, 1)])
    [datetime.datetime(2022, 1, 1, 0, 0), datetime.datetime(2023, 5, 1, 14, 0)]

    >>> _parse_and_sort_dates(["invalid", None])
    []
    """
    parsed = [d for d in (_parse_date(dt) for dt in dates) if d is not None]
    return sorted(parsed)


def get_latest_date(dates: List[Any]) -> Optional[datetime]:
    """
    Return the most recent (latest) valid date from a list of values.

    Parameters
    ----------
    dates : list of any
        A list of datetime objects or ISO-format date strings.

    Returns
    -------
    datetime or None
        The most recent valid datetime, or None if no valid values are found.

    Examples
    --------
    >>> get_latest_date(["2025-05-13T17:36:00", "2022-01-01", "2023-06-15T10:30:00"])
    datetime.datetime(2025, 5, 13, 17, 36)

    >>> get_latest_date(["bad date", None])
    None
    """
    parsed = _parse_and_sort_dates(dates)
    return parsed[-1] if parsed else None


def get_earliest_date(dates: List[Any]) -> Optional[datetime]:
    """
    Returns the earliest (oldest) date from a list.
    Args:
        dates: List of datetime objects or ISO-format strings.
    Returns:
        The oldest datetime or None if no valid dates.

    Examples
    --------
    >>> get_earliest_date(["2025-05-13T17:40:00", "2022-01-01"])
    datetime.datetime(2022, 1, 1, 0, 0)

    >>> get_earliest_date(["invalid", None])
    None
    """
    parsed = _parse_and_sort_dates(dates)
    return parsed[0] if parsed else None


def parse_field_map_for_time_and_mag(input_str: str) -> Dict[str, List[str]]:
    """
    Parses a field specification string with 'times' and 'data' keys.

    Parameters
    ----------
    input_str : str
        JSON-like string with keys 'times' and 'data'.
    Returns
    -------
    dict
        Dictionary with lists under 'times' and 'data'.

    Examples
    --------
    >>> parse_field_map_for_time_and_mag("{'times': ['t1', 't2'], 'data': ['m1', 'm2']}")
    {'times': ['t1', 't2'], 'data': ['m1', 'm2']}

    >>> parse_field_map_for_time_and_mag("invalid")
    {'times': [], 'data': []}

    >>> parse_field_map_for_time_and_mag("{'times': 'wrong type'}")
    {'times': [], 'data': []}
    """

    def ensure_list(x: Any) -> List[str]:
        return list(x) if isinstance(x, list) else []

    if not input_str or not isinstance(input_str, str):
        return {"times": [], "data": []}

    try:
        formatted = input_str.replace("'", '"')
        parsed = json.loads(formatted)
        return {
            "times": ensure_list(parsed.get("times")),
            "data": ensure_list(parsed.get("data")),
        }
    except (json.JSONDecodeError, TypeError, AttributeError):
        return {"times": [], "data": []}


def get_magnitude_slope_per_day(
    colibri_event: Dict[str, Any], field_name: str, sep="."
) -> Optional[List[Optional[float]]]:
    """
    Compute the slope of magnitude change per day between two time points in a Colibri event.

    This function extracts nested time and magnitude fields from a Colibri event,
    computes the time difference (in days) and magnitude difference, and returns
    the slope(s) as delta_mag / delta_time.

    Parameters
    ----------
    colibri_event : dict
        A nested dictionary containing photometric data (typically from Colibri).
    field_name : str
        A JSON-like string with keys "times" and "data", indicating which fields to extract.

    Returns
    -------
    list of Optional[float] or None
        List of slopes (delta_mag / delta_time), or None if data is incomplete or invalid.

    Examples
    --------
    >>> field_map = "{'times': ['photometry.ztf_g.first.time', 'photometry.ztf_g.last.time'],
                      'data': ['photometry.ztf_g.first.mag', 'photometry.ztf_g.last.mag']}"
    """
    field_map = parse_field_map_for_time_and_mag(field_name)
    if len(field_map) < 2:
        return None

    time_fields = field_map.get("times")
    mag_fields = field_map.get("data")
    if not time_fields or not mag_fields:
        return None

    time_start = get_nested_event_value(colibri_event, time_fields[0], sep)
    time_end = get_nested_event_value(colibri_event, time_fields[-1], sep)
    mag_start = get_nested_event_value(colibri_event, mag_fields[0], sep)
    mag_end = get_nested_event_value(colibri_event, mag_fields[-1], sep)

    # make the difference between each pair dates and magnitudes
    delta_day = days_between_dates(time_start, time_end)
    delta_mag = get_value_difference(mag_start, mag_end)

    if delta_day is None or delta_mag is None:
        return None

    return get_value_division(delta_mag, delta_day)


def _to_list(x: Union[Any, List[Any]]) -> List[Any]:
    """Convert x to a list if it isn't already."""
    if isinstance(x, list):
        return x
    return [x]


def get_delta_time_between_fields(
    colibri_event: Dict[str, Any], field_name: str, sep: str = "."
) -> Optional[List[Optional[float]]]:
    """
    Returns the absolute time difference (in days) between two nested datetime fields.

    Parameters
    ----------
    colibri_event : dict
        A dictionary representing the Colibri event.
    field_name : str
        A string like "{'photometry.first.time', 'photometry.last.time'}"

    sep  : str, default ``"."``
        Path separator; change it if your keys contain other like "/" etc.

    Returns
    -------
    list of Optional[float] or None
        A list containing the absolute time difference in days,
        or None if fields are missing or invalid.
    """
    field_map = _parse_bracketed_string(field_name)

    if len(field_map) < 2:
        return None

    time_start = get_nested_event_value(colibri_event, field_map[0], sep)
    time_end = get_nested_event_value(colibri_event, field_map[-1], sep)

    return days_between_dates(time_start, time_end)


def days_between_dates(start: Any, end: Any) -> Optional[List[Optional[float]]]:
    """
    Compute the absolute difference in days between two date values or lists of date values.

    Parameters
    ----------
    start : any
        Single datetime or list of datetime-compatible values.
    end : any
        Single datetime or list of datetime-compatible values.

    Returns
    -------
    list of Optional[float] or None
        Time differences in days, or None if parsing fails.

    Examples
    --------
    >>> days_between_dates("2025-05-13", "2025-05-15")
    [2.0]

    >>> days_between_dates(["2025-05-13", "2024-05-10"], ["2025-05-15", "2024-05-15"])
    [2.0, 5.0]

    >>> days_between_dates("invalid", "2024-05-03")
    None

    >>> days_between_dates(["2025-05-13", "bad"], ["2025-05-15", "2024-05-06"])
    [2.0, None]
    """

    # Convert all to lists for generality
    start_list, end_list = _to_list(start), _to_list(end)

    # If one is shorter, zip to shortest
    length = min(len(start_list), len(end_list))

    results = []
    for i in range(length):
        s, e = _parse_date(start_list[i]), _parse_date(end_list[i])
        if s is not None and e is not None:
            results.append(abs((e - s).total_seconds()) / 86400)
        else:
            results.append(None)

    return results


def _to_list(x: Union[Any, List[Any]]) -> List[Any]:
    """Convert x to a list if it isn't already."""
    if isinstance(x, list):
        return x
    return [x]


def _parse_bracketed_string(input_str: str) -> List[str]:
    """
    Convert a bracketed string like "{'a.b', 'c.d'}" to a list of strings.

    Examples
    --------
    >>> _parse_bracketed_string("{'a.b', 'c.d'}")
    ['a.b', 'c.d']

    >>> _parse_bracketed_string("{\"a.b\", \"c.d\"}")
    ['a.b', 'c.d']

    >>> _parse_bracketed_string("{ 'a', 'c.d }")
    ['a', 'c.d']

    >>> _parse_bracketed_string("{}")
    []
    """
    if input_str is None:
        return []
    if not isinstance(input_str, str):
        # Log warning or debug info here if you want
        return []
    cleaned = re.sub(r"[{}]", "", input_str)
    parts = [p.strip().strip("'\"").strip() for p in cleaned.split(",") if p.strip()]

    return parts
