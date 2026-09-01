# Changelog

- **0.0.49** — Two real breweries sharing an exact name across different countries (e.g. "Akasha Brewing Company" in both the US and Australia) now get a country appended to keep them distinct, instead of the second one silently failing to seed. Affects 8 name collisions found in the pre-populated brewery list. README cleanup: reordered and trimmed the features list, shortened the "Pre-populated breweries" and OIDC sections, removed a stale admin bullet. docker-compose.yml: trimmed a comment block (the two `volumes:` sections aren't redundant - one mounts the volume into the container, the other declares it exists - so both stay).

- **0.0.48** — Merged 79 more of the near-duplicate groups found within Open Brewery DB itself (e.g. "Big Storm Brewing" → "Big Storm Brewing Co."), reviewed individually and choosing the more complete name; 5 groups that looked like they could be genuinely different physical locations (e.g. a separate "...Brewpub" listing) were deliberately left alone. While applying this, caught and fixed a mistake in the same pass - two entries ("Batch Brewing Co" and "New England Brewing Co") were wrongly removed because the same exact name legitimately belongs to two unrelated breweries in different countries; both are restored.

- **0.0.47** — Removed 34 breweries from the hand-picked starting list that duplicated an Open Brewery DB entry under slightly different punctuation (e.g. "Founders Brewing Co." vs. "Founders Brewing Co") - reviewed each pair individually before removing, keeping the Open Brewery DB version in every case. Near-duplicates within Open Brewery DB itself weren't touched, since there's no reliable way to tell those apart from two genuinely different breweries with similar names.

- **0.0.46** — Brewery list grew from ~215 to 10,562 via a bulk import from Open Brewery DB (US + 20 other countries, excluding closed/planning/bars/taprooms/beer gardens). Fixed a real bug this surfaced: the beer/brewery search's 500-result cap could exclude a just-used entry from its own results once the catalog grew large enough, since the cap ran before the recency-based sort - a user's own recently-used items are now always included regardless of where they'd otherwise rank. The Beer/Brewery fields on "Add a bottle" and both admin search panels no longer show suggestions just from clicking in - typing is required, as before the previous autopopulate change.

- **0.0.45** — Cellar CSV export now always includes both `size_oz` and `size_ml`; import reads whichever matches your unit setting, falling back to the other if it's blank. On narrow screens (phones), the top nav collapses into a hamburger menu instead of causing the whole page to scroll sideways.

- **0.0.44** — Moved cellar CSV import/export from its own page into Account → Cellar data (the old link still works, redirecting there). Moved History from a cellar-page toolbar link into the top nav, right after "My cellar" and before Admin. Fixed a leftover "best-before" label on the account page's privacy settings that should have said "drink-by."

- **0.0.43** — Beer names with an external link no longer underline on hover on the cellar page.

- **0.0.42** — Added a "Beers" panel to the admin page, mirroring the Breweries one: add, rename, reassign to a different brewery, edit style/ABV/external link, delete (blocked while in use by any cellar entry, history log, or wanted item), plus CSV import/export. The "Edit bottle" form's beer/brewery/style/ABV/link fields were already locked (they're shared data, not per-entry) but gave no explanation why - there's now a note, and admins get a one-click shortcut straight into editing that beer.

