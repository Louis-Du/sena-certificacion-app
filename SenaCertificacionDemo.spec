from pathlib import Path

from PyInstaller.building.build_main import Analysis, EXE, PYZ, COLLECT


ROOT = Path(SPECPATH).resolve()
STATIC_DIR = ROOT / "app" / "static"
TEMPLATES_DIR = ROOT / "app" / "templates"
ICON_FILE = ROOT / "assets" / "SENACertificacion.ico"

# Falla la compilación si falta la carpeta, en lugar de generar un .exe roto.
if not STATIC_DIR.is_dir():
    raise SystemExit(f"No existe la carpeta de estáticos: {STATIC_DIR}")
if not TEMPLATES_DIR.is_dir():
    raise SystemExit(f"No existe la carpeta de plantillas: {TEMPLATES_DIR}")

datas = [(str(STATIC_DIR), "app/static"), (str(TEMPLATES_DIR), "app/templates")]
if ICON_FILE.is_file():
    datas.append((str(ICON_FILE), "."))

a = Analysis(
    [str(ROOT / "demo.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.lifespan.on",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "webview",
        "webview.platforms.winforms",
        "webview.platforms.edgechromium",
        "webview.platforms.win32",
        "webview.platforms.mshtml",
        "pystray",
        "clr",
        "clr_loader",
        "pythonnet",
        "plyer",
        "plyer.platforms.win.notification",
        "plyer.platforms.win.libs.balloontip",
        "windows_toasts",
        "winrt",
        "winrt.system",
        "winrt.windows.ui.notifications",
        "winrt.windows.data.xml.dom",
        "winrt.windows.foundation",
        "winrt.windows.foundation.collections",
        "xlrd",
        "fitz",
        "pymupdf",
    ],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="SENACertificacion",
    console=False,
    icon=str(ICON_FILE) if ICON_FILE.is_file() else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="SENACertificacion")