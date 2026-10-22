"""
tests/test_voevent_roundtrip.py

The broker publishes every alert twice: as Astro-COLIBRI JSON and as a
VOEvent made from it by scripts/database/VoEvents/AstroCOLIBRI_to_VoEvent.py.
VOEvent.to_colibri_event() undoes that conversion so that one EventFilter
works on both topics. These tests hold the two directions together:

- an event with every attribute of the API's event model comes back
  unchanged, apart from the fields the VOEvent deliberately leaves out;
- every filter of the app's default configuration gives the same answer on
  an event and on its round trip, which is the promise made to subscribers;
- the sample events cover the whole event model, so a field added to the
  model fails here until the converter (and this file) say what happens to it.

They need the converter, the API's event model and the app's filter
configuration from the Astro-COLIBRI monorepo, and skip without them (in the
public SDK repository and the PyPI source distribution).

Run:
    pytest tests/test_voevent_roundtrip.py -v
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest
from astrocolibri import parse_voevent
from astrocolibri._filters.filter import BaseFilter, create_filter_from_dict

MONOREPO = Path(__file__).resolve().parents[2]
CONVERTER = MONOREPO / "scripts/database/VoEvents/AstroCOLIBRI_to_VoEvent.py"
EVENT_MODEL = MONOREPO / "colibri_flask_api/app/api_folder/models/voevents_db.py"
APP_FILTERS = MONOREPO / "colibri_frontend/assets/configuration"

if not (CONVERTER.exists() and EVENT_MODEL.exists() and APP_FILTERS.is_dir()):
    pytest.skip(
        "needs the Astro-COLIBRI monorepo (converter, event model, app filters)",
        allow_module_level=True,
    )

#: Fields the VOEvent leaves out on purpose.
NOT_CARRIED = {
    # Large: the API serves them through optional_parameters.
    "gw_contours",
    "archive",
    # Events carrying it are withheld from the broker altogether.
    "confidential_observatory",
}


def _load_converter():
    spec = importlib.util.spec_from_file_location("astrocolibri_to_voevent", CONVERTER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.convert_event_to_voevent


convert_event_to_voevent = _load_converter()


def _model_defaults() -> Dict[str, Any]:
    """``Voevent.__init__``'s attributes and their default values, read with ast."""
    tree = ast.parse(EVENT_MODEL.read_text(encoding="utf-8"))
    model = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Voevent"
    )
    init = next(
        node
        for node in model.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    defaults = {}
    for statement in init.body:
        if isinstance(statement, ast.Assign):
            for target in statement.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                ):
                    defaults[target.attr] = ast.literal_eval(statement.value)
    return defaults


#: A freshly created event: every field unset. On the JSON topics an event
#: that never received a value for a field carries exactly this.
DEFAULT_EVENT = _model_defaults()

