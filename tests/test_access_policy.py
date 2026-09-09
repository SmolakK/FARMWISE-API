import pytest

from farmwise_api.core.utils.access_policy import (
    IMGW_PRIVATE_USE_ENV,
    private_noncommercial_imgw_enabled,
    require_private_noncommercial_imgw,
)


def test_imgw_access_is_denied_without_explicit_acknowledgement(monkeypatch):
    monkeypatch.delenv(IMGW_PRIVATE_USE_ENV, raising=False)

    assert private_noncommercial_imgw_enabled() is False
    with pytest.raises(PermissionError, match="private, non-commercial"):
        require_private_noncommercial_imgw()


@pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
def test_imgw_access_accepts_documented_truthy_values(monkeypatch, value):
    monkeypatch.setenv(IMGW_PRIVATE_USE_ENV, value)

    assert private_noncommercial_imgw_enabled() is True
    assert require_private_noncommercial_imgw() is None
