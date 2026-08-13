import importlib
import inspect

import pytest

from farmwise_api.adapters.mappings.data_source_mapping import API_PATH_RANGES


@pytest.mark.parametrize("source", API_PATH_RANGES)
def test_every_registered_adapter_accepts_within_source_policy(source):
    adapter = importlib.import_module(source)

    assert "within_source_aggregation_methods" in inspect.signature(
        adapter.read_data
    ).parameters
