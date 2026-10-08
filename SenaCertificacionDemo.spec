from pathlib import Path

from PyInstaller.building.build_main import Analysis, EXE, PYZ, COLLECT


ROOT = Path(SPECPATH).resolve()

a = Analysis(
    [str(ROOT / "demo.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "app" / "static" / "*"), "app/static")],
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
