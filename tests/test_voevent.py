"""
tests/test_voevent.py

Unit tests for parse_voevent(), the VOEvent 2.0 parser.

The fixtures in tests/data/voevents/ are real documents: the astrocolibri_*
files come out of the converter behind the broker's VOEvent topics and
/get_event_as_voevent, applied to production events; the gcn_* files are
GCN notices as received by the Astro-COLIBRI listeners.

Run:
    pytest tests/test_voevent.py -v
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from astrocolibri import (
    AstrocolibriDecodeError,
    AstrocolibriError,
    VOEvent,
    parse_voevent,
)
from astrocolibri.voevent import Citation, Position, _parse_time

DATA = Path(__file__).resolve().parent / "data" / "voevents"
UTC = timezone.utc


def load(name: str) -> VOEvent:
    return parse_voevent((DATA / f"{name}.xml").read_text(encoding="utf-8"))


class TestAstroColibriDocument:
    @pytest.fixture
    def gw(self):
        return load("astrocolibri_gw_S230518h")

    def test_identity(self, gw):
        assert gw.ivorn.startswith("ivo://AstroCOLIBRI/")
        assert gw.role == "observation"
        assert gw.version == "2.0"
        assert gw.is_astro_colibri
        assert not gw.is_test
        assert gw.author == "Astro-COLIBRI"
        assert gw.name == "S230518h"

    def test_time_is_aware_utc(self, gw):
        assert gw.time == datetime(2023, 5, 18, 12, 59, 8, tzinfo=UTC)

    def test_position_in_degrees(self, gw):
        assert gw.position.ra == pytest.approx(100.72265625)
        assert gw.position.dec == pytest.approx(-22.1048, abs=1e-3)
        assert gw.position.system == "UTC-FK5-GEO"

    def test_zero_error_radius_means_none_given(self, gw):
        # Astro-COLIBRI writes Error2Radius 0 when an event has no radius;
        # a GW is localized by its sky map, not a circle.
        assert "<Error2Radius>0</Error2Radius>" in (
            DATA / "astrocolibri_gw_S230518h.xml"
        ).read_text(encoding="utf-8")
        assert gw.position.err is None

    def test_error_radius(self):
        assert load("astrocolibri_grb_190829A_swift").position.err == pytest.approx(
            0.0016
        )

    def test_every_param_sits_in_a_group(self, gw):
        assert gw.params == {}
        assert list(gw.groups) == [
            "Identifiers",
            "Classification",
            "Measurements",
            "Links",
        ]

    def test_values_follow_their_data_type(self, gw):
        assert gw.get("far") == pytest.approx(0.010156060444406362)
        assert isinstance(gw.get("far"), float)
        assert gw.get("pkt_ser_num") == 4
        assert isinstance(gw.get("pkt_ser_num"), int)
        # area_90 is written "436" but declared a float.
        assert isinstance(gw.get("area_90"), float)
        assert gw.get("trigger_id") == "S230518h"

    def test_json_encoded_values_are_decoded(self, gw):
        follow_up = gw.get("follow_up")
        assert isinstance(follow_up, list)
        assert "ligo/virgo/kagra" in follow_up
        assert gw.param("follow_up").raw.startswith("[")

    def test_param_metadata(self, gw):
        far = gw.param("far")
        assert far.unit == "yr^-1"
        assert far.ucd == "stat.probability"
        assert far.data_type == "float"
        assert gw.param("area_90").description.startswith("Sky area within the 90%")

    def test_links_carry_their_reference(self, gw):
        link = gw.groups["Links"]["event_url"]
        assert link.references == (link.value,)

    def test_why_and_how(self, gw):
        # The highest probability among the event's classification values.
        assert gw.importance == 1.0
        assert gw.concepts == ("process.variation.transient;phys.gravity",)
        assert gw.references == (
            "https://astro-colibri.com/event:S230518h",
            gw.get("event_url"),
        )

    def test_get_default_and_missing_param(self, gw):
        assert gw.get("no_such_param") is None
        assert gw.get("no_such_param", "n/a") == "n/a"
        assert gw.param("no_such_param") is None

    def test_to_dict_flattens_the_groups(self, gw):
        values = gw.to_dict()
        assert values["trigger_id"] == "S230518h"
        assert values["far"] == gw.get("far")
        assert len(values) == len(list(gw.iter_params()))

    def test_optical_transient(self):
        sn = load("astrocolibri_ot_sn_2023ixf")
        assert sn.get("type") == "ot_sn"
        assert sn.name == "SN 2023ixf"
        assert sn.position.ra == pytest.approx(210.9106746)


class TestGcnNotices:
    def test_fermi_gbm(self):
        gbm = load("gcn_fermi_gbm_fin_pos")
        assert gbm.ivorn.startswith("ivo://nasa.gsfc.gcn/Fermi#GBM_Fin_Pos")
        assert not gbm.is_astro_colibri
        assert gbm.author == "Fermi (via VO-GCN)"
        # Two fractional digits, which fromisoformat() rejects before 3.11.
        assert gbm.time == datetime(2026, 4, 24, 15, 30, 22, 500000, tzinfo=UTC)
        assert gbm.position == Position(171.74, 20.24, 14.8, "UTC-FK5-GEO")
        assert gbm.importance == pytest.approx(0.95)
        assert gbm.probability == pytest.approx(1.0)
        assert gbm.concepts == ("process.variation.burst;em.gamma",)
        assert gbm.references == ("http://gcn.gsfc.nasa.gov/fermi.html",)

    def test_untyped_values_stay_text(self):
        # GCN classic notices declare no dataType: numbers arrive as text.
        gbm = load("gcn_fermi_gbm_fin_pos")
        assert gbm.get("TrigID") == "798737427"
        assert float(gbm.get("Burst_SOD")) == pytest.approx(55822.5)
        assert gbm.param("Burst_SOD").unit == "sec"

    def test_a_name_can_be_both_a_param_and_a_group(self):
        gbm = load("gcn_fermi_gbm_fin_pos")
        assert gbm.params["Trigger_ID"].value == "0x04000001"
        assert gbm.groups["Trigger_ID"]["Long_short"].value == "Short"
        # get() prefers the ungrouped Param.
        assert gbm.get("Trigger_ID") == "0x04000001"
        assert gbm.get("Long_short") == "Short"

    def test_citations(self):
        gbm = load("gcn_fermi_gbm_fin_pos")
        assert gbm.citations == (
            Citation(
                "ivo://nasa.gsfc.gcn/Fermi#GBM_Alert_2026-04-24T15:30:22.50_798737427_1-656",
                "followup",
            ),
        )
        assert len(load("gcn_svom_mxt").citations) == 4

    def test_lvk_notice_is_typed_and_has_no_position(self):
        lvk = load("gcn_lvk_preliminary")
        assert lvk.is_test
        assert lvk.position is None
        assert lvk.get("FAR") == pytest.approx(9.110699364861297e-14)
        assert lvk.get("HardwareInj") == 0
        assert lvk.groups["Classification"]["BNS"].value == pytest.approx(0.99999573)
        assert lvk.param("GraceID").description == "Identifier in GraceDB"
        # Who/Date carries an explicit "Z" here.
        assert lvk.date == datetime(2026, 3, 30, 17, 57, 18, tzinfo=UTC)

    def test_unavailable_position_is_none(self):
        # IPN writes RA = Dec = Error2Radius = -1 for "unavailable".
        ipn = load("gcn_ipn_raw")
        assert ipn.position is None
        assert ipn.time is not None
        assert ipn.importance is None

    def test_all_sky_error_is_kept(self):
        # SNEWS has no direction: 0/0 with a 360-degree radius.
        snews = load("gcn_snews_test")
        assert snews.position == Position(0.0, 0.0, 360.0, "UTC-FK5-GEO")

    def test_icrs_system(self):
        svom = load("gcn_svom_mxt")
        assert svom.position.system == "UTC-ICRS-GEO"
        assert svom.time == datetime(2026, 4, 21, 4, 18, 40, 264000, tzinfo=UTC)

    @pytest.mark.parametrize("name", sorted(path.stem for path in DATA.glob("*.xml")))
    def test_every_fixture_parses_from_bytes_too(self, name):
        raw = (DATA / f"{name}.xml").read_bytes()
        assert parse_voevent(raw) == load(name)


class TestNamespaces:
    def test_prefixed_children_still_parse(self):
        # Astro-COLIBRI qualified every element before 2026-09.
        text = (DATA / "astrocolibri_grb_190829A_swift.xml").read_text(encoding="utf-8")
        prefixed = re.sub(r"<(/?)(?!voe:|\?)(\w)", r"<\1voe:\2", text)
        assert "<voe:WhereWhen>" in prefixed
        assert parse_voevent(prefixed) == parse_voevent(text)

    def test_root_is_untouched_by_namespace_stripping(self):
        event = load("gcn_svom_mxt")
        assert event.root.tag == "VOEvent"
        assert event.root.find("WhereWhen") is not None


class TestErrors:
    @pytest.mark.parametrize(
        ("document", "message"),
        [
            ("not xml at all", "not a well-formed XML document"),
            ("", "not a well-formed XML document"),
            ('<VOTABLE version="1.3"/>', "root element is <VOTABLE>"),
            (
                '<voe:VOEvent xmlns:voe="http://www.ivoa.net/xml/VOEvent/v2.0"/>',
                "no ivorn",
            ),
        ],
    )
    def test_decode_errors(self, document, message):
        with pytest.raises(AstrocolibriDecodeError, match=message) as info:
            parse_voevent(document)
        assert isinstance(info.value, AstrocolibriError)

    def test_value_contradicting_its_data_type_stays_text(self):
        event = parse_voevent(
            '<VOEvent ivorn="ivo://x/y" version="2.0"><What>'
            '<Param name="n" value="many" dataType="int"/></What></VOEvent>'
        )
        assert event.get("n") == "many"

    def test_value_element(self):
        # The schema also allows the value as a <Value> child.
        event = parse_voevent(
            '<VOEvent ivorn="ivo://x/y" version="2.0"><What>'
            '<Param name="n" dataType="float"><Value>2.5</Value></Param></What></VOEvent>'
        )
        assert event.get("n") == 2.5

    def test_minimal_document(self):
        event = parse_voevent('<VOEvent ivorn="ivo://x/y" version="2.0"/>')
        assert event.role == "observation"
        assert (event.time, event.position, event.importance, event.name) == (
            None,
            None,
            None,
            None,
        )
        assert event.to_dict() == {}


class TestTimes:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("2026-04-24T15:30:22", datetime(2026, 4, 24, 15, 30, 22, tzinfo=UTC)),
            (
                "2026-04-24T15:30:22.5",
                datetime(2026, 4, 24, 15, 30, 22, 500000, tzinfo=UTC),
            ),
            (
                "2026-04-24T15:30:22.1234567",
                datetime(2026, 4, 24, 15, 30, 22, 123456, tzinfo=UTC),
            ),
            ("2026-04-24T15:30:22Z", datetime(2026, 4, 24, 15, 30, 22, tzinfo=UTC)),
            (
                "2026-04-24T17:30:22+02:00",
                datetime(2026, 4, 24, 15, 30, 22, tzinfo=UTC),
            ),
            ("24/04/2026", None),
            ("2026-13-40T15:30:22", None),
        ],
    )
    def test_parse_time(self, text, expected):
        assert _parse_time(text, utc=True) == expected

    def test_non_utc_time_scale_stays_naive(self):
        document = (
            '<VOEvent ivorn="ivo://x/y" version="2.0"><WhereWhen><ObsDataLocation>'
            '<ObservationLocation><AstroCoords coord_system_id="TT-ICRS-TOPO">'
            "<Time><TimeInstant><ISOTime>2026-04-24T15:30:22</ISOTime></TimeInstant></Time>"
            "</AstroCoords></ObservationLocation></ObsDataLocation></WhereWhen></VOEvent>"
        )
        # A TT time is not a UTC time, so it gets no UTC timezone.
        assert parse_voevent(document).time == datetime(2026, 4, 24, 15, 30, 22)


class TestSkyCoord:
    def test_frame_follows_the_coordinate_system(self):
        pytest.importorskip("astropy")
        fk5 = load("gcn_fermi_gbm_fin_pos").position.to_skycoord()
        icrs = load("gcn_svom_mxt").position.to_skycoord()
        assert fk5.frame.name == "fk5"
        assert icrs.frame.name == "icrs"
        assert fk5.ra.deg == pytest.approx(171.74)
        assert icrs.dec.deg == pytest.approx(-17.7566)
