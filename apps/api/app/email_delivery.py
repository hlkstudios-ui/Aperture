import asyncio
import smtplib
from email.message import EmailMessage
from urllib.parse import urlsplit

from app.config import get_settings


def _public_origin(value: str | None) -> str:
    candidate = value or str(get_settings().web_origin)
    parsed = urlsplit(candidate)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise RuntimeError("Password-reset storefront origin is invalid")
    return f"{parsed.scheme}://{parsed.netloc}"


def _send_password_reset(
    email: str, token: str, brand_name: str, public_origin: str | None = None
) -> None:
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
    reset_url = f"{_public_origin(public_origin)}/reset-password?token={token}"
    safe_brand_name = " ".join(brand_name.split())[:60] or "Your streaming service"
    message = EmailMessage()
    message["Subject"] = f"Reset your {safe_brand_name} password"
    message["From"] = settings.smtp_from_email
    message["To"] = email
    message.set_content(
        f"A password reset was requested for your {safe_brand_name} account.\n\n"
        f"Open this one-time link within 30 minutes:\n{reset_url}\n\n"
        "If you did not request this, you can ignore this message."
    )
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


async def send_password_reset(
    email: str, token: str, brand_name: str, public_origin: str | None = None
) -> None:
    try:
        await asyncio.to_thread(_send_password_reset, email, token, brand_name, public_origin)
    except (OSError, smtplib.SMTPException) as error:
        raise RuntimeError("Transactional email delivery failed") from error
