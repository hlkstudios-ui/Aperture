import asyncio
import smtplib
from email.message import EmailMessage

from app.config import get_settings


def _send_password_reset(email: str, token: str) -> None:
    settings = get_settings()
    if not all(
        (
            settings.smtp_host,
            settings.smtp_username,
            settings.smtp_password,
            settings.smtp_from_email,
        )
    ):
        raise RuntimeError("Transactional email is not configured")
    reset_url = f"{str(settings.web_origin).rstrip('/')}/reset-password?token={token}"
    message = EmailMessage()
    message["Subject"] = "Reset your Aperture password"
    message["From"] = settings.smtp_from_email
    message["To"] = email
    message.set_content(
        "A password reset was requested for your Aperture account.\n\n"
        f"Open this one-time link within 30 minutes:\n{reset_url}\n\n"
        "If you did not request this, you can ignore this message."
    )
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


async def send_password_reset(email: str, token: str) -> None:
    try:
        await asyncio.to_thread(_send_password_reset, email, token)
    except (OSError, smtplib.SMTPException) as error:
        raise RuntimeError("Transactional email delivery failed") from error
