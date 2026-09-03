# BeerKeeper

**Current version: 0.0.62** — see [CHANGELOG.md](CHANGELOG.md) for release history. Security measures are summarized in [SECURITY.md](SECURITY.md).

A self-hosted tracker for a beer cellar and fridge: bottles, tasting
notes, drinking history, and trading. A single Python backend, a SQLite
database file, and a plain-JS frontend with no build step and no external
CDN calls. No third-party accounts, analytics, or API keys required.

- [Features](#features)
- [Quick start (Docker)](#quick-start-docker)
- [Running without Docker](#running-without-docker)
- [Configuration](#configuration)
- [OIDC / SSO](#oidc--sso)
- [Admin](#admin)
- [Email (SMTP)](#email-smtp)
- [Trading and wanted lists](#trading-and-wanted-lists)
- [Beer styles](#beer-styles)
- [Pre-populated breweries](#pre-populated-breweries)
- [Upgrading an existing deployment](#upgrading-an-existing-deployment)
- [Backup and restore](#backup-and-restore)
- [Beer cellar CSV format](#beer-cellar-csv-format)
- [Architecture](#architecture)
- [Screenshots](#screenshots)
- [License](#license)

## Features

- Track bottles in your cellar and/or fridge — quantity, size, bottle
  date, drink-by date, notes — sortable by beer, brewery, or drink-by
  date, searchable by beer name, in imperial or metric units (metric by
  default)
- Autocomplete for beer, brewery, and style, backed by a shared database
  that grows as bottles are added, plus 10,400+ pre-populated breweries —
  see "Pre-populated breweries" below
- Optional trading labels and a shareable wanted list — see "Trading and
  wanted lists" below
- Public cellar profiles with configurable privacy, a browse directory,
  and a recent-activity feed
- Password login and/or OIDC/SSO, with an admin page for managing users
  and instance settings — see "OIDC / SSO" and "Admin" below
- Optional SMTP email for password resets and welcome emails — see
  "Email (SMTP)" below

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

## OIDC / SSO

Set `CELLAR_OIDC_ENABLED=true` plus `CELLAR_OIDC_ISSUER`,
`CELLAR_OIDC_CLIENT_ID`, `CELLAR_OIDC_CLIENT_SECRET`, and `CELLAR_BASE_URL`
(see `.env.example`) to add a "Continue with SSO" button to the login
page. Works alongside password login, or set
`CELLAR_PASSWORD_AUTH_ENABLED=false` to make SSO the only way in.

Register `<CELLAR_BASE_URL>/api/auth/oidc/callback` as an allowed
redirect URI with your provider. `CELLAR_OIDC_ISSUER` and `CELLAR_BASE_URL`
need a scheme (`https://`/`http://`) — if omitted, the app assumes
`https://` and logs a warning.

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
- The same for beers - name, brewery, style, ABV, and external link are
  all editable, and a beer can only be deleted once nothing (cellar,
  history, or wanted list) references it
- Adding, renaming, or deleting beer styles in the shared suggestion
  list - see "Beer styles" below
- Downloading a full backup of the whole instance (every account, not
  just your own) as a single zip file, and restoring one — validated on
  upload, applied at the next restart rather than live

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

The Style field suggests from a list as you type — a hand-picked default
set of ~105 styles, seeded into the database once on first boot. Managed
from the admin page's "Beer Styles" panel from that point on: add,
rename, or delete freely. Like the brewery list, it's just suggestions;
typing something not on the list is always fine.

## Pre-populated breweries

The database starts with 10,400+ real, currently-operating breweries — a hand-picked starting set (Swedish craft breweries, major American and Belgian names, cider makers and meaderies, and a spread across the rest of Europe), plus a bulk import from [Open Brewery DB](https://www.openbrewerydb.org/) covering the US and 20+ other countries.

Seeded once, then managed from the admin page's "Breweries" panel —
rename, delete (once nothing references it), add, or bulk import/export
as CSV.
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

## Backup and restore

Easiest: the admin page's "Backup and restore" panel — downloads a single
zip file with a snapshot of the whole database (validated on upload,
restore applied on the next restart, not live).

For a manual copy, everything lives in one file in your data
directory/volume: `cellar.db` (plus the `-wal`/`-shm` companion files
SQLite uses while running).

```bash
docker compose exec beerkeeper sh -c "sqlite3 /data/cellar.db '.backup /data/backup.db'"
docker cp $(docker compose ps -q beerkeeper):/data/backup.db ./cellar-backup.db
```

To restore manually, stop the container, replace that file in the
volume with your backup, and start it again. Each user can also
self-serve a partial backup of just their own cellar any time from
**Account → Cellar data → Download CSV**.

## Beer cellar CSV format

A cellar export produces (and cellar import expects) these columns:

```
brewery, beer, style, abv, location, custom_location, quantity, size_oz,
size_ml, bottle_date, best_before, batch_notes, trade_status
```

`location` is `cellar` or `fridge`; `trade_status` is `none`, `ft`, or
`iso`; dates are `YYYY-MM-DD`. Export always fills in both `size_oz` and
`size_ml` (converted from the one value actually stored), so the file is
usable regardless of which unit system opens it next. Import reads
whichever of the two matches the importing account's own unit setting,
falling back to the other column if that one's blank - handles a
hand-edited file that only has one, or one produced by an install with
the opposite default. Importing reuses an existing beer/brewery by name
if one matches, otherwise creates it.

## Architecture

- **Backend**: FastAPI + SQLAlchemy + SQLite (`app/`), JWT auth (plus
  optional OIDC via Authlib), one process serves both the JSON API
  (`/api/...`) and the static frontend.
- **Frontend**: no framework, no build step — plain HTML/CSS/JS in
  `static/`, hash-routed single-page app (`static/js/app.js` is the router,
  `pages.js` renders each screen, `api.js` wraps `fetch`, `theme.js` handles
  dark/light/system theme switching).

## Screenshots
<img width="1229" height="982" alt="image" src="https://github.com/user-attachments/assets/c4b606c0-720e-460a-9cb6-3326a0e8d2c7" />
<img width="1229" height="984" alt="image" src="https://github.com/user-attachments/assets/be122cc5-45fa-46c3-a7f0-446beef4d6a7" />

## License

MIT — do whatever you'd like with it.
