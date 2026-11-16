from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path


if getattr(sys, "frozen", False):
    os.chdir(Path(sys.executable).resolve().parent)
    (Path.cwd() / "data").mkdir(parents=True, exist_ok=True)
    try:
        from app.runtime import data_dir

        _log_file = open(data_dir() / "sena_certificacion.log", "a", encoding="utf-8")
        if sys.stdout is None:
            sys.stdout = _log_file
        if sys.stderr is None:
            sys.stderr = _log_file
    except Exception:
        pass

from app.main import app
import uvicorn


def available_port(preferred_port: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", preferred_port))
        except OSError:
            probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def server_is_ready(port: int, timeout: float = 10.0) -> bool:
    """Espera a que el servidor local acepte conexiones."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


class DesktopNotificationBridge:
    """Puente JS -> Python para notificaciones nativas y foco de ventana.

    ``notify_conflict`` se invoca desde el frontend cuando el polling detecta
    ``conflict_pending``. La marca ``notified_at`` del backend garantiza una
    sola notificación por conjunto de documentos, incluso si la ventana se
    recarga. En Windows se usa ``windows-toasts`` porque permite manejar el
    clic del toast; si no está disponible se cae a ``plyer``.
    """

    def __init__(self, url: str) -> None:
        self.url = url
        self.window = None
        self._notified_fingerprints: set[str] = set()
        self._lock = threading.Lock()
        self._toaster = None

    def attach(self, window) -> None:
        self.window = window

    def _focus_window(self) -> None:
        window = self.window
        if window is None:
            return
        try:
            window.show()
        except Exception:
            pass
        try:
            window.restore()
        except Exception:
            pass
        try:
            window.on_top = True
            time.sleep(0.15)
            window.on_top = False
        except Exception:
            pass

    def _open_resolution_js(self) -> bool:
        window = self.window
        if window is None:
            return False
        script = (
            "window.SenaConflictBanner && "
            "window.SenaConflictBanner.openResolution && "
            "window.SenaConflictBanner.openResolution();"
        )
        try:
            window.evaluate_js(script)
            return True
        except Exception:
            return False

    def focus_app(self) -> bool:
        self._focus_window()
        return True

    def open_conflict_resolution(self, fingerprint: str | None = None) -> bool:
        """Enfoca la ventana y abre directamente el modal de resolución."""
        self._focus_window()
        return self._open_resolution_js()

    def _notify_windows_toast(self, title: str, body: str, fingerprint: str) -> bool:
        try:
            from windows_toasts import InteractableWindowsToaster, Toast
        except Exception:
            return False
        try:
            if self._toaster is None:
                # InteractableWindowsToaster permite capturar el clic del
                # cuerpo del toast sin depender de botones de accion.
                self._toaster = InteractableWindowsToaster("SENA Certificacion")
            toast = Toast(text_fields=[title, body])
            try:
                toast.on_activated = lambda _args: self.open_conflict_resolution(
                    fingerprint
                )
            except Exception:
                # Algunas versiones no exponen el callback de activacion; el
                # toast sigue siendo util aunque el clic no abra el modal.
                pass
            self._toaster.show_toast(toast)
            return True
        except Exception:
            return False

    def _notify_plyer(self, title: str, body: str) -> bool:
        try:
            from plyer import notification
        except Exception:
            return False
        try:
            notification.notify(
                title=title,
                message=body,
                app_name="SENA Certificacion",
                timeout=12,
            )
            return True
        except Exception:
            return False

    def notify_conflict(
        self,
        count: int = 0,
        fingerprint: str = "",
        title: str = "",
        body: str = "",
    ) -> dict:
        """Muestra el toast nativo una sola vez por huella de conflictos."""
        fingerprint = str(fingerprint or "")
        count = int(count or 0)
        title = title or "Conflicto de certificación detectado"
        if not body:
            noun = "aprendiz" if count == 1 else "aprendices"
            verb = "aparece" if count == 1 else "aparecen"
            body = (
                f"{count} {noun} {verb} en CERTIFICADOS y PENDIENTES. "
                "Debe definir el estado final en la aplicación."
            )
        with self._lock:
            if fingerprint and fingerprint in self._notified_fingerprints:
                return {"delivered": True, "method": "deduped", "fingerprint": fingerprint}

            delivered = self._notify_windows_toast(title, body, fingerprint)
            method = "windows-toasts" if delivered else None
            if not delivered:
                delivered = self._notify_plyer(title, body)
                method = "plyer" if delivered else None
            if delivered and fingerprint:
                self._notified_fingerprints.add(fingerprint)
            return {
                "delivered": bool(delivered),
                "method": method,
                "fingerprint": fingerprint,
            }


def run_desktop_window(url: str) -> None:
    """Abre la aplicación en una ventana nativa de escritorio."""
    try:
        import webview
    except ImportError:
        if os.getenv("SENA_USE_BROWSER") == "1":
            import webbrowser

            webbrowser.open(url)
            return
        raise RuntimeError(
            "Falta pywebview. Reinstale la aplicación o defina "
            "SENA_USE_BROWSER=1 para usar el navegador externo."
        )

    bridge = DesktopNotificationBridge(url)
    window = webview.create_window(
        "SENA Certificación",
        url,
        width=1440,
        height=900,
        min_size=(1024, 700),
        confirm_close=False,
        js_api=bridge,
    )
    bridge.attach(window)
    webview.start()


if __name__ == "__main__":
    from app.version import APP_NAME, APP_VERSION

    smoke_test = "--smoke-test" in sys.argv or os.getenv("SENA_SMOKE_TEST") == "1"
    port = available_port(int(os.getenv("PORT", "8000")))
    url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info")
    )
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    try:
        if not server_is_ready(port, timeout=30.0):
            raise RuntimeError(f"El servidor local no respondió en {url}")
        if smoke_test:
            import urllib.request

            print(f"{APP_NAME} {APP_VERSION} - prueba de arranque")
            for path in ("/", "/api/version", "/api/learners"):
                with urllib.request.urlopen(f"{url}{path}", timeout=10) as response:
                    print(f"  {path} -> HTTP {response.status}")
            print("SMOKE_OK")
        else:
            run_desktop_window(url)
    except Exception as error:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        print(f"No fue posible iniciar la aplicación en {url}:\n{error}")
        if getattr(sys, "frozen", False) or smoke_test is False:
            try:
                input("Presiona Enter para cerrar...")
            except EOFError:
                pass
    finally:
        server.should_exit = True
        server_thread.join(timeout=5)
        if smoke_test:
            sys.exit(0)
