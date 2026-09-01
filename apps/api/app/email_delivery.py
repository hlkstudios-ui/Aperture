import asyncio
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from urllib.parse import quote, urlsplit

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
        raise RuntimeError("Public application origin is invalid")
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
    _send_message(message)


def _send_message(message: EmailMessage) -> None:
    settings = get_settings()
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_starttls:
            smtp.starttls(context=ssl.create_default_context())
        smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


def _send_platform_email_verification(email: str, token: str, expires_at: datetime) -> None:
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
    verification_url = (
        f"{_public_origin(str(settings.web_origin))}/marketplace"
        f"#verify-email={quote(token, safe='')}"
    )
    message = EmailMessage()
    message["Subject"] = "Verify your Apertures platform account"
    message["From"] = settings.smtp_from_email
    message["To"] = email
    message.set_content(
        "Verify the email address for your Apertures platform account.\n\n"
        f"Open this one-time link before {expires_at.isoformat()}:\n{verification_url}\n\n"
        "If your browser does not open the verification flow, paste this one-time token "
        f"into the marketplace dialog:\n{token}\n\n"
        "If you did not create this account, you can ignore this message."
    )
    _send_message(message)


async def send_password_reset(
    email: str, token: str, brand_name: str, public_origin: str | None = None
) -> None:
    try:
        await asyncio.to_thread(_send_password_reset, email, token, brand_name, public_origin)
    except (OSError, smtplib.SMTPException) as error:
        raise RuntimeError("Transactional email delivery failed") from error


async def send_platform_email_verification(
    email: str,
    token: str,
    expires_at: datetime,
) -> None:
    try:
        await asyncio.to_thread(_send_platform_email_verification, email, token, expires_at)
    except (OSError, smtplib.SMTPException) as error:
        raise RuntimeError("Transactional email delivery failed") from error
