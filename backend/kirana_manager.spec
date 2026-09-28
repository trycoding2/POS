# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Kirana Manager single-file Windows EXE.
# Built by build_windows.bat (do not run directly).

from pathlib import Path

dist_dir = Path(SPECPATH) / "dist" / "frontend"
if not dist_dir.exists():
    raise SystemExit("ERROR: built frontend missing at backend/dist/frontend. Run build_windows.bat first.")

a = Analysis(
    ['run_server.py'],
    pathex=[],
    binaries=[],
    datas=[(str(dist_dir), 'dist')],
    hiddenimports=[
        'uvicorn.logging', 'uvicorn.loops.auto', 'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan.on',
        'sqlalchemy.sql.default_comparator',
        'app.routers.auth', 'app.routers.catalog', 'app.routers.pos',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', '_pytest', 'tkinter'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='KiranaManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # keep console so shop staff can see server status/errors
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
