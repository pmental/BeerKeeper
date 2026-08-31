# BeerKeeper

**Current version: 0.0.40** — see [CHANGELOG.md](CHANGELOG.md) for release history. Security measures are summarized in [SECURITY.md](SECURITY.md).

A self-hosted tracker for a beer cellar and fridge: bottles, tasting
notes, drinking history, and trading. A single Python backend, a SQLite
database file, and a plain-JS frontend with no build step and no external
CDN calls. No third-party accounts, analytics, or API keys required.

## Features

- Password login and/or OIDC/SSO, with an admin page for managing users
  and instance settings — see "OIDC / SSO" and "Admin" below
- Optional SMTP email for password resets and welcome emails — see
  "Email (SMTP)" below
- Dark, light, or system-matched theme
- Track bottles in your cellar and/or fridge — quantity, size, bottle
  date, best-before date, notes — sortable by beer, brewery, or drink-by
  date, in imperial or metric units (metric by default)
- Autocomplete for beer, brewery, and style, backed by a shared database
  that grows as bottles are added, plus 210+ pre-populated breweries —
  see "Pre-populated breweries" below
- Quick actions per bottle: restock (+1), drink (logs a tasting note and
  rating), move between cellar and fridge
- Optional trading labels and a shareable wanted list — see "Trading and
  wanted lists" below
- Public cellar profiles with configurable privacy, a browse directory,
  and a recent-activity feed
- CSV import and export
- Comfortable or compact list view, remembered per browser

## OIDC / SSO

Set `CELLAR_OIDC_ENABLED=true` plus `CELLAR_OIDC_ISSUER`,
`CELLAR_OIDC_CLIENT_ID`, `CELLAR_OIDC_CLIENT_SECRET`, and `CELLAR_BASE_URL`
(see `.env.example`) to add a "Continue with SSO" button to the login
page. Works alongside password login, or set
`CELLAR_PASSWORD_AUTH_ENABLED=false` to make SSO the only way in.

**Account linking:** the first OIDC sign-in looks for a local account with
a matching, *verified* email (the provider's `email_verified` claim must
be true — an unverified match is never linked) and links to it if found;
otherwise it creates a new account from the provider's
`preferred_username` claim (with a numeric suffix on collision). Accounts
created this way get a random, unrecoverable password until one is set
from **Account → Change password**. If the provider sends a `name` (or
`given_name`/`family_name`) and a `picture` claim, they're used as the
display name and avatar shown in the nav — both stay in sync with the
provider on every login.

Register `<CELLAR_BASE_URL>/api/auth/oidc/callback` as an allowed
redirect URI with your provider. Any standard discovery-supporting OIDC
provider should work; if yours needs something unusual, you may need to
adjust `app/routers/oidc.py`. `CELLAR_OIDC_ISSUER` and `CELLAR_BASE_URL`
need a scheme (`https://`/`http://`) — if omitted, the app assumes
`https://` and logs a warning. Login failures land back on the login page
with a readable error instead of a blank 500.

## Admin

The first person to ever register (or log in via OIDC, if that's your
only auth method) automatically becomes an admin. Admins get an "Admin"
link in the nav (`#/admin`) for:

- Resetting any user's password directly
- Creating or deleting accounts, promoting/demoting other admins
- Turning new registrations on or off at runtime, independently of
  `CELLAR_PASSWORD_AUTH_ENABLED`
- Adding, renaming, or deleting breweries in the shared list (deleting is
  blocked while any beer still references one), plus CSV import/export
  for the whole list
- Downloading a full backup of the whole instance (every account, not
  just your own, plus your custom beer styles) as a single zip file, and
  restoring one — validated on upload, applied at the next restart rather
  than live

You can't remove the last admin or delete your own account from this
page. If a deployment ever ends up with zero admins, set
`CELLAR_ADMIN_USERNAMES` to a comma-separated list and restart — each one
is granted admin on every boot, as a recovery lever.

## Email (SMTP)

Configure via the admin page's "Email (SMTP)" panel, or `CELLAR_SMTP_*`
env vars (see `.env.example`) — env vars act as the default, the admin
panel overrides per field. Requires `CELLAR_BASE_URL` to be set. Supports
STARTTLS (default), implicit SSL, or no encryption, with optional auth.
Uses Python's built-in `smtplib` — no extra dependency.

