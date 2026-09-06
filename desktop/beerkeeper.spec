# PyInstaller spec for the BeerKeeper desktop app.
#
# Build (on Windows, from the repo root, with both requirements files
# installed - see desktop/README.md):
#   pyinstaller desktop/beerkeeper.spec
#
# Output lands in dist/BeerKeeper/ (onedir - see note below).

import sys
from pathlib import Path

block_cipher = None

REPO_ROOT = Path(SPECPATH).parent  # desktop/ -> repo root

a = Analysis(
    [str(REPO_ROOT / "desktop" / "launcher.py")],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=[
        (str(REPO_ROOT / "static"), "static"),
        (str(REPO_ROOT / "app" / "beer_styles_default.txt"), "app"),
        (str(REPO_ROOT / "app" / "breweries_default.txt"), "app"),
    ],
    hiddenimports=[
        # FastAPI/Starlette/uvicorn pull some of these in dynamically
        # (via import strings or optional-extra detection) in a way
        # PyInstaller's static analysis doesn't always catch.
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "email_validator",
        "authlib.integrations.starlette_client",
        "webview.platforms.winforms",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BeerKeeper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # no console window behind the app
    icon=str(REPO_ROOT / "static" / "icons" / "favicon.ico"),
)

# onedir, not onefile: a onefile build re-extracts everything to a fresh
# temp directory on every single launch, which is a slow, flash-of-nothing
# start for an app people will open repeatedly. onedir starts instantly
# after the first run and is just as easy to distribute as a zip.
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="BeerKeeper",
)
