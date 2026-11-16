import base64
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
    assert "def notify_update" in source
    assert "def open_conflict_resolution" in source
    assert "def save_file" in source
    assert "def open_external" in source
    assert "def start_update_monitor" in source
    assert "def stop_update_monitor" in source
    assert "js_api=bridge" in source
    assert "SenaConflictBanner" in source
    assert "SenaUpdates" in source


def test_save_file_uses_native_dialog_and_writes_bytes(tmp_path):
    import demo

    class FakeWindow:
        def __init__(self, result):
            self.result = result
            self.calls = []

        def create_file_dialog(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return self.result

    destination = tmp_path / "informe.pdf"
    window = FakeWindow((str(destination),))
    bridge = demo.DesktopNotificationBridge("http://127.0.0.1:8000")
    bridge.window = window

    result = bridge.save_file(
        "informe.pdf",
        base64.b64encode(b"%PDF-1.4 contenido").decode("ascii"),
    )

    assert result["saved"] is True
    assert destination.read_bytes() == b"%PDF-1.4 contenido"
    assert window.calls
    assert window.calls[0][1]["save_filename"] == "informe.pdf"


def test_save_file_reports_cancellation(tmp_path):
    import demo

    class FakeWindow:
        def create_file_dialog(self, *args, **kwargs):
            return None

    bridge = demo.DesktopNotificationBridge("http://127.0.0.1:8000")
    bridge.window = FakeWindow()

    result = bridge.save_file("informe.xlsx", base64.b64encode(b"data").decode("ascii"))

    assert result == {"saved": False, "cancelled": True}


def test_save_file_accepts_a_string_dialog_result(tmp_path):
    import demo

    destination = tmp_path / "informe.csv"

    class FakeWindow:
        def create_file_dialog(self, *args, **kwargs):
            return str(destination)

    bridge = demo.DesktopNotificationBridge("http://127.0.0.1:8000")
    bridge.window = FakeWindow()

    result = bridge.save_file("informe.csv", base64.b64encode(b"a,b").decode("ascii"))

    assert result["saved"] is True
    assert destination.read_bytes() == b"a,b"


def test_save_file_rejects_invalid_base64():
    import demo

    class FakeWindow:
        def create_file_dialog(self, *args, **kwargs):
            raise AssertionError("no debe abrir el diálogo con contenido inválido")

    bridge = demo.DesktopNotificationBridge("http://127.0.0.1:8000")
    bridge.window = FakeWindow()

    result = bridge.save_file("informe.pdf", "no-es-base64!!")

    assert result["saved"] is False
    assert result["error"] == "invalid-content"


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
