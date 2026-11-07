import importlib.util
from pathlib import Path


LAUNCHER = Path(__file__).parents[1] / "demo.py"


def test_desktop_launcher_defines_embedded_window_entrypoint():
    source = LAUNCHER.read_text(encoding="utf-8")

    assert "def run_desktop_window" in source
    assert "webview.create_window" in source
    assert "127.0.0.1" in source


def test_pywebview_is_declared_for_desktop_build():
    requirements = (LAUNCHER.parent / "requirements.txt").read_text(encoding="utf-8")

    assert "pywebview>=" in requirements
