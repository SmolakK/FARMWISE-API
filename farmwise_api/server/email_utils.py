import smtplib
from email.mime.text import MIMEText
import os
from pathlib import Path

from dotenv import load_dotenv

from farmwise_api.core.utils.paths import PROJECT_ROOT
from farmwise_api.server.logging_config import logger


# The default must stay outside the package tree: an installed package
# directory may be read-only, and SMTP credentials must never be kept
# next to the shipped source. PROJECT_ROOT is the checkout root in a
# source checkout and the process working directory once installed.
SMTP_ENV_FILE = Path(
    os.environ.get("FARMWISE_SMTP_ENV_FILE", PROJECT_ROOT / "smtp.env")
).resolve()


def _smtp_config() -> tuple[str, int, str, str]:
    # Existing environment variables win: load_dotenv does not override them,
    # so a deployment can inject credentials without a file on disk.
    load_dotenv(SMTP_ENV_FILE)
    values = {
        "EMAIL_HOST": os.getenv("EMAIL_HOST"),
        "EMAIL_PORT": os.getenv("EMAIL_PORT"),
        "EMAIL_USER": os.getenv("EMAIL_USER"),
        "EMAIL_PASS": os.getenv("EMAIL_PASS"),
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        # The resolved credential path is deliberately not part of this
        # message: it travels into logs and, through any caller that reports
        # exception text, potentially further. Operators get it from the
        # debug log below instead.
        logger.debug("SMTP configuration was read from %s", SMTP_ENV_FILE)
        raise RuntimeError(
            f"SMTP configuration is missing: {', '.join(missing)}. "
            "Set these as environment variables, or provide them in the "
            "smtp.env file referenced by FARMWISE_SMTP_ENV_FILE."
        )
    # Past the check above every value is a non-empty string; rebuilding the
    # mapping this way makes that visible instead of implied.
    config = {name: value for name, value in values.items() if value}
    try:
        port = int(config["EMAIL_PORT"])
    except ValueError as exc:
        raise RuntimeError("EMAIL_PORT must be an integer") from exc
    return config["EMAIL_HOST"], port, config["EMAIL_USER"], config["EMAIL_PASS"]


def send_email(to_email, subject, body) -> None:
    try:
        smtp_server, smtp_port, smtp_user, smtp_password = _smtp_config()

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = to_email

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, [to_email], msg.as_string())

        logger.info(f"Email sent to {to_email}")
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
