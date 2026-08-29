# Changelog

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
