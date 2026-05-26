import pytest
from pydantic import ValidationError

from app.config import AppConfig, ConfigService


def test_default_config_is_paper_mode():
    config = AppConfig()
    assert config.trading.mode == "paper"
    assert config.trading.live_trading_enabled is False


def test_live_mode_requires_explicit_enablement():
    payload = AppConfig().model_dump()
    payload["trading"]["mode"] = "live"
    payload["trading"]["live_trading_enabled"] = False
    with pytest.raises(ValidationError):
        AppConfig.model_validate(payload)


def test_config_service_saves_and_loads(tmp_path):
    service = ConfigService(tmp_path / "config.json")
    saved = service.save(AppConfig())
    loaded = service.load(force=True)
    assert loaded == saved