- **0.0.41** — Added an optional "External link" field for beers (Untappd, RateBeer, a brewery's own page, etc.) — the beer name becomes clickable wherever it's shown (cellar cards, both view modes, history, trade/wanted lists) when a link is set, and stays plain text when it isn't. URLs are validated to only accept http(s) links, a check now also applied retroactively to brewery websites, which had the same gap.

- **0.0.40** — docker-compose.yml now sets `container_name: BeerKeeper`, so `docker ps`/`docker logs` show a friendly name instead of an auto-generated one. Note: this means only one instance can run under this container name at a time on a given Docker host — remove or rename it if you need to run multiple.

- **0.0.39** — "Best before" is now "Drink by" everywhere it's shown, not just the add/edit form — cellar cards, both private and public views.

- **0.0.38** — Renamed the "Best before / drink by" field label to just "Drink by" on the add/edit bottle form.

- **0.0.37** — Bottles due to drink within 30 days (or already overdue) now show a "!" next to the beer name, styled to match the "Keeper" half of the logo. Shows in both comfortable and compact cellar views.

- **0.0.36** — The account page now shows your full display name ("Signed in as Jane Middlename Doe") instead of just the first name. The nav's greeting elsewhere is unchanged, still first-name-only.

- **0.0.35** — The "Users" section on the admin page is now a panel card like the rest of the page (Settings, Email, Breweries, Backup), instead of having its heading sit outside the block that holds the actual user list.

- **0.0.34** — The profile chip no longer underlines on hover. The BeerKeeper logo is now a link back to Home.

- **0.0.33** — OIDC accounts now show their provider's profile picture in the nav (kept in sync on every login, same as display name), with a fallback initials badge for password-only accounts. Removed the separate "Account" nav button — the avatar and name are now the link to the account page. Required loosening the CSP's `img-src` to allow external images, since avatars are hosted by the identity provider, not this app.

- **0.0.32** — The Brewery and Beer fields on "Add a bottle", and the admin Breweries panel's search, now show suggestions immediately on focus instead of waiting for you to type, matching how the Style field already worked. Fixed a bug this surfaced: a brewery or beer you'd just used could fail to appear in your own empty-search results at all, if 50+ others came before it alphabetically.

- **0.0.31** — Added a "Breweries" panel to the admin page: add, rename, and delete breweries in the shared list (deletion blocked while any beer still references one), plus CSV import/export for the whole list. This is what the README's "managed like any other brewery" line was supposed to mean — there was previously no way to actually do it.

- **0.0.30** — The cellar page now shows a running total ("N beers · N on hand") next to the title, reflecting whatever filter is active. Added ~19 major cider makers and meaderies to the pre-populated brewery list (Strongbow, Thatchers, Angry Orchard, B. Nektar, Schramm's, and more) — existing installs pick these up automatically on next boot, same as any brewery-list update.

- **0.0.29** — Cellar sort buttons now toggle ascending/descending on click, with an arrow showing the current direction. History entries are now editable (rating, note, quantity, date), not just deletable. Removed the background glow on all pages. Removed two unnecessary 0-byte `__init__.py` files.

- **0.0.28** — Added ~65 pre-populated breweries covering the UK, Ireland, Germany, Austria, Czechia, Poland, and (new) Latvia and Lithuania, plus more for Estonia — 190+ total. Existing installs pick these up automatically on next boot too, same as any brewery-list update, since seeding tracks individual breweries rather than all-or-nothing.

- **0.0.27** — README fixes: "Backup and restore" now describes the actual zip format (database + beer styles), and `CELLAR_SECRET_KEY`'s documented default no longer references the old hardcoded insecure key, reflecting 0.0.26's auto-generated-and-persisted behavior. No functional changes.

- **0.0.26** — Security hardening pass (see SECURITY.md): random+persisted secret key instead of a hardcoded fallback; rate limiting on login/register/forgot-password; a leaked token stops working immediately on password change/reset instead of waiting out its 30-day expiry; OIDC no longer auto-links an account on an unverified email; changing your account email now requires your password; upload size limits on CSV import and backup restore; CSP + security headers (required removing the app's one inline script and one inline event handler).

- **0.0.25** — Admin backups are now a zip containing both the database and `beer_styles.txt` (which lives outside the database, so 0.0.24's database-only backup silently dropped any custom styles). Old single-file `.db` backups from 0.0.24 are no longer accepted for restore — re-download a fresh backup.

- **0.0.24** — New accounts now default to metric units instead of imperial (existing accounts unaffected). Added whole-instance backup/restore to the admin page: download the entire database as a single file, and restore it on any install (validated on upload, staged to apply on the next restart rather than live, to avoid corrupting an active database).

- **0.0.23** — Condensed README.md substantially: trimmed the features list, cut the outdated "known limitations" section, removed repeated originality disclaimers, and shortened the pre-populated-breweries and email sections to the essentials. No functional changes.

- **0.0.22** — The admin panel's "send test email" field now prepopulates with your own account email, still editable if you want to send it elsewhere.

- **0.0.21** — Added a Comfortable/Compact view toggle for the cellar list (~57% shorter cards on desktop, ~39% on mobile) — comfortable stays the default, your choice is remembered locally between sessions.

- **0.0.20** — Imperial-account size suggestions are now genuine US customary sizes (8/12/16/19.2/22/32/64 oz — bottle, pint, stovepipe, bomber, crowler, growler) instead of the metric list converted to odd numbers like 11.2 or 25.4 oz.

- **0.0.19** — The bottle size field now suggests common sizes (250/330/375/440/500/750/1500 mL, or the oz equivalent for imperial accounts) plus sizes you've personally used before, most-used first.

- **0.0.18** — Condensed this changelog: each entry is now a line or two instead of a paragraph.
- **0.0.17** — Added a favicon (amber pint glass, matches the app's colors) as SVG/PNG/ICO + Apple touch icon, plus a dedicated `/favicon.ico` route.
- **0.0.16** — Added an "Email (SMTP)" panel on the admin page to configure SMTP through the UI, with a send-test-email button. Env vars from 0.0.15 still work as fallback defaults.
- **0.0.15** — Added SMTP support (stdlib `smtplib`; STARTTLS/SSL/none): self-service "forgot password" and welcome emails on new accounts.
- **0.0.14** — Moved the changelog out of README.md into this file.
- **0.0.13** — Added an admin page: reset passwords, create/delete/promote users, toggle new registrations on/off. First user (or first OIDC login) becomes admin automatically.
- **0.0.12** — OIDC display name now shows first name only ("David" instead of "David Lundin").
- **0.0.11** — Fixed a bug where merging OIDC userinfo-endpoint data could overwrite the ID token's display name with a blank; added diagnostic logging for future claim issues. Display name only re-syncs on login, not on page load — log out/in if it's stale.
- **0.0.10** — Fixed OIDC display names for providers that split claims across the ID token and userinfo endpoint (e.g. Pocket ID), with a given/family-name fallback; fixed a crash for accounts with no email address.
- **0.0.9** — The "Recently uncorked" feed now always includes your own activity, even with a private cellar — visible only to you, never to others.
- **0.0.8** — Fixed a timezone bug that could reject valid dates (e.g. for Scandinavia) as invalid, plus a related "today" pre-fill bug on the Drink form.
- **0.0.7** — Added drink-by-date sorting (cellar + public page) with a 3-way sort listbox in settings, and OIDC display names shown throughout the app.
- **0.0.6** — Added a public, no-login trade/wanted list per account, with a shareable link independent of overall cellar privacy.
- **0.0.5** — Expanded US/Belgian brewery lists; fixed seeding so future list updates reach existing installs.
- **0.0.4** — Pre-populated ~80 real breweries for autocomplete.
- **0.0.3** — Added a custom calendar picker for date fields.
- **0.0.2** — Fixed stale browser caching after upgrades via versioned asset URLs.
- **0.0.1** — Initial versioned release: OIDC/SSO, autocomplete, theming, units, ISO dates, renamed to BeerKeeper.
