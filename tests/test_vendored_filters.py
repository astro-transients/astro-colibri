"""
tests/test_vendored_filters.py

The SDK filters broker alerts with a verbatim copy of the Astro-COLIBRI
API's filter engine (astrocolibri/_filters/), so a filter means the same in
the SDK as in /latest_transients.

- The copy must equal the API source. In the monorepo, a change to the API
  filters fails here until `python sync_api_filters.py` has been re-run. The
  check skips where the API source is absent (public repository, PyPI).
- The engine's semantics that broker filtering relies on, which subscribers
  see through EventFilter.

Run:
    pytest tests/test_vendored_filters.py -v
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from astrocolibri._filters.filter import (
    BaseClassExceptionFilterParsing,
    BaseFilter,
    create_filter_from_dict,
)

SDK_ROOT = Path(__file__).resolve().parents[1]
SYNC_SCRIPT = SDK_ROOT / "sync_api_filters.py"


def _sync_module():
    spec = importlib.util.spec_from_file_location("sync_api_filters", SYNC_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCopyMatchesTheApi:
    @pytest.fixture
    def sync(self):
        if not SYNC_SCRIPT.exists():
            pytest.skip("sync_api_filters.py lives in the Astro-COLIBRI monorepo only")
        module = _sync_module()
        if not module.API_CONTROLLER.is_dir():
            pytest.skip("needs the API source from the Astro-COLIBRI monorepo")
        return module

    def test_every_copy_equals_the_api_source(self, sync):
        assert sync.outdated() == [], (
            "astrocolibri/_filters/ differs from the API filters; run "
            "`python sync_api_filters.py` in colibri_client/"
        )

    def test_a_copy_is_the_api_file_behind_a_header(self, sync):
        for name in sync.MODULES:
            api_source = (sync.API_CONTROLLER / name).read_text(encoding="utf-8")
            copy = (sync.VENDOR_DIR / name).read_text(encoding="utf-8")
            assert copy.startswith("# GENERATED FILE - DO NOT EDIT.")
            assert copy.endswith(api_source)


def evaluate(spec, event):
    return BaseFilter.create_from_dict(json.loads(json.dumps(spec))).apply_filter(event)


def field(name, operation, value, type_field="string", **extra):
    return {
        "type": "FieldSpecification",
        "field": name,
        "operation": operation,
        "value": value,
        "typeField": type_field,
        **extra,
    }


class TestEngineSemantics:
    def test_string_comparison_ignores_case(self):
        assert evaluate(field("observatory", "==", "Fermi"), {"observatory": "fermi"})
        assert not evaluate(
            field("observatory", "!=", "FERMI"), {"observatory": "fermi"}
        )

    def test_a_missing_number_reads_as_minus_one(self):
        # The placeholder the event model uses for an unset number.
        assert evaluate(field("redshift", ">", "-2", "float"), {})
        assert not evaluate(field("redshift", ">=", "0", "float"), {})

    def test_a_missing_string_reads_as_empty(self):
        assert evaluate(field("classification", "==", ""), {})

    def test_array_index_into_the_credible_areas(self):
        spec = field("map_areas", "<", "100", "array_float", arrayIndex="90")
        assert evaluate(spec, {"map_areas": {"50": 20.0, "90": 80.0}})
        assert evaluate(spec, {"map_areas": '{"50": 20.0, "90": 80.0}'})
        assert not evaluate(spec, {"map_areas": {"50": 20.0, "90": 800.0}})
        assert not evaluate(spec, {"map_areas": ""})

    def test_photometry_path(self):
        spec = field("photometry.ztf_g.last.mag", "<=", "18", "maps_float")
        bright = {"photometry": {"ztf_g": {"last": {"mag": 17.5}}}}
        faint = {"photometry": {"ztf_g": {"last": {"mag": 19.5}}}}
        assert evaluate(spec, bright)
        assert not evaluate(spec, faint)
        assert not evaluate(spec, {"photometry": {}})

    def test_contains_and_array(self):
        contains = {
            "type": "ContainsSpecification",
            "field": "classification",
            "value": "ia",
        }
        array = {"type": "ArraySpecification", "field": "follow_up", "value": "hess"}
        assert evaluate(contains, {"classification": "SN Ia-91T"})
        assert evaluate(array, {"follow_up": ["hess", "rapas"]})
        # Only a real list counts: the JSON text of one does not.
        assert not evaluate(array, {"follow_up": '["hess"]'})

    def test_numeric_string_drops_the_unit(self):
        spec = {
            "type": "NumericStringSpecification",
            "field": "dm",
            "operation": ">",
            "value": 300,
        }
        assert evaluate(spec, {"dm": "512.3 pc cm^-3"})
        assert not evaluate(spec, {"dm": ""})

    def test_visibility_window_on_the_declination(self):
        spec = {
            "type": "MaxAbsoluteDifferenceSpecification",
            "field": "dec",
            "typeField": "float",
            "value": -23.27,
            "range": 60,
        }
        assert evaluate(spec, {"dec": 12.0})
        assert not evaluate(spec, {"dec": 45.0})
        assert not evaluate(spec, {})

    def test_composites_and_switched_off_filters(self):
        grb = field("type", "==", "grb")
        swift = field("observatory", "==", "swift")
        event = {"type": "grb", "observatory": "fermi"}
        assert not evaluate({"type": "AndSpecification", "specs": [grb, swift]}, event)
        assert evaluate({"type": "OrSpecification", "specs": [grb, swift]}, event)
        assert evaluate({"type": "NotSpecification", "spec": swift}, event)
        # A switched-off filter answers its default state, whatever the event.
        off = {**swift, "isActivated": False, "defaultState": True}
        assert evaluate({"type": "AndSpecification", "specs": [grb, off]}, event)

    def test_saved_app_configuration_combines_into_one_spec(self):
        def system(spec, activated=True, default_state=False):
            return {
                "isActivated": activated,
                "defaultState": default_state,
                "filter": spec,
            }

        configuration = {
            "obs": [system(field("observatory", "==", "fermi"))],
            "type": [system(field("type", "==", "grb"))],
            "general": [system({"type": "TrueSpecification"}, False, True)],
        }
        spec = create_filter_from_dict(configuration)
        assert evaluate(spec, {"observatory": "fermi", "type": "grb"})
        assert not evaluate(spec, {"observatory": "swift", "type": "grb"})

    @pytest.mark.parametrize(
        "spec",
        [
            {"type": "NoSuchSpecification"},
            {"isActivated": True},
            field("ra", "~", "1", "float"),
            field("ra", "<", "1", "complex"),
            {"type": "AndSpecification"},
        ],
        ids=["unknown-type", "no-type", "bad-operator", "bad-field-type", "no-specs"],
    )
    def test_invalid_specifications_raise_a_parsing_error(self, spec):
        with pytest.raises((BaseClassExceptionFilterParsing, KeyError)):
            BaseFilter.create_from_dict(spec)