## Trading and wanted lists

Turn on **Enable trading labels** (Account → Cellar preferences) to mark
bottles **For Trade** or **In Search Of**, and to track beers you don't
own yet on a **wanted list**. Once enabled, `#/u/<username>/trades` is a
public, no-login page listing both — independent of your general cellar
privacy setting, so you can keep your cellar private while still sharing
just this list. Get the shareable link from Account or from the trade
page itself.

## Beer styles

The Style field suggests from a list as you type. That list lives in a
plain text file, `beer_styles.txt`, in your data directory — one style
per line — seeded once from a built-in default on first boot. Edit the
file and restart to pick up changes:

```bash
docker compose exec beerkeeper sh -c 'echo "My Custom Style" >> /data/beer_styles.txt'
docker compose restart beerkeeper
```

## Pre-populated breweries

The database starts with 210+ real breweries — Swedish craft breweries,
major American and Belgian names, and a solid spread across the rest of
Europe (UK, Ireland, Germany, Austria, Czechia, Poland, the Nordics, and
the Baltics) — plus major cider makers and meaderies, so autocomplete is
useful from day one whether you're tracking beer, cider, or mead. Seeded
once, then managed from the admin page's "Breweries" panel — rename,
delete (once nothing references it), add, or bulk import/export as CSV.
Source list for the initial seed: `app/breweries_default.txt`.

## Upgrading an existing deployment

Pull the new code and rebuild/restart — `docker compose up -d --build`
(or the non-Docker equivalent). New database columns/tables are added
automatically on startup; existing data is untouched.

**Deploy from the same folder you originally used** — Docker Compose
derives its data volume name from the directory you run it in unless
pinned explicitly. If a fresh extract into a differently named folder
points at an empty volume, run `docker volume ls` to find your real one
(named `<something>_cellar-data`) and either move back to the original
folder or update `volumes:` in `docker-compose.yml` to match.

## Quick start (Docker)

1. Copy the env template and fill in a secret key:

   ```bash
   cp .env.example .env
   python3 -c "import secrets; print(secrets.token_hex(32))"
   # paste the output as CELLAR_SECRET_KEY= in .env
   ```

2. Build and run:

   ```bash
   docker compose up -d --build
   ```

3. Open `http://localhost:8000` (or whatever `CELLAR_PORT` you set) and
   create an account.

Your data lives in the `cellar-data` Docker volume (a SQLite file at
`/data/cellar.db` inside the container), so it survives rebuilds and
restarts. Put a reverse proxy (Caddy, Nginx, Traefik) in front for a real
domain and HTTPS.

## Running without Docker

Requires Python 3.11+.

