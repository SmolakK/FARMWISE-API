"""Groundwater levels from every source share one column and one unit.

EPA Ireland, Hub'Eau and CORRECTIV all report the elevation of the water table,
but used to return it as "[m AOD]", "[cm]" (after multiplying metres by 100)
and "Depth [a.s.l]" respectively. Three names for one quantity meant the
harmonisation step could never combine them, and "Depth" described an
elevation. They now all use GROUNDWATER_LEVEL_COLUMN, in metres.
"""

from farmwise_api.adapters.mappings.units import GROUNDWATER_LEVEL_COLUMN


def test_the_shared_column_is_metres_above_sea_level():
    assert GROUNDWATER_LEVEL_COLUMN == "Groundwater level [m a.s.l.]"


def test_epa_reports_groundwater_level_in_the_shared_column():
    from farmwise_api.adapters.API_readers.epa_ireland.epa_ireland_mappings import (
        epa_ireland_mapping as epa,
    )

    assert GROUNDWATER_LEVEL_COLUMN in epa.GLOBAL_MAPPING.values()


def test_hubeau_reports_groundwater_level_in_the_shared_column():
    from farmwise_api.adapters.API_readers.hubeau.hubeau_mappings import (
        hubeau_mapping_piezo as hubeau,
    )

    assert hubeau.MAPPING["niveau_nappe_eau"] == GROUNDWATER_LEVEL_COLUMN


def test_hubeau_depth_is_never_labelled_as_a_level_or_below_ground():
    """profondeur_nappe is relative to a measuring reference, not the ground."""
    from farmwise_api.adapters.API_readers.hubeau.hubeau_mappings import (
        hubeau_mapping_piezo as hubeau,
    )

    label = hubeau.MAPPING["profondeur_nappe"]
    assert label != GROUNDWATER_LEVEL_COLUMN
    assert "measuring reference" in label
    assert "[m]" in label


def test_correctiv_levels_are_labelled_as_levels_in_metres():
    from farmwise_api.adapters.API_readers.correctiv.mappings import (
        correctiv_mappings as correctiv,
    )

    for label in correctiv.GLOBAL_MAPPING.values():
        assert "groundwater level [m a.s.l.]" in label
        assert "Depth" not in label, f"an elevation was labelled as a depth: {label}"


def test_no_adapter_still_rescales_groundwater_level_to_centimetres():
    """The shared unit is metres; a stray *100 would silently break it."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "farmwise_api" / "adapters"
    offenders = [
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if "Groundwater Level [cm]" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"centimetre groundwater levels remain in: {offenders}"


def test_gios_aquifer_top_depth_is_not_presented_as_a_water_level():
    """GIOŚ reports depth to the top of the aquifer layer below ground.

    That is a property of the borehole, not the water table, and a depth below
    ground cannot become an elevation without the ground elevation. It must
    stay out of the shared groundwater-level column.
    """
    from farmwise_api.adapters.API_readers.gios_gw.gios_gw_mappings import (
        gios_gw_mapping as gios,
    )

    assert "Depth to Top of Aquifer Layer [m b.g.l.]" in gios.DATA_ALIASES
    assert GROUNDWATER_LEVEL_COLUMN not in gios.selected_columns.values()
