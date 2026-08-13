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


def send_email(to_email, subject, body):
    try:
        load_dotenv(SMTP_ENV_FILE)
        smtp_server = os.getenv("EMAIL_HOST")
        smtp_port = int(os.getenv("EMAIL_PORT"))
        smtp_user = os.getenv("EMAIL_USER")
        smtp_password = os.getenv("EMAIL_PASS")

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
