from unittest.mock import MagicMock

from farmwise_api.core.utils.paths import PACKAGE_ROOT
from farmwise_api.server import email_utils


def test_smtp_config_is_not_written_inside_installed_package():
    assert email_utils.SMTP_ENV_FILE.name == "smtp.env"
    assert email_utils.SMTP_ENV_FILE.parent == email_utils.PROJECT_ROOT
    assert not email_utils.SMTP_ENV_FILE.is_relative_to(PACKAGE_ROOT)


def test_send_email_uses_configured_smtp(monkeypatch):
    monkeypatch.setenv("EMAIL_HOST", "smtp.example.test")
    monkeypatch.setenv("EMAIL_PORT", "587")
    monkeypatch.setenv("EMAIL_USER", "farmwise@example.test")
    monkeypatch.setenv("EMAIL_PASS", "secret")
    monkeypatch.setattr(email_utils, "load_dotenv", MagicMock())
    smtp = MagicMock()
    monkeypatch.setattr(email_utils.smtplib, "SMTP", smtp)

    email_utils.send_email("user@example.test", "Subject", "Body")

    smtp.assert_called_once_with("smtp.example.test", 587)
    connection = smtp.return_value.__enter__.return_value
    connection.starttls.assert_called_once_with()
    connection.login.assert_called_once_with("farmwise@example.test", "secret")
    args = connection.sendmail.call_args.args
    assert args[0] == "farmwise@example.test"
    assert args[1] == ["user@example.test"]
    assert "Subject: Subject" in args[2]
    assert "Body" in args[2]


def test_send_email_logs_configuration_errors(monkeypatch):
    monkeypatch.setenv("EMAIL_HOST", "smtp.example.test")
    monkeypatch.setenv("EMAIL_PORT", "not-a-number")
    monkeypatch.setenv("EMAIL_USER", "farmwise@example.test")
    monkeypatch.setenv("EMAIL_PASS", "secret")
    monkeypatch.setattr(email_utils, "load_dotenv", MagicMock())
    smtp = MagicMock()
    monkeypatch.setattr(email_utils.smtplib, "SMTP", smtp)
    error = MagicMock()
    monkeypatch.setattr(email_utils.logger, "error", error)

    email_utils.send_email("user@example.test", "Subject", "Body")

    error.assert_called_once()
    assert "Failed to send email" in error.call_args.args[0]
    assert "EMAIL_PORT must be an integer" in error.call_args.args[0]
    smtp.assert_not_called()


def test_send_email_identifies_missing_configuration(monkeypatch):
    for name in ("EMAIL_HOST", "EMAIL_PORT", "EMAIL_USER", "EMAIL_PASS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(email_utils, "load_dotenv", MagicMock())
    smtp = MagicMock()
    monkeypatch.setattr(email_utils.smtplib, "SMTP", smtp)
    error = MagicMock()
    monkeypatch.setattr(email_utils.logger, "error", error)

    email_utils.send_email("user@example.test", "Subject", "Body")

    message = error.call_args.args[0]
    assert "SMTP configuration is missing" in message
    assert "EMAIL_HOST" in message
    assert "EMAIL_PORT" in message
    smtp.assert_not_called()
