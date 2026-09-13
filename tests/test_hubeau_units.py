"""Hub'Eau results must be converted to their declared unit before aggregation.

The mixed units below are the ones Hub'Eau returned for these parameters in a
live sample taken on 2026-09-13.
"""

from unittest.mock import AsyncMock

import pandas as pd
import pytest

from farmwise_api.adapters.API_readers.hubeau import hubeau_sw_quality_read as surface
from farmwise_api.adapters.API_readers.hubeau import hubeau_wq_read as groundwater
from farmwise_api.adapters.API_readers.hubeau.hubeau_mappings import (
    hubeau_mapping_sw_quality,
    hubeau_mapping_wq,
)
from farmwise_api.adapters.API_readers.hubeau.hubeau_units import (
    BASIS_CONVERSIONS,
    PARAMETERS,
    conversion,
    normalise_results,
)


@pytest.mark.parametrize(
    "code, symbol, factor",
    [
        ("1340", "mg(NO3)/L", 1.0),
        ("1340", "mg(N)/L", 62.004 / 14.007),
        ("1350", "mg(P2O5)/L", 61.948 / 141.943),
        ("1350", "µg(P)/L", 1e-3),
        ("1369", "mg(As)/L", 1e3),
        ("1369", "µg/L", 1.0),
        ("1383", "mg/L", 1e3),
        ("1337", "mg(Cl-)/L", 1.0),
        ("1375", "μg/L", 1e-3),  # GREEK SMALL LETTER MU, not MICRO SIGN
        ("5347", "ng/L", 1e-3),
        ("1302", "unité pH", 1.0),
        ("1303", "µS/cm", 1.0),
    ],
)
def test_convertible_units(code, symbol, factor):
    assert conversion(code, symbol).factor == pytest.approx(factor, rel=1e-4)


@pytest.mark.parametrize(
    "code, symbol",
    [
        ("1340", "mg/L"),        # nitrate as N or as NO3?
        ("1340", "µg/L"),
        ("1340", "mg(CO3)/L"),   # wrong chemical form
        ("1350", "mg/L"),        # phosphorus as P, PO4 or P2O5?
        ("1369", "mg(As)/kg"),   # sediment, not water
        ("1388", "µg/kg"),
        ("1375", "Unité inconnue"),
        ("1375", None),
        ("1302", "mg/L"),
    ],
)
def test_ambiguous_or_incompatible_units_are_rejected(code, symbol):
    result = conversion(code, symbol)
    assert result.factor is None and result.reason


def test_every_requested_code_has_an_output_unit():
    for module in (hubeau_mapping_wq, hubeau_mapping_sw_quality):
        codes = {codes[0] for codes in module.CODES.values()}
        assert codes <= set(PARAMETERS)
    for code, _basis in BASIS_CONVERSIONS:
        assert code in PARAMETERS


def test_every_output_label_ends_in_a_parseable_unit():
    for module in (hubeau_mapping_wq, hubeau_mapping_sw_quality):
        for key, label in module.MAPPING.items():
            code = key.split(":")[0]
            assert label.endswith(f"[{PARAMETERS[code][1]}]")


def test_normalise_results_converts_splits_fractions_and_reports_drops():
    frame = pd.DataFrame(
        {
            "code_param": ["1369", "1369", "1369", "1369", "1340", "1340"],
            "symbole_unite": ["µg(As)/L", "mg(As)/L", "µg(As)/L", "mg(As)/kg",
                              "mg(N)/L", "mg/L"],
            "code_fraction": ["3", "3", "23", "32", "23", "23"],
            "resultat": [2.0, 0.004, 5.0, 12.0, 1.0, 40.0],
        }
    )

    kept, report = normalise_results(frame, prefix="SW")

    assert list(kept["parameter"]) == [
        "SW Arsenic (dissolved) [µg(As)/L]",
        "SW Arsenic (dissolved) [µg(As)/L]",
        "SW Arsenic (raw water) [µg(As)/L]",
        "SW Nitrates (raw water) [mg(NO3)/L]",
    ]
    assert kept["resultat"].tolist() == pytest.approx([2.0, 4.0, 5.0, 4.4266], rel=1e-4)
    assert report["results_received"] == 6
    assert report["results_kept"] == 4
    assert sum(report["results_dropped"].values()) == 2


