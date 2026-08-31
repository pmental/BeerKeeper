# Security

A brief summary of the security measures in this project, not an exhaustive
audit trail.

## Authentication & sessions

- Passwords are hashed with bcrypt (per-password salt, never stored or
  logged in plain text).
- Sessions are JWTs (HS256, algorithm explicitly pinned on decode) signed
  with `CELLAR_SECRET_KEY`. If that's not set, a random key is generated
  and persisted to the data directory on first boot rather than falling
  back to a shared default - set it explicitly in production.
- Changing or resetting a password immediately invalidates any other
  token already issued for that account, so a leaked token stops working
  the moment the account is secured - not just when it naturally expires
  (tokens last 30 days).
- Login, registration, and forgot-password are rate-limited per IP.
- OIDC account linking only auto-links to an existing local account when
  the provider marks the email `email_verified` - an unverified email
  claim can't be used to take over someone else's account.
- Changing your account's email requires re-entering your current
  password, and (if outgoing mail is configured) sends a notice to the
  old address.

## Application

- Every cellar/consumption/wanted-list endpoint scopes its query to the
  authenticated user - there's no way to read or modify another
  account's data by guessing an ID.
- All database access goes through SQLAlchemy's parameterized query
  builder; the only raw SQL is static DDL in schema migrations, never
  built from request input.
- The frontend consistently HTML-escapes user-supplied content
  (beer/brewery names, notes, display names, etc.) before inserting it
  into the page, and has no inline scripts or inline event handlers -
  enforced by a Content-Security-Policy with `script-src 'self'`.
- User-supplied URLs that get rendered as clickable links (a beer's
  external reference link, a brewery's website) only accept `http(s)`
  schemes - a link is a real, if narrow, stored-XSS vector otherwise.
- Additional response headers: `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`.
- File uploads (CSV import, backup restore) are capped and read in
  bounded chunks rather than loaded into memory unbounded.
- Full-instance backup restores are validated (integrity-checked, schema
  sanity-checked) before being accepted, and only ever applied at the
  next clean startup - never against a live, in-use database.
- No CORS headers are sent, so no other origin can read this app's API
  responses from a browser.
- The container runs as a non-root user.

## Reporting an issue

This is a self-hosted hobby project without a formal disclosure program.
If you find a real vulnerability, please open a private report (e.g. a
GitHub security advisory on the repository) rather than a public issue.
