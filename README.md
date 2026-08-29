# BeerKeeper

**Current version: 0.0.13**

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

## Changelog

- **0.0.13** — Added an admin page (`#/admin`, linked from the nav for
  admins only): reset anyone's password, create accounts directly,
  promote/demote admins, delete users (cascades their whole cellar and
  history), and a toggle to turn off new registrations while existing
  logins — password and OIDC alike — keep working. The `is_admin` column
  existed on the User model from the very first version of this app but
  was never actually wired up anywhere until now. The first person to
  ever register or log in becomes admin automatically, no setup required;
  an existing deployment upgrading to this version promotes whoever
  registered earliest. You can't delete or demote the last remaining
  admin, and you can't delete your own account from this page. A
  `CELLAR_ADMIN_USERNAMES` env var exists as a recovery lever if a
  deployment ever somehow ends up with zero admins.

- **0.0.12** — Anywhere the app shows your OIDC display name, it now
  shows just your first name ("David" instead of "David Lundin") — nav,
  account page, browse list, activity feed, and public cellar/trade
  headers. The account page's subtitle still shows your full username
  for reference. No backend or database change: the full name is still
  stored as before, this only changes how it's rendered.

- **0.0.11** — More OIDC display-name work, this time prompted by a report
  from an actual Pocket ID token payload rather than a guess. Two things
  changed: fixed a real bug in 0.0.10's own fix, where merging the ID
  token's claims with a separate `/userinfo` call let the `/userinfo`
  response unconditionally overwrite the ID token's data, including with
  a missing/blank value if that endpoint returned a sparser claim set
  than the token itself — now whichever source actually has a non-empty
  value wins. Second, and probably more relevant if you're on this: the
  sync only ever happens *during* an OIDC login, not on every page load —
  if your browser still holds a session from before display names worked
  (or from before you'd have had one at all), just having the app open
  won't pick up the fix; **log out and log back in via SSO** to trigger a
  fresh sync. Also added a diagnostic log line (`docker compose logs`
  after a login attempt) printing which claim keys your provider actually
  sent and what got resolved, so a future report doesn't have to be
  guessed at from a copy-pasted token again. I could not reproduce the
  original report even with a token built to match Pocket ID's exact
  shape (array-valued `aud`, all its extra claims), so if display name
  still doesn't show after re-logging-in, that log line is the next
  place to look.

- **0.0.10** — Two OIDC display-name fixes. First: the app only called
  your provider's separate `/userinfo` endpoint when the ID token had
  *nothing at all*; providers that put a minimal claim set (e.g. just
  `sub`) in the ID token and serve the rest — including your display
  name — from `/userinfo` instead were silently missed, since a
  minimal-but-non-empty ID token still skipped that call. Now both are
  always checked and merged. Also added a fallback to `given_name` +
  `family_name` for providers that don't send a combined `name` claim.
  Second, found while chasing the first one: accounts created via a
  provider that doesn't release an email address got a placeholder
  address ending in `.invalid`, which is syntactically correct but is on
  the reserved-domain list our email validator rejects outright — meaning
  every request describing that account (starting with `/api/auth/me`
  right after login) failed with a 500, which would have looked like
  being logged right back out. Fixed the placeholder domain, and added a
  migration that repairs any account already stuck with the broken one.
  I couldn't reproduce your exact setup, so if display name still doesn't
  show after upgrading, it means your provider isn't sending `name` (or
  given/family name) at all — worth checking your provider's scope/claim
  configuration for the `profile` scope.

- **0.0.9** — The "Recently uncorked" home feed now always includes your
  own activity when you're logged in, even if your cellar is set to
  private. Everyone else's view of the feed is unaffected: your entries
  only ever appear when you yourself are viewing it, never for other
  people or anonymous visitors — confirmed with tests covering an
  anonymous visitor, the private-cellar owner, a different logged-in
  user, and a stale/invalid auth token, to make sure the personalization
  never leaks beyond the one person it's for.