#: Every model attribute set, with the types the JSON topics carry.
FULL_EVENT: Dict[str, Any] = {
    "ra": 187.70593,
    "dec": 12.39112,
    "err": 0.0004,
    "ivorn_time": "2025-02-20T10:02:11",
    "time": "2025-02-14T08:15:00.250",
    "timestamp": 1739520900250.0,
    "ivorn": "ivo://AstroCOLIBRI/TNS_OT_SN_TNS2025mq_20250214T081500",
    "assoc": "EP250214a",
    "trigger_id": "TNS2025mq",
    "astro_colibri_id": "AC2025mq",
    "identifier": "SN2025mq",
    "energy": 0.3,
    "far": 0.01,
    "signalness": 0.4,
    "pkt_ser_num": 3,
    "reference": "ivo://tns/2025mq#1",
    "source_name": "SN 2025mq",
    "observatory": "ztf",
    "instrument": "ZTF-cam",
    "type": "ot_sn",
    "comment": "Type Ia supernova in NGC 4501",
    "lc_url": "https://example.org/lc.png",
    "energy_time_url": "https://example.org/energy_time.png",
    "sed_url": "https://example.org/sed.png",
    "simbad_link": "https://simbad.u-strasbg.fr/simbad/sim-id?Ident=NGC4501",
    "dm": "500 pc cm^-3",
    "latest_lc_url": "https://example.org/latest_lc.png",
    "longterm_lc_url": "https://example.org/longterm_lc.png",
    "gw_BNS": 0.1,
    "gw_NSBH": 0.2,
    "gw_BBH": 0.3,
    "gw_MassGap": 0.05,
    "gw_Noise": 0.35,
    "gw_hasNS": 0.6,
    "gw_hasSSM": 0.01,
    "gw_pipeline": "pycbc",
    "gw_contours": {"90": [[187.0, 12.0], [188.0, 13.0]]},
    "map_areas": {"50": 12.5, "90": 46.0},
    "alert_type": "classification",
    "slew": True,
    "url": "https://www.wis-tns.org/object/2025mq",
    "url_name": "TNS",
    "constellation": "Virgo",
    "discoverer_internal_name": "ZTF25aaxyzab",
    "redshift": 0.0213,
    "distance": 95.0,
    "distance_error": 4.5,
    "classification": "SN Ia",
    "transient_flux": 17.8,
    "transient_flux_error": 0.05,
    "transient_flux_units": "mag",
    "transient_flux_band": "ztf_r",
    "significance": 7.5,
    "confidential_observatory": "",
    "ivorn_history": ["ivo://tns/2025mq#1", "ivo://tns/2025mq#2"],
    "event_display_url": "https://example.org/display.png",
    "event_url": "https://example.org/event",
    "unistellar_deeplink": "unistellar://target?ra=187.7&dec=12.4",
    "photometry": {
        "ztf_g": {
            "first": {"time": "2025-02-14T08:15:00", "mag": 19.21, "mag_err": 0.09},
            "peak": {"time": "2025-02-27T07:40:00", "mag": 17.52, "mag_err": 0.03},
            "last": {"time": "2025-03-10T06:55:00", "mag": 18.34, "mag_err": 0.05},
        },
        "atlas_o": {
            "last": {"time": "2025-03-11T11:02:00", "mag": 18.1, "mag_err": 0.07}
        },
    },
    "extinction_ebv": 0.023,
    "sun_distance": 101.5,
    "broker": "TNS",
    "follow_up": ["rapas", "hess"],
    "broker_attributes": {"classifier": "SNIascore", "score": 0.97},
    "archive_id": "TNS2025mq_7",
    "last_modified": "2025-02-20T10:05:40",
    "archive": {"TNS2025mq_6": "2025-02-19T09:00:00"},
    "image_urls": {"finder": "https://example.org/finder.png"},
}

GW_EVENT = {
    **DEFAULT_EVENT,
    "trigger_id": "S230518h",
    "source_name": "S230518h",
    "type": "gw",
    "observatory": "lvc",
    "instrument": "H1,L1",
    "alert_type": "Update",
    "time": "2023-05-18T12:59:08.000",
    "timestamp": 1684414748000.0,
    "ra": 100.72265625,
    "dec": -22.10481241978742,
    "far": 0.010156060444406362,
    "significance": 1.0,
    "gw_NSBH": 0.86,
    "gw_BBH": 0.04,
    "gw_hasNS": 1.0,
    "map_areas": {"50": 131.0, "90": 436.0},
    "distance": 204.28,
    "follow_up": ["icecube neutrino observatory"],
}

NEUTRINO_EVENT = {
    **DEFAULT_EVENT,
    "trigger_id": "137840_57034692",
    "source_name": "IceCube-230101A",
    "type": "neutrino",
    "observatory": "icecube",
    "alert_type": "gold",
    "time": "2023-01-01T13:20:00.000",
    "timestamp": 1672579200000.0,
    "ra": 350.1,
    "dec": 12.4,
    "err": 0.8,
    "energy": 180.0,
    "signalness": 0.52,
}


def _days_ago(days: float) -> str:
    moment = datetime.now(tz=timezone.utc) - timedelta(days=days)
    return moment.strftime("%Y-%m-%dT%H:%M:%S")


#: A young, bright, fast-rising supernova, so the photometry filters (bright,
#: recent, fast rising) pass for it rather than fail for lack of data. The
#: dates sit days away from the filters' 7-day limits, which are measured
#: from now.
RISING_OT_EVENT = {
    **DEFAULT_EVENT,
    "trigger_id": "TNS2026abc",
    "source_name": "SN 2026abc",
    "type": "ot_sn",
    "observatory": "ztf",
    "classification": "SN II",
    "broker": "TNS",
    "time": "2026-01-01T00:00:00.000",
    "ra": 210.9,
    "dec": -20.5,
    "photometry": {
        band: {
            "first": {"time": _days_ago(5.5), "mag": 19.8, "mag_err": 0.1},
            "peak": {"time": _days_ago(2.5), "mag": 16.4, "mag_err": 0.03},
            "last": {"time": _days_ago(1.5), "mag": 16.6, "mag_err": 0.03},
        }
        for band in ("ztf_g", "ztf_r", "atlas_o", "atlas_c", "last_clear")
    },
}

SAMPLE_EVENTS = {
    "full": FULL_EVENT,
    "rising_ot": RISING_OT_EVENT,
    "defaults": DEFAULT_EVENT,
    "gw": GW_EVENT,
    "neutrino": NEUTRINO_EVENT,
}


