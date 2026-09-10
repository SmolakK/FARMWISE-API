import smtplib
from email.mime.text import MIMEText
import os
from pathlib import Path

from dotenv import load_dotenv

from farmwise_api.core.utils.paths import PROJECT_ROOT
from farmwise_api.server.logging_config import logger


SMTP_ENV_FILE = Path(
    os.environ.get("FARMWISE_SMTP_ENV_FILE", PROJECT_ROOT / "smtp.env")
).resolve()


def _smtp_config():
    load_dotenv(SMTP_ENV_FILE)
    values = {
        "EMAIL_HOST": os.getenv("EMAIL_HOST"),
        "EMAIL_PORT": os.getenv("EMAIL_PORT"),
        "EMAIL_USER": os.getenv("EMAIL_USER"),
        "EMAIL_PASS": os.getenv("EMAIL_PASS"),
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(
            f"SMTP configuration is missing: {', '.join(missing)} "
            f"(expected in {SMTP_ENV_FILE})"
        )
    try:
        port = int(values["EMAIL_PORT"])
    except ValueError as exc:
        raise RuntimeError("EMAIL_PORT must be an integer") from exc
    return values["EMAIL_HOST"], port, values["EMAIL_USER"], values["EMAIL_PASS"]


def send_email(to_email, subject, body):
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
