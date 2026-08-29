# BeerKeeper

**Current version: 0.0.18** — see [CHANGELOG.md](CHANGELOG.md) for release history.

A self-hosted tracker for a beer cellar and fridge: bottles, batches, tasting
notes, drinking history, and trading labels. It's an original build inspired
by the general idea of cellar-tracking apps (accounts, an in-cellar/in-fridge
inventory, drink/move/add actions, notes that persist independently of your
inventory, public shareable profiles) — it isn't affiliated with, and doesn't
reuse any code, design, or content from, any existing site.

Everything runs on your own server: a single Python backend, a SQLite
database file, and a plain-JS frontend with no build step and no external
CDN calls (fonts are bundled locally). No third-party accounts, analytics,
or API keys required.

## Features

- Accounts with your own login (JWT-based sessions), or sign in via any
  OpenID Connect provider, or both at once
- Shows your OIDC provider's first name (from its `name`, or
  `given_name`/`family_name`, claim) instead of your username throughout
  the app, when one is available
- Optionally disable password login entirely and run on SSO only
- An admin page for resetting passwords, creating/deleting accounts, and
  turning registration on or off without touching env vars — see "Admin"
  below
- Optional SMTP email: self-service password reset and welcome emails on
  new accounts — see "Email (SMTP)" below
- Dark, light, or system-matched theme, switchable from the top bar
- Track bottles In Cellar and/or In Fridge, with quantity, size, bottle
  date, best-before date, and free-form batch notes
- Sort your cellar by beer, brewery, or drink-by date (soonest-expiring
  first), as a default account preference or switched on the fly
- Choose imperial (oz) or metric (mL) units per account — bottle sizes are
  stored internally in ounces and converted for display/entry, so switching
  the setting doesn't lose or corrupt existing data
- Dates display in ISO format (`YYYY-MM-DD`) throughout the app
- Adding a bottle autocompletes both the beer and brewery fields, and
  ranks *your own* previously-used beers/breweries first, so re-adding
  something you've had before — or adding a new beer from a brewery
  you've already logged — doesn't mean retyping everything or risking a
  duplicate brewery entry
- The Style field suggests from an editable list of beer styles (see
  below) instead of being a bare text box
- Comes with over 130 real breweries already in the database (Swedish
  craft breweries plus major American, Belgian, and other international
  names) so brewery autocomplete is useful before you've added anything
  yourself
- Quick actions per bottle: **+1** to restock, **Drink** (logs a tasting
  note + rating and decrements your count), **Move** between cellar/fridge
- Tasting notes and drinking history are stored independently of your
  cellar entries, so they survive even after you delete an empty entry
- Optional trading labels (For Trade / In Search Of), plus a "wanted"
  list for beers you don't own yet, and a public trade/wanted page you
  can share without a login — see "Trading and wanted lists" below
- Per-account privacy controls: make your cellar public or private, and
  separately choose whether tasting notes and best-before dates show up
  on your public profile
- A public "Browse cellars" directory and a home-page feed of what people
  have recently had
- CSV import and export of your whole cellar
- A shared, community-editable beer/brewery database — adding a bottle
  reuses an existing beer/brewery if one already matches, or creates one

### Known limitations

This is a from-scratch build, not a 1:1 port, so a few things common to
hosted community sites were deliberately left out to keep a self-hosted
deploy simple:

- **No email.** There's no outgoing mail server configured, so there's no
  "forgot password" flow — only a "change password while logged in" form.
  If you lock yourself out and password auth is your only login method,
  reset a password directly in the database (see below), or configure OIDC
  so you have a second way in.
- **No user-to-user messaging.** Trading labels and public profiles work,
  but there's no in-app inbox. Easy to add later if you want it.

## OIDC / SSO

Set `CELLAR_OIDC_ENABLED=true` plus `CELLAR_OIDC_ISSUER`,
`CELLAR_OIDC_CLIENT_ID`, `CELLAR_OIDC_CLIENT_SECRET`, and `CELLAR_BASE_URL`
(see `.env.example` for details on each) to add a "Continue with SSO"
button to the login page. This works alongside password login, or you can
turn password login off entirely with `CELLAR_PASSWORD_AUTH_ENABLED=false`
to make SSO the only way in.

