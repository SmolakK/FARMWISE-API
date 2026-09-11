import os

import pytest

from farmwise_api.core.utils.access_policy import (
    IMGW_PRIVATE_USE_ENV,
    IMGW_RESEARCH_USE_ENV,
    acknowledged_private_noncommercial_imgw,
    private_noncommercial_imgw_enabled,
    require_private_noncommercial_imgw,
)


def test_imgw_access_is_denied_without_explicit_acknowledgement(monkeypatch):
    monkeypatch.delenv(IMGW_PRIVATE_USE_ENV, raising=False)
    monkeypatch.delenv(IMGW_RESEARCH_USE_ENV, raising=False)

    assert private_noncommercial_imgw_enabled() is False
    with pytest.raises(PermissionError, match="academic research"):
        require_private_noncommercial_imgw()


@pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
def test_imgw_access_accepts_documented_truthy_values(monkeypatch, value):
    monkeypatch.delenv(IMGW_RESEARCH_USE_ENV, raising=False)
    monkeypatch.setenv(IMGW_PRIVATE_USE_ENV, value)

    assert private_noncommercial_imgw_enabled() is True
    assert require_private_noncommercial_imgw() is None


@pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
def test_imgw_access_accepts_research_acknowledgement(monkeypatch, value):
    monkeypatch.delenv(IMGW_PRIVATE_USE_ENV, raising=False)
    monkeypatch.setenv(IMGW_RESEARCH_USE_ENV, value)

    assert private_noncommercial_imgw_enabled() is True
    assert require_private_noncommercial_imgw() is None


def test_acknowledgement_opens_the_gate_only_inside_the_block(monkeypatch):
    monkeypatch.delenv(IMGW_PRIVATE_USE_ENV, raising=False)
    monkeypatch.delenv(IMGW_RESEARCH_USE_ENV, raising=False)

    with acknowledged_private_noncommercial_imgw():
        assert private_noncommercial_imgw_enabled() is True

    assert private_noncommercial_imgw_enabled() is False
    assert IMGW_RESEARCH_USE_ENV not in os.environ


def test_acknowledgement_restores_a_pre_existing_value(monkeypatch):
    monkeypatch.delenv(IMGW_PRIVATE_USE_ENV, raising=False)
    monkeypatch.setenv(IMGW_RESEARCH_USE_ENV, "on")

    with acknowledged_private_noncommercial_imgw():
        assert os.environ[IMGW_RESEARCH_USE_ENV] == "1"

    assert os.environ[IMGW_RESEARCH_USE_ENV] == "on"


def test_acknowledgement_is_restored_when_the_block_raises(monkeypatch):
    monkeypatch.delenv(IMGW_PRIVATE_USE_ENV, raising=False)
    monkeypatch.delenv(IMGW_RESEARCH_USE_ENV, raising=False)

    with pytest.raises(RuntimeError):
        with acknowledged_private_noncommercial_imgw():
            raise RuntimeError("collection failed")

    assert private_noncommercial_imgw_enabled() is False
    assert IMGW_RESEARCH_USE_ENV not in os.environ