def round_trip(event: Dict[str, Any]) -> Dict[str, Any]:
    return parse_voevent(convert_event_to_voevent(event)).to_colibri_event()


# ── The event model is covered ──────────────────────────────────────────────


def test_the_full_sample_sets_every_model_attribute():
    # A new attribute in Voevent.__init__ lands here: add it to FULL_EVENT,
    # and either to the converter or to NOT_CARRIED.
    assert set(FULL_EVENT) == set(DEFAULT_EVENT)
    unset = {
        name
        for name, value in FULL_EVENT.items()
        if value == DEFAULT_EVENT[name] and name not in NOT_CARRIED
    }
    assert unset == set()


def test_the_full_event_comes_back_unchanged():
    expected = {k: v for k, v in FULL_EVENT.items() if k not in NOT_CARRIED}
    assert round_trip(FULL_EVENT) == expected


def test_time_keeps_millisecond_precision():
    event = {**NEUTRINO_EVENT, "time": "2023-01-01T13:20:00.123456"}
    back = round_trip(event)
    assert back["time"] == "2023-01-01T13:20:00.123"
    assert back["timestamp"] == 1672579200123.0


def test_unset_fields_are_left_out_but_read_the_same():
    back = round_trip(DEFAULT_EVENT)
    # The placeholders a filter compares against survive where it matters.
    assert (back["ra"], back["dec"], back["err"]) == (-1.0, -1.0, -1.0)
    assert back["slew"] is False
    assert "redshift" not in back
    assert "photometry" not in back
    assert "follow_up" not in back


def test_the_timestamp_is_derived_from_the_time():
    back = round_trip(GW_EVENT)
    moment = datetime.fromtimestamp(back["timestamp"] / 1000.0, tz=timezone.utc)
    assert moment == datetime(2023, 5, 18, 12, 59, 8, tzinfo=timezone.utc)


# ── Same filter, same answer on both topics ─────────────────────────────────


def _app_filter_systems() -> Dict[str, List[Dict[str, Any]]]:
    """The app's default filter systems by group, as saved to Firestore."""
    systems = {}
    for group, name in (
        ("obs", "observatory"),
        ("type", "type"),
        ("general", "general"),
    ):
        document = json.loads((APP_FILTERS / f"{name}_filters.json").read_text("utf-8"))
        (configuration,) = document.values()
        systems[group] = configuration
    return systems


def _specifications(node: Any) -> Iterator[Dict[str, Any]]:
    """Every filter specification in ``node``, composites and leaves alike."""
    if isinstance(node, dict):
        if str(node.get("type", "")).endswith("Specification"):
            yield node
        for value in node.values():
            yield from _specifications(value)
    elif isinstance(node, list):
        for value in node:
            yield from _specifications(value)


def _activated(spec: Dict[str, Any]) -> Dict[str, Any]:
    """``spec`` switched on, so its field logic runs rather than its default."""
    spec = copy.deepcopy(spec)
    spec["isActivated"] = True
    return spec


def _app_filters() -> Dict[str, Dict[str, Any]]:
    systems = _app_filter_systems()
    filters = {}
    for index, spec in enumerate(_specifications(systems)):
        label = spec.get("field") or spec["type"]
        filters[f"{index}:{label}"] = _activated(spec)
    # Every system switched on, combined as /saved_filters returns them.
    switched_on = {
        group: [{**system, "isActivated": True} for system in entries]
        for group, entries in systems.items()
    }
    filters["combined:defaults"] = create_filter_from_dict(systems)
    filters["combined:all-on"] = create_filter_from_dict(switched_on)
    return filters


APP_FILTERS_BY_NAME = _app_filters()


def _outcome(spec: Dict[str, Any], event: Dict[str, Any]) -> Any:
    engine = BaseFilter.create_from_dict(copy.deepcopy(spec))
    try:
        return engine.apply_filter(event)
    except Exception as exc:  # the comparison itself is what is under test
        return type(exc).__name__


def test_the_app_configuration_is_found():
    # A path or format change in the app must not silently empty this test.
    assert len(APP_FILTERS_BY_NAME) > 100


@pytest.mark.parametrize("event_name", SAMPLE_EVENTS)
def test_every_app_filter_answers_the_same_after_the_round_trip(event_name):
    event = SAMPLE_EVENTS[event_name]
    back = round_trip(event)
    different = {
        name: (_outcome(spec, event), _outcome(spec, back))
        for name, spec in APP_FILTERS_BY_NAME.items()
        if _outcome(spec, event) != _outcome(spec, back)
    }
    assert different == {}