**Account linking:** the first time someone signs in via OIDC, the app
looks for a local account with a matching email address. If one exists (and
isn't already linked to a different OIDC identity), that login gets linked
to it. Otherwise a new account is created automatically, using the
provider's `preferred_username` claim (falling back to the email's local
part, then a generic name) with a numeric suffix added if there's a
collision. Accounts created this way get a random, unrecoverable password —
password login is effectively unusable for them unless they later set a
real password from **Account → Change password** (only available if
password auth is enabled instance-wide).

Register `<CELLAR_BASE_URL>/api/auth/oidc/callback` as an allowed redirect
URI with your provider. Any standard OIDC provider that supports discovery
should work — this has been tested against a spec-compliant mock provider
exercising the full authorization-code + PKCE-less flow with RS256-signed
ID tokens; if your provider needs something unusual (e.g. no discovery
endpoint, or a non-standard claim for username), you may need to adjust
`app/routers/oidc.py`.

`CELLAR_OIDC_ISSUER` and `CELLAR_BASE_URL` need a scheme (`https://` or
`http://`). If you forget it, the app assumes `https://`, logs a warning
saying so at startup, and carries on — it won't silently misbehave, but
it's worth fixing the env var rather than relying on the guess. If login
itself fails for any reason (unreachable issuer, bad TLS cert, provider
outage), you'll land back on the login page with a readable error message
instead of a blank 500 page; check `docker compose logs` for the full
traceback if the on-page message isn't enough to diagnose it.

## Admin

The first person to ever register (or log in via OIDC, if that's your
only auth method) automatically becomes an admin — nothing to configure.
Admins get an "Admin" link in the nav, leading to `#/admin`, where you
can:

- **Reset any user's password** directly (they aren't emailed — you tell
  them the new one yourself, since there's no mail server involved
  anywhere in this app)
- **Create accounts** without going through the registration form
- **Promote or demote** other admins
- **Delete a user**, which cascades their entire cellar, drinking
  history, and wanted list — there's no undo
- **Turn registration on or off** independently of `CELLAR_PASSWORD_AUTH_ENABLED`:
  this is a runtime, database-backed toggle (no restart needed), so you
  can let people sign up during initial setup and then lock it down,
  while existing accounts — password and OIDC alike — keep working
  exactly as before

A couple of safety rails: you can't delete or remove admin from the last
remaining admin (the API rejects it outright), and you can't delete your
own account from this page.

If a deployment somehow ends up with zero admins (shouldn't happen given
the auto-promotion above, but self-hosted things go sideways sometimes),
set `CELLAR_ADMIN_USERNAMES` to a comma-separated list of usernames and
restart — each one is granted admin on boot, every boot, as a recovery
lever rather than the normal way to manage admins.

## Email (SMTP)

Configure this either in the admin page's "Email (SMTP)" panel (host,
port, security mode, credentials, from-address, and a "send test email"
button for immediate feedback — no restart needed) or via `CELLAR_SMTP_*`
env vars (see `.env.example` for the full list). Both work together: the
admin panel is a per-field override, so anything left blank there falls
back to its matching env var if one is set — handy if you want the basics
baked into your deployment but the admin able to tweak things without
touching the server. Uses Python's built-in `smtplib` — no new dependency.
Supports STARTTLS (the default), implicit SSL, or no encryption at all
for a trusted local relay. Also requires `CELLAR_BASE_URL` to already be
set, since emailed links need to be absolute.

Two things this powers:

- **Forgot password**, a proper self-service flow (a "Forgot password?"
  link appears on the login page once email is configured) — previously
  the only option was an admin resetting your password for you. Reset
  links are single-use and expire after an hour; only a hash of the token
  is ever stored, the raw token exists only in the email itself.
- **Welcome emails** on new accounts — sent automatically for
  self-registration and for a brand-new OIDC identity's first login, and
  optionally for admin-created users via a checkbox in the "Add user"
  form (unchecked automatically, with an explanatory note, if email isn't
  configured).

If your mail server is on a self-signed certificate (common for an
internal relay), turn on "Skip certificate verification" in the admin
panel (or set `CELLAR_SMTP_SKIP_CERT_VERIFY=true`) — off by default,
since it does weaken the connection to that server specifically.

The stored password is never sent back to the browser once saved — the
field always shows blank with a placeholder note that one's already set,
the same way a login password field never shows what's stored. Saving
other settings without retyping it leaves it untouched; there's a
dedicated "clear the stored password" checkbox for when you actually want
to remove it.

## Trading and wanted lists