```bash
pip install -r requirements.txt
export CELLAR_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
export CELLAR_DATA_DIR=./data
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Setting `CELLAR_SECRET_KEY` explicitly (as above) is recommended but not
required — if it's unset, a random key is generated and saved to
`CELLAR_DATA_DIR` on first boot instead. The Docker Compose path enforces
setting it explicitly; running this way does not, so it's worth doing
deliberately.

The SQLite database and static assets need no separate setup — tables are
created automatically on first boot.

## Configuration

| Variable            | Default          | Notes                                                                 |
|----------------------|------------------|------------------------------------------------------------------------|
| `CELLAR_SECRET_KEY`  | *(auto-generated)* | Signs login sessions. If unset, a random key is generated and saved to your data directory on first boot — works, but losing that directory invalidates every login. **Set this explicitly in production.** |
| `CELLAR_DATA_DIR`    | `/data`          | Where the SQLite database file lives.                                 |
| `CELLAR_PORT`        | `8000`           | Host port, used by `docker-compose.yml` only.                         |
| `CELLAR_PASSWORD_AUTH_ENABLED` | `true` | Set `false` to disable username/password login and registration (hides the forms too). |
| `CELLAR_OIDC_ENABLED` | `false`         | Set `true` to enable SSO. Requires the four `CELLAR_OIDC_*` vars below plus `CELLAR_BASE_URL`. |
| `CELLAR_OIDC_ISSUER` | *(none)*         | Your OIDC provider's issuer URL (discovery is fetched from `<issuer>/.well-known/openid-configuration`). |
| `CELLAR_OIDC_CLIENT_ID` / `CELLAR_OIDC_CLIENT_SECRET` | *(none)* | From your provider's application/client registration. |
| `CELLAR_OIDC_SCOPES` | `openid email profile` | Space-separated OAuth scopes to request. |
| `CELLAR_OIDC_BUTTON_LABEL` | `Continue with SSO` | Text on the login page's SSO button. |
| `CELLAR_BASE_URL`   | *(none)*          | This app's externally-reachable URL, no trailing slash. Required for OIDC and SMTP. |
| `CELLAR_ADMIN_USERNAMES` | *(none)*     | Comma/whitespace-separated usernames to force-grant admin on every boot. |
| `CELLAR_SMTP_HOST` / `CELLAR_SMTP_FROM_EMAIL` | *(none)* | Both required to enable outgoing email. |
| `CELLAR_SMTP_PORT` | `587`            | SMTP server port. |
| `CELLAR_SMTP_SECURITY` | `starttls`   | `starttls`, `ssl` (implicit TLS), or `none`. |
| `CELLAR_SMTP_USERNAME` / `CELLAR_SMTP_PASSWORD` | *(none)* | Leave blank if your relay doesn't require auth. |
| `CELLAR_SMTP_FROM_NAME` | `BeerKeeper` | Display name on outgoing mail. |
| `CELLAR_SMTP_SKIP_CERT_VERIFY` | `false` | Only for a self-signed internal relay — weakens that connection specifically. |

If `CELLAR_PASSWORD_AUTH_ENABLED=false` and OIDC isn't properly configured,
the app logs a startup warning and the login page shows a plain
"sign-in unavailable" message rather than a broken form.

## Backup and restore

Easiest: the admin page's "Backup and restore" panel — downloads a single
zip file with everything (the database *and* `beer_styles.txt`, which
lives outside the database as its own file), and restores one (validated
on upload, applied on the next restart, not live).

For a manual copy, there are two files, both in your data directory/volume:
`cellar.db` (plus the `-wal`/`-shm` companion files SQLite uses while
running) and `beer_styles.txt`.

```bash
docker compose exec beerkeeper sh -c "sqlite3 /data/cellar.db '.backup /data/backup.db'"
docker cp $(docker compose ps -q beerkeeper):/data/backup.db ./cellar-backup.db
docker cp $(docker compose ps -q beerkeeper):/data/beer_styles.txt ./beer_styles-backup.txt
```

To restore manually, stop the container, replace both files in the
volume with your backups, and start it again. Each user can also
self-serve a partial backup any time via **Import / Export → Download
CSV**.

## CSV format

Export produces (and import expects) these columns:

```
brewery, beer, style, abv, location, custom_location, quantity, size_oz,
bottle_date, best_before, batch_notes, trade_status
```

`location` is `cellar` or `fridge`; `trade_status` is `none`, `ft`, or
`iso`; dates are `YYYY-MM-DD`. `size_oz` is always in fluid ounces
regardless of your account's unit display setting. Importing reuses an
existing beer/brewery by name if one matches, otherwise creates it.

## Architecture

- **Backend**: FastAPI + SQLAlchemy + SQLite (`app/`), JWT auth (plus
  optional OIDC via Authlib), one process serves both the JSON API
  (`/api/...`) and the static frontend.
- **Frontend**: no framework, no build step — plain HTML/CSS/JS in
  `static/`, hash-routed single-page app (`static/js/app.js` is the router,
  `pages.js` renders each screen, `api.js` wraps `fetch`, `theme.js` handles
  dark/light/system theme switching).
- **Fonts**: Fraunces and Inter, self-hosted as woff2 files in
  `static/fonts/` — no Google Fonts or other CDN calls at runtime.
- **Theming**: CSS custom properties keyed by role (`--bg`, `--text`,
  `--accent`, etc.) in `static/css/style.css`, with a `[data-theme="light"]`
  override block.

## License

MIT — do whatever you'd like with it.
