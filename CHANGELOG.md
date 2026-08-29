# Changelog

- **0.0.16** — SMTP settings now have an actual place to type them in: a
  new "Email (SMTP)" panel on the admin page, with a "send test email"
  button for immediate feedback. This was a real gap in 0.0.15 - SMTP was
  entirely environment-variable-only, with the admin page only ever
  showing read-only status, never anywhere to enter host/port/credentials.
  The `CELLAR_SMTP_*` env vars from 0.0.15 still work exactly as before
  and now act as the fallback default for any field left blank in the
  admin panel, so nothing already deployed breaks. Caught and fixed one
  real bug of my own while building this: the password field can never
  show its stored value back (same as any password field anywhere), so a
  first draft would have silently wiped a saved password every time you
  saved an unrelated setting without retyping it - confirmed fixed by
  testing that exact sequence through the actual UI.

- **0.0.15** — Added SMTP support (`smtplib` from the standard library —
  no new dependency), with STARTTLS, implicit SSL, or no encryption, and
  optional auth. Two things it powers: a proper self-service "forgot
  password" flow (previously the only option was an admin resetting it
  for you), and welcome emails on new accounts — sent for self-registration
  and OIDC's first-ever login automatically, and optionally for
  admin-created users via a checkbox. Reset tokens are single-use, expire
  in an hour, and only a hash of the token is ever stored - the raw token
  exists only in the emailed link, the same way a password itself is
  never stored in plain text. Tested against a real local STARTTLS server
  (not just mocked): actual message delivery, the full reset cycle with a
  genuine extracted token (old password stops working, new one works,
  the token can't be reused), and a broken/unreachable mail server
  confirmed to degrade gracefully rather than break signup or login.

- **0.0.14** — Moved this changelog out of README.md into its own file
  (this one). No functional changes.
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