def _result(code, unit, value, fraction, day="2024-01-02"):
    return {
        "date_debut_prelevement": pd.Timestamp(day),
        "latitude": 50.0,
        "longitude": 2.0,
        "code_param": code,
        "code_parametre": code,
        "nom_param": "ignored",
        "libelle_parametre": "ignored",
        "resultat": value,
        "symbole_unite": unit,
        "code_fraction": fraction,
        "libelle_fraction": "",
        "code_remarque": "1",
        "libelle_support": "Eau",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "module, points, id_column, prefix",
    [
        (groundwater, {"code_bss_new": ["P1"], "lon": [2.0], "lat": [50.0]}, "bss_id", "GW"),
        (surface, {"code_station": ["P1"], "x_longitude": [2.0], "y_latitude": [50.0]},
         "code_station", "SW"),
    ],
)
async def test_read_data_never_averages_results_in_different_units(
    monkeypatch, module, points, id_column, prefix
):
    rows = [
        # Same point and day: 2 µg/L and 0.004 mg/L are 2 and 4 µg/L. Averaged
        # without conversion they used to give 1.002 under a µg/L label.
        _result("1369", "µg(As)/L", 2.0, "3"),
        _result("1369", "mg(As)/L", 0.004, "3"),
        # A sediment result must not enter the water column at all.
        _result("1369", "mg(As)/kg", 30.0, "32"),
        # Raw water is a different quantity from the dissolved fraction.
        _result("1369", "µg(As)/L", 9.0, "23"),
    ]
    frame = pd.DataFrame(rows)
    frame[id_column] = "P1"
    # Each API names the parameter fields its own way; the river adapter
    # renames code_parametre/libelle_parametre to the groundwater names.
    if module is surface:
        frame = frame.drop(columns=["code_param", "nom_param"])
    else:
        frame = frame.drop(columns=["code_parametre", "libelle_parametre"])
    monkeypatch.setattr(module, "adapter_data", lambda *_args: "points.csv")
    monkeypatch.setattr(module.pd, "read_csv", lambda *_a, **_k: pd.DataFrame(points))
    monkeypatch.setattr(module.hub, "init_api", lambda *_a, **_k: object())
    monkeypatch.setattr(module, "fetch_data", AsyncMock(return_value=frame))

    result = await module.read_data(
        (50.5, 49.5, 2.5, 1.5), ("2024-01-01", "2024-01-03"), ["heavy metals"], 10,
    )

    labels = set(result.columns.get_level_values(0))
    dissolved = f"{prefix} Arsenic (dissolved) [µg(As)/L]"
    raw = f"{prefix} Arsenic (raw water) [µg(As)/L]"
    assert labels == {dissolved, raw}
    day = pd.Timestamp("2024-01-02").date()
    assert result.loc[day, dissolved].iloc[0] == pytest.approx(3.0)
    assert result.loc[day, raw].iloc[0] == pytest.approx(9.0)
    report = result.attrs["unit_normalisation"]
    assert report["results_kept"] == 3
    assert any("mg(As)/kg" in key for key in report["results_dropped"])


@pytest.mark.asyncio
async def test_groundwater_requests_exclude_incorrect_and_uncertain_results():
    class API:
        def __init__(self):
            self.kwargs = None

        def get_data(self, **kwargs):
            self.kwargs = kwargs
            return pd.DataFrame()

    api = API()
    await groundwater.fetch_data(api, "P1", ["2024-01-01", "2024-01-02"], ["1340"], 0)

    assert api.kwargs["code_qualification"] == "0,1,4"
    assert "only_valid_data" not in api.kwargs
