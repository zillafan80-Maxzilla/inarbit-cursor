import asyncio
import logging
import os
import smtplib
from email.message import EmailMessage
from typing import Iterable, Optional


logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _split_recipients(value: Optional[str]) -> list[str]:
    if not value:
        return []
    parts = [item.strip() for item in value.replace(";", ",").split(",")]
    return [item for item in parts if item]


def _send_email_sync(
    *,
    subject: str,
    body: str,
    to_addrs: Iterable[str],
    host: str,
    port: int,
    username: Optional[str],
    password: Optional[str],
    sender: str,
    use_tls: bool,
    use_ssl: bool,
    timeout: int,
) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(to_addrs)
    msg.set_content(body)

    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=timeout) as smtp:
            if username:
                smtp.login(username, password or "")
            smtp.send_message(msg)
        return

    with smtplib.SMTP(host, port, timeout=timeout) as smtp:
        if use_tls:
            smtp.starttls()
        if username:
            smtp.login(username, password or "")
        smtp.send_message(msg)


async def send_alert_email(
    *,
    subject: str,
    body: str,
    to_addrs: Optional[Iterable[str]] = None,
) -> None:
    if not _env_bool("EMAIL_ALERTS_ENABLED", default=False):
        return

    host = (os.getenv("SMTP_HOST") or "").strip()
    if not host:
        return

    recipients = list(to_addrs or _split_recipients(os.getenv("ALERT_EMAIL_TO")))
    if not recipients:
        return

    sender = (os.getenv("SMTP_FROM") or "").strip()
    if not sender:
        sender = os.getenv("SMTP_USER", "").strip()
    if not sender:
        return

    try:
        port = int(os.getenv("SMTP_PORT", "587").strip() or "587")
    except Exception:
        port = 587

    timeout = 10
    try:
        timeout = int(os.getenv("SMTP_TIMEOUT", "10").strip() or "10")
    except Exception:
        timeout = 10

    use_tls = _env_bool("SMTP_TLS", default=True)
    use_ssl = _env_bool("SMTP_SSL", default=False)

    try:
        await asyncio.to_thread(
            _send_email_sync,
            subject=subject,
            body=body,
            to_addrs=recipients,
            host=host,
            port=port,
            username=os.getenv("SMTP_USER"),
            password=os.getenv("SMTP_PASSWORD"),
            sender=sender,
            use_tls=use_tls,
            use_ssl=use_ssl,
            timeout=timeout,
        )
    except Exception as exc:
        logger.warning("email alert failed: %s", exc)