Turn on **Enable trading labels** (Account → Cellar preferences) to mark
individual bottles as **For Trade** or **In Search Of** from the add/edit
bottle form, and to track beers you don't own yet on a separate **wanted
list** (Cellar page → "+ Add to wanted list", or from your trade page
directly). Wanted entries are just a beer and an optional note — no
quantity or location, since you don't have any yet — and never affect
your cellar count.

Once trading is enabled, everyone gets a page at `#/u/<username>/trades`
combining:
- **For Trade**: your bottles marked FT (with quantity, matching what's
  on your cellar entry)
- **Wanted**: both kinds of "want" — beers you don't own at all, and
  beers you already have some of but marked ISO because you want more
  (labeled "Have some, want more" so it's clear which is which)

This page is public and requires no login to view, and is **deliberately
independent of your cellar-privacy setting** — you can keep your whole
cellar private while still sharing just this focused trade/wanted list.
Get your shareable link (with a one-click copy button) from Account once
trading is enabled, or from the trade page itself when you're viewing
your own. Visiting someone else's trade page only ever shows what they're
trading or looking for — no management controls, no matter who's logged
in.

## Beer styles

The Style field on the add/edit bottle form suggests from a list of beer
styles as you type (a small dropdown filtered against what you've typed —
not a native `<datalist>`, since browser support for those is inconsistent;
you can still type anything not on the list). That list lives in a plain
text file, `beer_styles.txt`, inside your data directory (the `cellar-data`
Docker volume) — one style per line, blank lines and `#` comments ignored.
It's seeded once from a built-in default (a general beer-style taxonomy,
organized roughly the way BeerAdvocate groups its own style guide, though
not a verified exact mirror of their current list) the first time the app
boots. After that, edit the file directly and restart the app to pick up
changes — there's deliberately no in-app editor for it:

```bash
docker compose exec beerkeeper sh -c 'echo "My Custom Style" >> /data/beer_styles.txt'
docker compose restart beerkeeper
```

or just edit it directly if you've bind-mounted the data directory instead
of using a named volume.

## Pre-populated breweries

The database starts with over 130 real breweries already in it, so the
brewery field has useful suggestions from day one instead of only showing
whatever you've personally logged. It leans Swedish (29 craft breweries,
sourced from craft-beer press coverage and Wikipedia, cross-checked where
possible — not an exhaustive or official registry) plus a substantial set
of American (53) and Belgian (29, including all six official Trappist
breweries) names, and smaller sets from the UK, Germany, the Netherlands,
Denmark, Norway, and Estonia.

Unlike beer styles, this isn't a file read fresh on every request — these
become ordinary `Brewery` rows in the database. Each brewery name is
tracked individually (in `.breweries_seeded_names` in your data
directory) once it's been added, so a future update that adds more
breweries to the default list will reach your existing install on its
next restart — while anything you've deliberately deleted stays deleted
and won't quietly come back. From that point on, breweries are managed
entirely through the app itself: rename, delete, or add more the same way
you would any brewery you typed in yourself. The source list is
`app/breweries_default.txt` if you want to see exactly what's in it or
change the default for a fresh install.

## Upgrading an existing deployment

If you already have this running with data in it, just pull the new code
and rebuild/restart — `docker compose up -d --build` (or the non-Docker
equivalent). The app adds any new database columns or tables it needs
automatically on startup; nothing manual is required, and existing
bottles, notes, and accounts are untouched. New accounts default to
imperial units and get the new preference available immediately in
**Account → Cellar preferences**.

**Deploy from the same folder you originally used.** Docker Compose
derives its default project name (and therefore the actual name of your
data volume) from the directory you run `docker compose` in, unless it's
been pinned explicitly. If you extract a new release into a differently
named folder and it ends up pointing at an empty volume instead of your
existing data, run `docker volume ls` to find your real volume (it'll be
named `<something>_cellar-data`), then either move back to the original
folder name or add `- <that-exact-name>:/data` under `volumes:` in place
of the default `cellar-data` entry.

The Docker Compose service is named `beerkeeper` (renamed from `cellar`
in an earlier release — purely cosmetic, it never touched your data since
the volume name itself is unchanged). If an old `cellar` container is
still around from before that rename, `docker compose up -d --remove-orphans`
will clean it up.

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
restarts. To put this behind a real domain, put a reverse proxy (Caddy,
Nginx, Traefik) in front of it and point it at container port 8000 — that
also gets you HTTPS for free with most of those.

## Running without Docker

Requires Python 3.11+.

