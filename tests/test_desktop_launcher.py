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


def test_desktop_launcher_exposes_notification_bridge():
    source = LAUNCHER.read_text(encoding="utf-8")

    assert "class DesktopNotificationBridge" in source
    assert "def notify_conflict" in source
    assert "def open_conflict_resolution" in source
    assert "js_api=bridge" in source
    assert "SenaConflictBanner" in source


def test_notification_bridge_dedupes_by_fingerprint(monkeypatch):
    import demo

    bridge = demo.DesktopNotificationBridge("http://127.0.0.1:8000")
    delivered: list[str] = []

    monkeypatch.setattr(bridge, "_notify_windows_toast", lambda *_args: False)
    monkeypatch.setattr(
        bridge,
        "_notify_plyer",
        lambda title, body: delivered.append(title) or True,
    )

    first = bridge.notify_conflict(2, "fingerprint-1", "", "")
    second = bridge.notify_conflict(2, "fingerprint-1", "", "")
    third = bridge.notify_conflict(3, "fingerprint-2", "", "")

    assert first == {
        "delivered": True,
        "method": "plyer",
        "fingerprint": "fingerprint-1",
    }
    assert second["method"] == "deduped"
    assert third["method"] == "plyer"
    assert len(delivered) == 2


def test_notification_dependencies_declared_for_desktop_build():
    root = LAUNCHER.parent
    requirements = (root / "requirements.txt").read_text(encoding="utf-8")
    spec = (root / "SenaCertificacionDemo.spec").read_text(encoding="utf-8")

    assert "plyer" in requirements
    assert "windows-toasts" in requirements
    assert '"plyer.platforms.win.notification"' in spec
    assert '"windows_toasts"' in spec
