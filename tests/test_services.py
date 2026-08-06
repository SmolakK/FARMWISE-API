from unittest.mock import AsyncMock

import pytest

from adapters.mappings.data_source_mapping import PUBLIC_SERVER_DISABLED_SOURCES
from server import services


@pytest.mark.asyncio
async def test_server_reader_always_applies_public_source_restrictions(monkeypatch):
    core_reader = AsyncMock(return_value={"data": "ok"})
    monkeypatch.setattr(services, "read_core_data", core_reader)

    result = await services.read_data(
        country="Poland",
        level=10,
        time_from="2024-01-01",
        time_to="2024-01-02",
        factors=["temperature"],
        disabled_sources={"caller.attempt": "must not be trusted"},
    )

    assert result == {"data": "ok"}
    assert (
        core_reader.await_args.kwargs["disabled_sources"]
        is PUBLIC_SERVER_DISABLED_SOURCES
    )