```bash
pip install -r requirements.txt
export CELLAR_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
export CELLAR_DATA_DIR=./data
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The SQLite database and static assets need no separate setup — tables are
created automatically on first boot.

## Configuration

| Variable            | Default          | Notes                                                                 |
|----------------------|------------------|------------------------------------------------------------------------|
| `CELLAR_SECRET_KEY`  | *(insecure dev key)* | **Set this in production.** Signs login sessions; keep it private and stable. |
| `CELLAR_DATA_DIR`    | `/data`          | Where the SQLite database file lives.                                 |
| `CELLAR_PORT`        | `8000`           | Host port, used by `docker-compose.yml` only.                         |
| `CELLAR_PASSWORD_AUTH_ENABLED` | `true` | Set `false` to disable username/password login and registration (hides the forms too). |
| `CELLAR_OIDC_ENABLED` | `false`         | Set `true` to enable SSO. Requires the four `CELLAR_OIDC_*` vars below plus `CELLAR_BASE_URL`. |
| `CELLAR_OIDC_ISSUER` | *(none)*         | Your OIDC provider's issuer URL (discovery is fetched from `<issuer>/.well-known/openid-configuration`). |
| `CELLAR_OIDC_CLIENT_ID` / `CELLAR_OIDC_CLIENT_SECRET` | *(none)* | From your provider's application/client registration. |
| `CELLAR_OIDC_SCOPES` | `openid email profile` | Space-separated OAuth scopes to request. |
| `CELLAR_OIDC_BUTTON_LABEL` | `Continue with SSO` | Text on the login page's SSO button. |
| `CELLAR_BASE_URL`   | *(none)*          | This app's externally-reachable URL, no trailing slash. Required for OIDC's redirect URI. |
| `CELLAR_ADMIN_USERNAMES` | *(none)*     | Comma/whitespace-separated usernames to force-grant admin on every boot. Recovery lever, not the normal way to manage admins — see "Admin" above. |
| `CELLAR_SMTP_HOST` / `CELLAR_SMTP_FROM_EMAIL` | *(none)* | Both required to enable outgoing email — see "Email (SMTP)" above. |
| `CELLAR_SMTP_PORT` | `587`            | SMTP server port. |
| `CELLAR_SMTP_SECURITY` | `starttls`   | `starttls`, `ssl` (implicit TLS), or `none`. |
| `CELLAR_SMTP_USERNAME` / `CELLAR_SMTP_PASSWORD` | *(none)* | Leave blank if your relay doesn't require auth. |
| `CELLAR_SMTP_FROM_NAME` | `BeerKeeper` | Display name on outgoing mail. |
| `CELLAR_SMTP_SKIP_CERT_VERIFY` | `false` | Only for a self-signed internal relay — weakens that connection specifically. |

If `CELLAR_PASSWORD_AUTH_ENABLED=false` and OIDC isn't properly configured,
the app logs a startup warning (visible via `docker compose logs`) and the
login page shows a plain "sign-in unavailable" message rather than a broken
form.

## Backup and restore

Everything is one file: `cellar.db` inside your data directory/volume
(plus the `-wal`/`-shm` companion files SQLite uses while running). To back
up:

```bash
docker compose exec beerkeeper sh -c "sqlite3 /data/cellar.db '.backup /data/backup.db'"
docker cp $(docker compose ps -q beerkeeper):/data/backup.db ./cellar-backup.db
```

To restore, stop the container, replace the file in the volume with your
backup, and start it again. Each user can also self-serve a partial backup
any time via **Import / Export → Download CSV**.

## CSV format

Export produces (and import expects) these columns:

```
brewery, beer, style, abv, location, custom_location, quantity, size_oz,
bottle_date, best_before, batch_notes, trade_status
```

`location` is `cellar` or `fridge`; `trade_status` is `none`, `ft`, or
`iso`; dates are `YYYY-MM-DD`. `size_oz` is always in fluid ounces
regardless of your account's unit display setting — that setting only
affects what you see and type in the app, not the interchange format.
Importing reuses an existing beer/brewery by name if one matches, otherwise
creates it.

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
  override block. An inline script in `index.html`'s `<head>` resolves and
  applies the theme before first paint to avoid a flash of the wrong theme.
- **Beer styles**: seeded once into `beer_styles.txt` in the data
  directory from `app/beer_styles_default.txt`; served at `/api/beer-styles`
  and used to power the Style field's suggestions.

## License

MIT — do whatever you'd like with it.
