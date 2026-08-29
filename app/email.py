import logging
import smtplib
import ssl
from email.message import EmailMessage

from app import config

logger = logging.getLogger("beerkeeper.email")


def _tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    if config.SMTP_SKIP_CERT_VERIFY:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


def send_email(to_email: str, subject: str, body_text: str) -> None:
    """Low-level send. Raises on failure - callers (background tasks) are
    expected to catch and log rather than let it break the request that
    triggered it, since a broken mail server should never break signup,
    login, or password changes themselves."""
    if not config.SMTP_ENABLED:
        raise RuntimeError("SMTP is not configured on this instance.")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{config.SMTP_FROM_NAME} <{config.SMTP_FROM_EMAIL}>" if config.SMTP_FROM_NAME else config.SMTP_FROM_EMAIL
    msg["To"] = to_email
    msg.set_content(body_text)

    if config.SMTP_SECURITY == "ssl":
        with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, context=_tls_context()) as server:
            if config.SMTP_USERNAME:
                server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
            server.send_message(msg)
    else:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            if config.SMTP_SECURITY == "starttls":
                server.starttls(context=_tls_context())
            if config.SMTP_USERNAME:
                server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
            server.send_message(msg)


def send_email_safely(to_email: str, subject: str, body_text: str) -> None:
    """Same as send_email, but swallows and logs errors instead of raising -
    for use in BackgroundTasks, where there's no request left to return an
    error on and a mail hiccup should never look like the action (signup,
    password reset request, ...) itself failed."""
    try:
        send_email(to_email, subject, body_text)
    except Exception:
        logger.exception("Failed to send email to %s (subject: %s)", to_email, subject)


def send_welcome_email(to_email: str, username: str) -> None:
    subject = f"Welcome to {config.APP_NAME}"
    body = (
        f"Hi {username},\n\n"
        f"An account has been created for you on {config.APP_NAME}, a self-hosted "
        f"beer cellar tracker.\n\n"
        f"Username: {username}\n"
        f"Log in here: {config.BASE_URL}/#/login\n\n"
        f"If you don't have a password yet, use \"Forgot password?\" on the login "
        f"page to set one.\n"
    )
    send_email_safely(to_email, subject, body)


def send_password_reset_email(to_email: str, username: str, raw_token: str) -> None:
    reset_link = f"{config.BASE_URL}/#/reset-password?token={raw_token}"
    subject = f"Reset your {config.APP_NAME} password"
    body = (
        f"Hi {username},\n\n"
        f"Someone requested a password reset for your {config.APP_NAME} account. "
        f"If that was you, set a new password here:\n\n"
        f"{reset_link}\n\n"
        f"This link works once and expires in 1 hour. If you didn't request this, "
        f"you can safely ignore this email - your password hasn't been changed.\n"
    )
    send_email_safely(to_email, subject, body)