- **0.0.8** — Fixed a real bug: entering a perfectly valid date (e.g. when
  drinking a bottle) could be rejected as invalid, depending on your
  timezone. The date validation converted your local date to UTC and
  compared the strings; for anyone in a timezone ahead of UTC (all of
  Scandinavia included), local midnight rolls back to the previous day in
  UTC, so the comparison failed for a perfectly good date. Fixed by
  validating entirely in local time instead - no UTC conversion at all.
  Also fixed a related, quieter version of the same bug: the "Date" field
  on the Drink form pre-filled using the same broken approach, so for
  roughly the first couple of hours after local midnight (until UTC also
  rolled over) it would silently default to yesterday's date instead of
  today's. Confirmed both fixes against the reported timezone directly,
  including the exact overnight window where the old code broke.
- **0.0.7** — Sort your cellar (and the public cellar page) by drink-by
  date, in addition to beer/brewery — soonest-expiring first, bottles
  with no date set pushed to the end. The account setting for default
  sort is now a proper three-way listbox instead of a beer/brewery toggle
  switch. If you sign in via OIDC and your provider sends a `name` claim,
  the app now shows that everywhere instead of your (often auto-generated)
  username — nav, account page, browse list, activity feed, and public
  cellar/trade page headers all prefer it, while URLs and account
  identity continue to use the real username underneath. Kept in sync on
  every login in case your name changes upstream; password-only accounts
  are unaffected.
- **0.0.6** — Added a public, no-login trade/wanted list per account:
  a "+ Add to wanted list" flow for tracking beers you don't own yet
  (they show up separately from your inventory, never counted in your
  cellar total), and a shareable `#/u/<username>/trades` page listing
  just your For Trade and Wanted bottles. Gated only by the existing
  "Enable trading labels" account toggle, deliberately independent of
  whether your full cellar is public — you can keep your whole
  collection private and still share just a trade list. Get the
  shareable link from Account once trading is enabled.
- **0.0.5** — Substantially expanded the US (24 → 53) and Belgian (7 → 29)
  brewery lists, including all six official Belgian Trappist breweries
  (Achel, Chimay, Orval, Rochefort, Westmalle, Westvleteren). Also fixed
  how seeding tracks what's already been added: previously it was a single
  all-or-nothing flag, so an update like this one that adds *more*
  breweries to the default list would never have reached an existing
  install. Now each brewery is tracked individually, so future additions
  to the list reach upgraded installs too, while anything you've
  deliberately deleted stays deleted. One-time caveat for anyone upgrading
  directly from 0.0.4: a brewery you deleted before upgrading may reappear
  once, since the old version didn't keep that history — anything deleted
  from 0.0.5 onward won't have that problem.
- **0.0.4** — Pre-populated the breweries list with ~80 real breweries (29
  Swedish craft breweries plus major names from the US, UK, Belgium,
  Germany, the Netherlands, Denmark, Norway, and Estonia) so brewery
  autocomplete has something useful to suggest from day one, not just
  what you've personally added. Seeded once into the database on first
  boot; managed through the app from then on. See "Pre-populated
  breweries" below.
- **0.0.3** — Brought back a calendar picker for date fields. Rather than
  the native `<input type="date">` (which is what caused the original
  locale-formatting problem), it's a small custom popup calendar that
  writes into the same guaranteed-ISO text field, opened via a calendar
  icon next to each date input.
- **0.0.2** — Fixed stale browser caching after upgrades: asset URLs
  (`pages.js`, `style.css`, etc.) now carry a `?v=<version>` query string
  injected from the current app version, so bumping the version forces
  browsers to fetch fresh files instead of continuing to serve an old
  cached copy post-upgrade. (This was the actual cause behind dates still
  showing as `mm/dd/yyyy` after upgrading to 0.0.1 — the fix was already
  correct in the code, the browser just hadn't fetched it yet.)
- **0.0.1** — Initial versioned release: OIDC/SSO support, optional
  password-auth disable, personalized beer/brewery autocomplete, editable
  beer-styles config file, dark/light/system theming, metric/imperial
  units, ISO date formatting throughout, renamed to BeerKeeper.

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
