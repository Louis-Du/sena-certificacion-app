from pathlib import Path

from PyInstaller.building.build_main import Analysis, EXE, PYZ, COLLECT


ROOT = Path(SPECPATH).resolve()
STATIC_DIR = ROOT / "app" / "static"

# Falla la compilación si falta la carpeta, en lugar de generar un .exe roto.
if not STATIC_DIR.is_dir():
    raise SystemExit(f"No existe la carpeta de estáticos: {STATIC_DIR}")

a = Analysis(
    [str(ROOT / "demo.py")],
    pathex=[str(ROOT)],
    datas=[(str(STATIC_DIR), "app/static")],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
    ],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="SenaCertificacionDemo",
    console=True,
)
coll = COLLECT(exe, a.binaries, a.datas, name="SenaCertificacionDemo")