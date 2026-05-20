import os

from autonomous_trading_ai.execution import telegram_signal_service as svc


def test_service_not_configured_when_autostart_false(monkeypatch) -> None:
    monkeypatch.setenv("ATA_TELEGRAM_SIGNAL_AUTOSTART", "false")
    monkeypatch.setenv("TELEGRAM_API_ID", "123")
    monkeypatch.setenv("TELEGRAM_API_HASH", "abc")

    assert svc.telegram_signal_service_configured() is False


def test_service_configured_when_credentials_present(monkeypatch) -> None:
    monkeypatch.setenv("ATA_TELEGRAM_SIGNAL_AUTOSTART", "true")
    monkeypatch.setenv("TELEGRAM_API_ID", "123")
    monkeypatch.setenv("TELEGRAM_API_HASH", "abc")

    assert svc.telegram_signal_service_configured() is True


def test_env_int_invalid_falls_back(monkeypatch) -> None:
    monkeypatch.setenv("ATA_TELEGRAM_SIGNAL_HISTORY", "not-an-int")

    assert svc._env_int("ATA_TELEGRAM_SIGNAL_HISTORY", 7) == 7
