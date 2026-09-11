# BeerKeeper desktop (Windows build)

This turns the self-hosted app into a single-user, no-login, no-Docker
desktop app: one process, one window, your cellar only. It's the exact
same backend code as the self-hosted app (`app/`) running in
`CELLAR_SINGLE_USER_MODE` - see the code comments in `app/config.py`,
`app/deps.py`, and `app/admin_bootstrap.py` for what that actually
changes. Nothing in `app/` behaves differently for the normal self-hosted
deployment unless that flag is explicitly set.

## What you need

- Windows 10 (2004+) or Windows 11. Both ship the WebView2 runtime
  Microsoft's Edge browser uses, which is what actually renders the app's
  UI - no separate download needed on a normal, up-to-date Windows
  install. If you're on an older Windows 10 build, install it manually
  first: https://developer.microsoft.com/microsoft-edge/webview2/
- Python 3.12 (the version this was built and tested against). Get it
  from https://python.org - tick "Add python.exe to PATH" during install.

This has to be built **on Windows** - PyInstaller packages for the OS
it's running on, it doesn't cross-compile. Building it on Linux or macOS
would produce a Linux or macOS binary, not a Windows one.

## Build steps

Open a Command Prompt or PowerShell in the repo root (the folder with
`app/`, `static/`, `requirements.txt` in it) and run:

```powershell
python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt
pip install -r desktop\requirements-desktop.txt

pyinstaller desktop\beerkeeper.spec
```

That last step takes a few minutes the first time. When it's done, the
whole app is in `dist\BeerKeeper\` - an onedir build (a folder, not one
giant .exe) so it starts up fast on every launch rather than
re-extracting itself each time. `dist\BeerKeeper\BeerKeeper.exe` is what
you run.

Zip up the `dist\BeerKeeper` folder and that's the whole distributable -
copy it anywhere, no installer required for a first pass. (An actual
installer via Inno Setup, and code-signing so Windows SmartScreen doesn't
warn on first run, are natural next steps once the app itself is solid -
neither changes anything about the app itself, just how it arrives.)

## Where your data lives

`%LOCALAPPDATA%\BeerKeeper\BeerKeeper\` - typically
`C:\Users\<you>\AppData\Local\BeerKeeper\BeerKeeper\`. That's the SQLite
database (`cellar.db`), the auto-generated secret key, and nothing else.
Deleting that folder is equivalent to a fresh install.

## What to actually test once you have a built .exe

I tested everything on the Python/backend side directly (see the main
conversation for specifics - single-user mode auto-login, the stripped
routes actually 404ing, the backup password feature verified end to end).
What I *can't* test without Windows and a real display is the desktop
shell itself:

1. **It launches and shows the app** - the basic "does the window open
   and render the cellar UI" check.
2. **File downloads work** - click "Download full backup" and "Download
   CSV" on the Account/Settings pages. WebView2 should either prompt a
   Save As dialog or drop the file in your normal Downloads folder;
   either is fine, but this is the one piece of browser behavior I
   couldn't verify without a real WebView2 instance.
3. **File uploads work** - the "Restore from backup" and "Import from
   CSV" file pickers should open a normal native Windows file dialog.
4. **Closing the window actually exits the process** - check Task
   Manager after closing; there shouldn't be a leftover `BeerKeeper.exe`
   still running in the background.
5. **Reopening it later keeps your data** - close it, add a bottle,
   reopen it, confirm the bottle's still there (proves the data
   directory is being found consistently across launches, not
   regenerated).
6. **Drink-by reminders** - check what the Account page shows under
   "Drink-by reminders". The email option is hidden in single-user mode
   (there's no SMTP panel in the desktop app to configure), so you
   should see the day-count selector and, *if* WebView2 supports the
   Push API, a push toggle. If the toggle simply isn't there, that's
   the frontend correctly detecting that push isn't available in this
   window - not a bug, and nothing else on the page should be affected.
   Worth knowing either way, since a desktop app arguably wants native
   OS notifications (pywebview can do those directly) rather than web
   push - a small follow-up if the web push route turns out to be a
   dead end here.

If (2) turns out awkward in practice (some WebView2 setups silently drop
downloads instead of prompting), the fix is a small one - add a native
Save-As dialog via pywebview's own file-dialog API and a tiny JS hook
instead of relying on the browser's default download handling. Worth
knowing about now rather than assuming it'll just work.

## About the app's size

A packaged onedir build lands somewhere in the neighborhood of 50-60MB.
That's normal for this kind of app, not a sign of something wrong -
it's a full Python interpreter plus SQLAlchemy, cryptography, and the
WebView2/.NET bridge that lets the window render, and none of those
compress much further. A few things were already trimmed out
specifically for the desktop build, since they're genuinely unused in
single-user mode: the OIDC/SSO login path (`authlib`, `httpx`, and their
own dependency chains) is no longer even imported when
`CELLAR_SINGLE_USER_MODE` is set (see the comment in `app/main.py`), and
`uvicorn`'s hot-reload/websocket extras (`uvloop`, `httptools`,
`websockets`, `watchfiles`) are excluded from the bundle in
`beerkeeper.spec` and pinned off explicitly in `launcher.py`, since this
app has no websocket routes and a packaged build never hot-reloads.

If your build comes out noticeably larger than that, the most likely
cause is unrelated packages leaking in from a Python environment that
has more than just this repo's two requirements files installed in it -
build from a clean virtualenv with only `requirements.txt` and
`desktop\requirements-desktop.txt`, nothing else, to avoid that.

## Files in this folder- `launcher.py` - the actual desktop entry point (see its own comments)
- `requirements-desktop.txt` - pywebview, platformdirs, pyinstaller
- `beerkeeper.spec` - the PyInstaller build spec
