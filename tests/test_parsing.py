"""
tests/test_parsing.py

Unit tests for coordinate and time normalization.

These are pure functions with no I/O, and they carry the SDK's most
error-prone logic. A mistake here does not fail loudly: it quietly moves a
cone search to the wrong part of the sky or a transient search to the wrong
night. So the cases below favour the inputs astronomers actually type, and
every boundary is pinned on both sides.

Run:
    pytest tests/test_parsing.py -v
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest
from astrocolibri._parsing import (
    parse_dec,
    parse_ra,
    parse_radius,
    to_api_time,
    to_api_time_range,
)
from astrocolibri.exceptions import AstrocolibriConfigError

# Crab Nebula, the running example: RA 05h34m31.94s, Dec +22d00m52.2s.
CRAB_RA_DEG = (5 + 34 / 60 + 31.94 / 3600) * 15
CRAB_DEC_DEG = 22 + 0 / 60 + 52.2 / 3600


class TestDecimalDegrees:
    def test_float_passes_through(self):
        assert parse_ra(83.63) == 83.63

    def test_int_becomes_float(self):
        result = parse_ra(83)
        assert result == 83.0
        assert isinstance(result, float)

    def test_numeric_string_is_degrees(self):
        # The API itself would reject "83.6" (it only attaches degrees to
        # JSON numbers), which is why the SDK converts before sending.
        assert parse_ra("83.6") == 83.6

    def test_numeric_string_is_stripped(self):
        assert parse_dec("  -22.5 ") == -22.5

    def test_scientific_notation(self):
        assert parse_radius("1e-3") == 0.001

    def test_magnitude_never_implies_hours(self):
        # 5.5 is degrees even though it looks like an hour angle.
        assert parse_ra(5.5) == 5.5
        assert parse_ra("5.5") == 5.5

    def test_numpy_scalar(self):
        np = pytest.importorskip("numpy")
        assert parse_ra(np.float32(83.5)) == pytest.approx(83.5)
        assert parse_dec(np.int64(-22)) == -22.0


class TestHourNotation:
    def test_hms_letters(self):
        assert parse_ra("05h34m31.94s") == pytest.approx(CRAB_RA_DEG)

    def test_hms_letters_with_spaces(self):
        assert parse_ra("5h 34m 31.94s") == pytest.approx(CRAB_RA_DEG)

    def test_uppercase_units(self):
        assert parse_ra("05H34M31.94S") == pytest.approx(CRAB_RA_DEG)

    def test_hours_only(self):
        assert parse_ra("12h") == 180.0

    def test_hours_and_minutes(self):
        assert parse_ra("12h30m") == pytest.approx(187.5)

    def test_colon_form_is_hms_for_ra(self):
        assert parse_ra("05:34:31.94") == pytest.approx(CRAB_RA_DEG)

    def test_whitespace_form_is_hms_for_ra(self):
        assert parse_ra("05 34 31.94") == pytest.approx(CRAB_RA_DEG)

    def test_two_component_colon_form(self):
        assert parse_ra("05:34.5") == pytest.approx((5 + 34.5 / 60) * 15)

    def test_degree_letters_are_degrees_for_ra(self):
        assert parse_ra("83d38m") == pytest.approx(83 + 38 / 60)


class TestDegreeNotation:
    def test_dms_letters(self):
        assert parse_dec("+22d00m52.2s") == pytest.approx(CRAB_DEC_DEG)

    def test_unicode_symbols(self):
        assert parse_dec("22°00′52.2″") == pytest.approx(CRAB_DEC_DEG)

    def test_ascii_quote_symbols(self):
        assert parse_dec("22°00'52.2\"") == pytest.approx(CRAB_DEC_DEG)

    def test_colon_form_is_dms_for_dec(self):
        # The same string that is 83.6° as a right ascension is 5.6° here.
        assert parse_dec("05:34:31.94") == pytest.approx(5 + 34 / 60 + 31.94 / 3600)

    def test_colon_form_is_dms_for_radius(self):
        assert parse_radius("00:30:00") == pytest.approx(0.5)

    def test_negative_dms(self):
        assert parse_dec("-22d00m52s") == pytest.approx(-(22 + 52 / 3600))

    def test_positive_colon_form(self):
        assert parse_dec("+41:16:09") == pytest.approx(41 + 16 / 60 + 9 / 3600)


class TestSign:
    """The classic sexagesimal bug: a sign on a zero degrees component."""

    def test_negative_zero_degrees_colon_form(self):
        # A per-component sign would read this as +0.5°: the minus sits on
        # "00", which is zero. The sign belongs to the whole angle.
        assert parse_dec("-00:30:00") == pytest.approx(-0.5)

    def test_negative_zero_degrees_unit_form(self):
        assert parse_dec("-0d30m") == pytest.approx(-0.5)

    def test_sign_separated_by_space(self):
        assert parse_dec("- 00:30:00") == pytest.approx(-0.5)


class TestArcminuteRadius:
    def test_prime_symbol(self):
        assert parse_radius("30′") == pytest.approx(0.5)

    def test_apostrophe(self):
        assert parse_radius("30'") == pytest.approx(0.5)

    def test_minutes_letter(self):
        assert parse_radius("30m") == pytest.approx(0.5)

    def test_minutes_above_sixty_without_a_larger_unit(self):
        # Only wraps at 60 when degrees precede it.
        assert parse_radius("90m") == pytest.approx(1.5)

    def test_arcseconds(self):
        assert parse_radius("45s") == pytest.approx(45 / 3600)

    def test_prime_arcminutes_are_unambiguous_for_ra(self):
        assert parse_ra("30′") == pytest.approx(0.5)


class TestRejectedNotation:
    @pytest.mark.parametrize(
        "value",
        [
            "5h34d",  # hours and degrees mixed
            "10:61:00",  # minutes out of range
            "10:30:60",  # seconds out of range
            "1d90m",  # minutes wrap once degrees precede them
            "1:2:3:4",  # too many components
            "05:34.5:10",  # fraction on a non-final component
            "5.5h30m",  # fraction on a non-final component
            "30s5m",  # units out of order
            "5h5h",  # unit repeated
            "05:34:31.94s",  # colon and unit notation mixed
            "5h34m31.94",  # trailing component without a unit
            "abc",
            "nan",
            "inf",
            "1e999",
        ],
    )
    def test_malformed_ra(self, value):
        with pytest.raises(AstrocolibriConfigError, match="ra"):
            parse_ra(value)

    def test_hours_rejected_for_dec(self):
        with pytest.raises(AstrocolibriConfigError, match="only right ascension"):
            parse_dec("5h")

    def test_hours_rejected_for_radius(self):
        with pytest.raises(AstrocolibriConfigError, match="only right ascension"):
            parse_radius("1h")

    def test_bare_minutes_are_ambiguous_for_ra(self):
        # "30m" could be 7.5° (minutes of time) or 0.5° (arcminutes).
        with pytest.raises(AstrocolibriConfigError, match="ambiguous"):
            parse_ra("30m")

    def test_mixed_notation_message_names_the_problem(self):
        with pytest.raises(AstrocolibriConfigError, match="mixes hour and degree"):
            parse_ra("5h34d")

    @pytest.mark.parametrize("value", ["", "   "])
    def test_empty_string(self, value):
        with pytest.raises(AstrocolibriConfigError, match="empty"):
            parse_dec(value)

    def test_bool_is_not_an_angle(self):
        # bool subclasses int, so True would otherwise be read as 1°.
        with pytest.raises(AstrocolibriConfigError, match="bool"):
            parse_radius(True)

    @pytest.mark.parametrize("value", [None, [83.6], {"ra": 83.6}])
    def test_other_types(self, value):
        with pytest.raises(AstrocolibriConfigError, match="must be a number"):
            parse_ra(value)

    def test_astropy_style_object_gets_a_hint(self):
        class Longitude:
            deg = 83.6

        with pytest.raises(AstrocolibriConfigError, match=r"\.deg"):
            parse_ra(Longitude())

    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
    def test_non_finite_numbers(self, value):
        with pytest.raises(AstrocolibriConfigError, match="finite"):
            parse_dec(value)

    def test_error_echoes_the_input(self):
        with pytest.raises(AstrocolibriConfigError, match="10:61:00"):
            parse_ra("10:61:00")


class TestRanges:
    def test_ra_lower_bound_inclusive(self):
        assert parse_ra(0) == 0.0

    def test_ra_upper_bound_exclusive(self):
        assert parse_ra(359.99) == 359.99
        with pytest.raises(AstrocolibriConfigError, match=r"\[0, 360\)"):
            parse_ra(360.0)

    def test_ra_24h_is_out_of_range(self):
        with pytest.raises(AstrocolibriConfigError, match="from '24h'"):
            parse_ra("24h")

    def test_ra_negative(self):
        with pytest.raises(AstrocolibriConfigError):
            parse_ra(-0.1)

    def test_dec_bounds_inclusive(self):
        assert parse_dec(90) == 90.0
        assert parse_dec(-90) == -90.0

    def test_dec_out_of_range(self):
        with pytest.raises(AstrocolibriConfigError, match=r"\[-90, 90\]"):
            parse_dec(90.1)

    def test_radius_upper_bound_inclusive(self):
        assert parse_radius(180) == 180.0

    @pytest.mark.parametrize("value", [0, -1, 180.1])
    def test_radius_out_of_range(self, value):
        with pytest.raises(AstrocolibriConfigError, match=r"\(0, 180\]"):
            parse_radius(value)


class TestApiTime:
    def test_aware_utc_datetime(self):
        moment = datetime(2026, 9, 1, tzinfo=timezone.utc)
        assert to_api_time(moment, name="start") == "2026-09-01T00:00:00+00:00"

    def test_other_timezone_is_converted_not_relabelled(self):
        cest = timezone(timedelta(hours=2))
        moment = datetime(2026, 9, 1, 2, 0, tzinfo=cest)
        assert to_api_time(moment, name="start") == "2026-09-01T00:00:00+00:00"

    def test_z_suffix_string(self):
        assert (
            to_api_time("2026-09-01T00:00:00Z", name="start")
            == "2026-09-01T00:00:00+00:00"
        )

    def test_offset_string_is_converted(self):
        result = to_api_time("2026-09-01T02:00:00+02:00", name="start")
        assert result == "2026-09-01T00:00:00+00:00"

    def test_never_emits_z(self):
        # The API parses with datetime.fromisoformat, which rejects "Z" on
        # Python < 3.11.
        assert "Z" not in to_api_time("2026-09-01T00:00:00Z", name="start")

    def test_microseconds_survive(self):
        moment = datetime(2026, 9, 1, 0, 0, 0, 123456, tzinfo=timezone.utc)
        assert to_api_time(moment, name="end") == "2026-09-01T00:00:00.123456+00:00"

    def test_naive_datetime_is_rejected(self):
        # Guessing would be worse than refusing: datetime.utcnow() and
        # datetime.now() both produce naive values, in different timezones.
        with pytest.raises(AstrocolibriConfigError, match="no timezone"):
            to_api_time(datetime(2026, 9, 1), name="start")

    def test_naive_rejection_names_the_fix(self):
        with pytest.raises(AstrocolibriConfigError, match=r"timezone\.utc"):
            to_api_time(datetime(2026, 9, 1), name="start")

    @pytest.mark.parametrize("value", ["2026-09-01T00:00:00", "2026-09-01"])
    def test_naive_string_is_rejected(self, value):
        with pytest.raises(AstrocolibriConfigError, match="no timezone"):
            to_api_time(value, name="start")

    @pytest.mark.parametrize("value", ["not-a-date", "", "   "])
    def test_unparseable_string(self, value):
        with pytest.raises(AstrocolibriConfigError, match="ISO 8601"):
            to_api_time(value, name="end")

    @pytest.mark.parametrize("value", [1767225600, 1767225600000.0, None])
    def test_other_types_are_rejected(self, value):
        # An epoch number is ambiguous: the API's own timestamps are in
        # milliseconds, most Python code uses seconds.
        with pytest.raises(AstrocolibriConfigError, match="timezone-aware datetime"):
            to_api_time(value, name="start")

    def test_error_names_the_parameter(self):
        with pytest.raises(AstrocolibriConfigError, match="^end"):
            to_api_time("not-a-date", name="end")


class TestApiTimeRange:
    def test_valid_range(self):
        assert to_api_time_range("2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z") == (
            "2026-09-01T00:00:00+00:00",
            "2026-09-02T00:00:00+00:00",
        )

    def test_equal_bounds_rejected(self):
        with pytest.raises(AstrocolibriConfigError, match="before end"):
            to_api_time_range("2026-09-01T00:00:00Z", "2026-09-01T00:00:00Z")

    def test_reversed_bounds_rejected(self):
        with pytest.raises(AstrocolibriConfigError, match="before end"):
            to_api_time_range("2026-09-02T00:00:00Z", "2026-09-01T00:00:00Z")

    def test_compares_instants_not_strings(self):
        # 01:00 at +02:00 is 23:00 UTC the previous day, so this range is
        # valid even though the start string sorts after the end string.
        start, end = to_api_time_range(
            "2026-09-01T01:00:00+02:00", "2026-09-01T00:00:00Z"
        )
        assert start == "2026-08-31T23:00:00+00:00"
        assert end == "2026-09-01T00:00:00+00:00"

    def test_invalid_bound_is_named(self):
        with pytest.raises(AstrocolibriConfigError, match="^start"):
            to_api_time_range(datetime(2026, 9, 1), "2026-09-02T00:00:00Z")
