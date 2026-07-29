from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from adapters.API_readers.hubeau.hubeau_piezo_read_vbrgm import read_data


@pytest.mark.asyncio
@patch(
    "adapters.API_readers.hubeau.hubeau_piezo_read_vbrgm.fetch_data",
    new_callable=AsyncMock,
)
@patch("adapters.API_readers.hubeau.hubeau_piezo_read_vbrgm.prepare_coordinates")
@patch("adapters.API_readers.hubeau.hubeau_piezo_read_vbrgm.pd.read_csv")
@patch("adapters.API_readers.hubeau.hubeau_piezo_read_vbrgm.hub.init_api")
async def test_read_data(
    mock_init_api,
    mock_read_csv,
    mock_prepare_coordinates,
    mock_fetch_data,
):
    coordinates = pd.DataFrame(
        {
            "code_bss_old": ["OLD1", "OLD2"],
            "code_bss_new": ["STATION1", "STATION2"],
            "lat": [48.8566, 48.8333],
            "lon": [2.3522, 2.3333],
            "S2CELL": ["cell1", "cell2"],
        }
    )
    mock_read_csv.return_value = coordinates
    def prepare(
        frame=None,
        spatial_range=None,
        level=None,
        *,
        coordinates=None,
        **_kwargs,
    ):
        selected = coordinates if coordinates is not None else frame
        if "point_id" not in selected:
            return selected
        return selected.assign(
            S2CELL=selected["point_id"].map(
                {"STATION1": "cell1", "STATION2": "cell2"}
            )
        )

    mock_prepare_coordinates.side_effect = prepare
    mock_fetch_data.side_effect = [
        pd.DataFrame(
            {
                "date_mesure": ["2018-01-01"],
                "niveau_nappe_eau": [2.0],
                "code_bss_old": ["OLD1"],
            }
        ),
        pd.DataFrame(
            {
                "date_mesure": ["2018-01-01"],
                "niveau_nappe_eau": [1.5],
                "code_bss_old": ["OLD2"],
            }
        ),
    ]

    result = await read_data(
        spatial_range=(49.0, 48.0, 3.0, 2.0),
        time_range=("2018-01-01", "2018-01-02"),
        data_range=["groundwater quantity"],
        level=8,
    )

    assert isinstance(result, pd.DataFrame)
    assert not result.empty
    assert "Groundwater Level [cm]" in result.columns.get_level_values(0)
    assert result["Groundwater Level [cm]"].iloc[0, 0] == 200
    mock_init_api.assert_called_once_with("piezometry")
