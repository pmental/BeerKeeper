import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

from app import config

logger = logging.getLogger("beerkeeper.email")


@dataclass
class ResolvedSmtp:
    host: str
    port: int
    security: str
    username: str
    password: str
    from_email: str
    from_name: str
    skip_cert_verify: bool
    enabled: bool


def _first(*values):
    """First value that's a non-empty string (or non-None for non-strings)."""
    for v in values:
        if v is not None and v != "":
            return v
    return None


def resolve_smtp_settings(db=None) -> ResolvedSmtp:
    """Merge admin-panel settings (database, editable at runtime) over
    env-var config (set at deploy time): a blank field in the database
    means "fall back to the env var". Accepts an existing session so
    callers already holding one (e.g. a request handler) don't open a
    second one; opens and closes its own otherwise (e.g. from a
    BackgroundTask, which runs after the request's session is gone)."""
    from app import models
    from app.database import SessionLocal

    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        row = db.query(models.InstanceSettings).filter(models.InstanceSettings.id == 1).first()
        host = _first(row and row.smtp_host, config.SMTP_HOST)
        port = _first(row and row.smtp_port, config.SMTP_PORT)
        security = _first(row and row.smtp_security, config.SMTP_SECURITY)
        username = _first(row and row.smtp_username, config.SMTP_USERNAME) or ""
        password = _first(row and row.smtp_password, config.SMTP_PASSWORD) or ""
        from_email = _first(row and row.smtp_from_email, config.SMTP_FROM_EMAIL)
        from_name = _first(row and row.smtp_from_name, config.SMTP_FROM_NAME) or config.APP_NAME
        skip_verify = row.smtp_skip_cert_verify if row and row.smtp_skip_cert_verify is not None else None
        if skip_verify is None:
            skip_verify = config.SMTP_SKIP_CERT_VERIFY

        return ResolvedSmtp(
            host=host or "",
            port=int(port) if port else 587,
            security=security or "starttls",
            username=username,
            password=password,
            from_email=from_email or "",
            from_name=from_name,
            skip_cert_verify=bool(skip_verify),
            enabled=bool(host and from_email and config.BASE_URL),
        )
    finally:
        if close_db:
            db.close()


def is_smtp_enabled(db=None) -> bool:
    return resolve_smtp_settings(db).enabled


def _tls_context(skip_verify: bool) -> ssl.SSLContext:
    context = ssl.create_default_context()
    if skip_verify:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


def send_email(to_email: str, subject: str, body_text: str, smtp: "ResolvedSmtp | None" = None) -> None:
    """Low-level send. Raises on failure - callers (background tasks) are
    expected to catch and log rather than let it break the request that
    triggered it, since a broken mail server should never break signup,
    login, or password changes themselves."""
    smtp = smtp or resolve_smtp_settings()
    if not smtp.enabled:
        raise RuntimeError("SMTP is not configured on this instance.")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{smtp.from_name} <{smtp.from_email}>" if smtp.from_name else smtp.from_email
    msg["To"] = to_email
    msg.set_content(body_text)

    if smtp.security == "ssl":
        with smtplib.SMTP_SSL(smtp.host, smtp.port, context=_tls_context(smtp.skip_cert_verify)) as server:
            if smtp.username:
                server.login(smtp.username, smtp.password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(smtp.host, smtp.port) as server:
            if smtp.security == "starttls":
                server.starttls(context=_tls_context(smtp.skip_cert_verify))
            if smtp.username:
                server.login(smtp.username, smtp.password)
            server.send_message(msg)


def send_email_safely(to_email: str, subject: str, body_text: str) -> None:
    """Same as send_email, but swallows and logs errors instead of raising -
    for use in BackgroundTasks, where there's no request left to return an
    error on and a mail hiccup should never look like the action (signup,
    password reset request, ...) itself failed. Resolves its own settings
    from a fresh DB session, since a BackgroundTask runs after the
    request's own session has already closed."""
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


def send_test_email(to_email: str) -> None:
    """Raises on failure, deliberately - unlike the other senders, this one
    is called directly from a request (the admin's "send test email"
    button) so the admin gets an immediate, specific error instead of
    having to go check the server logs."""
    subject = f"{config.APP_NAME} test email"
    body = (
        f"If you're reading this, your SMTP settings are working correctly.\n\n"
        f"This is a test message from {config.APP_NAME}'s admin panel - no action needed.\n"
    )
    send_email(to_email, subject, body)
