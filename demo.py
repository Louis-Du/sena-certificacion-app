from __future__ import annotations

import base64
import os
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Callable


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


_FILE_TYPE_LABELS = {
    ".pdf": "Documento PDF",
    ".xlsx": "Libro de Excel",
    ".docx": "Documento de Word",
    ".csv": "Archivo CSV",
}


def _file_types_for_suffix(suffix: str) -> tuple[str, ...]:
    """Filtros válidos para el diálogo nativo de Windows."""
    suffix = (suffix or "").lower()
    if suffix:
        label = _FILE_TYPE_LABELS.get(suffix, "Archivo")
        return (f"{label} (*{suffix})", "Todos los archivos (*.*)")
    return ("Todos los archivos (*.*)",)


class DesktopNotificationBridge:
    """Puente JS -> Python para notificaciones, archivos y foco de ventana.

    ``notify_conflict`` se invoca desde el frontend cuando el polling detecta
    ``conflict_pending``. La marca ``notified_at`` del backend garantiza una
    sola notificación por conjunto de documentos, incluso si la ventana se
    recarga. En Windows se usa ``windows-toasts`` porque permite manejar el
    clic del toast; si no está disponible se cae a ``plyer``.

    ``save_file`` usa el diálogo nativo de guardado. La File System Access API
    del navegador exige una activación de usuario reciente y WebView2 la pierde
    cuando la generación del informe tarda unos segundos; por eso la descarga
    terminaba en la carpeta predeterminada sin mostrar el explorador.
    """

    def __init__(self, url: str) -> None:
        self.url = url
        self.window = None
        self._notified_fingerprints: set[str] = set()
        self._notified_updates: set[str] = set()
        self._lock = threading.Lock()
        self._toaster = None
        self._update_monitor_stop = threading.Event()
        self._update_monitor_thread: threading.Thread | None = None

    def _attach(self, window) -> None:
        # pywebview recorre con dir()/getattr() todos los atributos públicos del
        # js_api para exponerlos a JavaScript. Sin esta marca se mete en el
        # objeto nativo de la ventana y en los objetos COM de WebView2, lo que
        # provoca recursion infinita ("AccessibilityObject...") y congela la UI.
        try:
            window._serializable = False
        except Exception:
            pass
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

    def _open_updates_js(self) -> bool:
        window = self.window
        if window is None:
            return False
        script = (
            "window.SenaUpdates && "
            "window.SenaUpdates.open && "
            "window.SenaUpdates.open();"
        )
        try:
            window.evaluate_js(script)
            return True
        except Exception:
            return False

    def _notify_windows_toast(
        self,
        title: str,
        body: str,
        on_click: Callable[[], None] | None = None,
    ) -> bool:
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
            if on_click is not None:
                try:
                    toast.on_activated = lambda _args: on_click()
                except Exception:
                    # Algunas versiones no exponen el callback de activacion; el
                    # toast sigue siendo util aunque el clic no abra el modal.
                    pass
            self._toaster.show_toast(toast)
            return True
        except Exception:
            return False

    def save_file(self, filename: str = "", content_base64: str = "") -> dict:
        """Guarda un archivo en la ruta que el usuario elija.

        El diálogo nativo no depende de la activación de usuario que exige
        ``window.showSaveFilePicker``. Así el explorador de Windows aparece
        incluso cuando el informe tarda en generarse.
        """
        window = self.window
        if window is None:
            return {"saved": False, "cancelled": False, "error": "window-unavailable"}

        raw = str(content_base64 or "")
        if raw.startswith("data:"):
            raw = raw.split(",", 1)[-1]
        try:
            payload = base64.b64decode(raw, validate=True)
        except Exception:
            return {"saved": False, "cancelled": False, "error": "invalid-content"}

        safe_name = Path(str(filename or "")).name.strip() or "archivo"
        suffix = Path(safe_name).suffix
        try:
            import webview

            dialog = getattr(webview, "FileDialog", None)
            dialog_type = dialog.SAVE if dialog is not None else webview.SAVE_DIALOG
            result = window.create_file_dialog(
                dialog_type,
                directory=str(Path.home()),
                save_filename=safe_name,
                file_types=_file_types_for_suffix(suffix),
            )
        except Exception as error:
            return {"saved": False, "cancelled": False, "error": str(error)}

        if not result:
            return {"saved": False, "cancelled": True}

        selected_path = result[0] if isinstance(result, (tuple, list)) else result
        target = Path(str(selected_path))
        if suffix and not target.suffix:
            target = target.with_suffix(suffix)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        except Exception as error:
            return {"saved": False, "cancelled": False, "error": str(error)}

        return {
            "saved": True,
            "cancelled": False,
            "path": str(target),
        }

    def start_update_monitor(self, interval_seconds: int = 15 * 60) -> None:
        """Consulta releases aunque la ventana esté oculta en la bandeja."""
        if self._update_monitor_thread and self._update_monitor_thread.is_alive():
            return

        self._update_monitor_stop.clear()

        def monitor() -> None:
            while not self._update_monitor_stop.wait(interval_seconds):
                try:
                    from app.services.updates import check_for_update

                    info = check_for_update(force=True)
                    if not info.get("update_available") or info.get("error"):
                        continue
                    version = str(info.get("latest_version") or "")
                    notes = (info.get("notes_items") or [])[:3]
                    self.notify_update(
                        version,
                        f"SENA Certificación v{version} disponible",
                        " · ".join(notes)
                        or "Abre la aplicación para ver las novedades e instalar la actualización.",
                    )
                except Exception:
                    # Un fallo de red no debe cerrar ni bloquear la aplicación.
                    continue

        self._update_monitor_thread = threading.Thread(
            target=monitor,
            name="sena-update-monitor",
            daemon=True,
        )
        self._update_monitor_thread.start()

    def stop_update_monitor(self) -> None:
        """Detiene la comprobación de releases al cerrar la ventana."""
        self._update_monitor_stop.set()
        thread = self._update_monitor_thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=2)
        self._update_monitor_thread = None

    def open_external(self, url: str = "") -> dict:
        """Abre un enlace externo en el navegador predeterminado."""
        url = str(url or "").strip()
        if not url.startswith(("https://", "http://")):
            return {"opened": False, "error": "invalid-url"}
        try:
            import webbrowser

            return {"opened": bool(webbrowser.open(url))}
        except Exception as error:
            return {"opened": False, "error": str(error)}

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

            delivered = self._notify_windows_toast(
                title,
                body,
                lambda: self.open_conflict_resolution(fingerprint),
            )
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

    def notify_update(self, version: str = "", title: str = "", body: str = "") -> dict:
        """Muestra un toast con las novedades de la nueva versión."""
        version = str(version or "").strip()
        if not version:
            return {"delivered": False, "method": None, "version": version}
        title = title or f"Nueva versión {version} disponible"
        body = body or (
            "Abre SENA Certificación para ver las novedades e instalar "
            "la actualización."
        )
        with self._lock:
            if version in self._notified_updates:
                return {
                    "delivered": True,
                    "method": "deduped",
                    "version": version,
                }
            delivered = self._notify_windows_toast(
                title,
                body,
                self._open_updates_js,
            )
            method = "windows-toasts" if delivered else None
            if not delivered:
                delivered = self._notify_plyer(title, body)
                method = "plyer" if delivered else None
            if delivered:
                self._notified_updates.add(version)
            return {
                "delivered": bool(delivered),
                "method": method,
                "version": version,
            }


def run_desktop_window(url: str, background: bool = False) -> None:
    """Abre la aplicación en una ventana nativa de escritorio.

    La ventana se crea siempre en este proceso (el principal) y queda oculta
    cuando la aplicación arranca en segundo plano. La bandeja del sistema puede
    mostrarla después sin lanzar otra instancia.
    """
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

    from app.desktop import register_handlers, unregister_handlers

    bridge = DesktopNotificationBridge(url)
    state: dict[str, object] = {"window": None, "quitting": False}

    def create_window() -> None:
        window = webview.create_window(
            "SENA Certificación",
            url,
            width=1440,
            height=900,
            min_size=(1024, 700),
            confirm_close=False,
            js_api=bridge,
            hidden=background,
        )
        bridge._attach(window)

        def on_closing() -> bool:
            if state["quitting"]:
                return True
            # Cerrar la ventana la oculta: la aplicación sigue disponible en la
            # bandeja y "Salir" es la forma explícita de terminarla.
            try:
                window.hide()
            except Exception:
                pass
            return False

        try:
            window.events.closing += on_closing
        except Exception:
            pass
        state["window"] = window

    def show_window() -> bool:
        window = state.get("window")
        if window is None:
            return False
        try:
            window.show()
        except Exception:
            return False
        try:
            window.restore()
        except Exception:
            pass
        return True

    def quit_app() -> None:
        state["quitting"] = True
        window = state.get("window")
        if window is None:
            return
        try:
            window.destroy()
        except Exception:
            pass

    def evaluate_window(script: str) -> bool:
        window = state.get("window")
        if window is None:
            return False
        try:
            window.evaluate_js(script)
            return True
        except Exception:
            return False

    create_window()
    register_handlers(show_window, quit_app, evaluate_window)
    bridge.start_update_monitor()
    try:
        webview.start()
    finally:
        bridge.stop_update_monitor()
        unregister_handlers()


def _acquire_instance(port: int) -> bool:
    """Devuelve False si ya hay otra instancia en ejecucion."""
    if not getattr(sys, "frozen", False) and os.getenv("SENA_SINGLE_INSTANCE", "1") != "1":
        return True
    try:
        import ctypes

        mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "SENA_Certificacion_App_Mutex")
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            return False
        # Guardar el handle para que no se libere.
        globals()["_instance_mutex"] = mutex
    except Exception:
        pass
    return True


def _write_port_file(port: int) -> None:
    try:
        from app.runtime import data_dir

        (data_dir() / "port.txt").write_text(str(port), encoding="utf-8")
    except Exception:
        pass


def _read_port_file() -> int | None:
    try:
        from app.runtime import data_dir

        text = (data_dir() / "port.txt").read_text(encoding="utf-8").strip()
        return int(text)
    except Exception:
        return None


def _open_existing_instance(timeout: float = 25.0) -> None:
    """Pide a la instancia activa que muestre su ventana (no abre el navegador)."""
    import json
    import urllib.error
    import urllib.request
    import webbrowser

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        port = _read_port_file()
        if port:
            try:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/desktop/show",
                    method="POST",
                    data=b"",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read() or b"{}")
                if payload.get("shown"):
                    return
                break
            except urllib.error.HTTPError:
                # Instancia antigua sin el endpoint: se usa el navegador.
                break
            except Exception:
                pass
        time.sleep(0.4)

    port = _read_port_file() or 8000
    webbrowser.open(f"http://127.0.0.1:{port}")


if __name__ == "__main__":
    from app.version import APP_NAME, APP_VERSION

    smoke_test = "--smoke-test" in sys.argv or os.getenv("SENA_SMOKE_TEST") == "1"
    background = "--background" in sys.argv or os.getenv("SENA_BACKGROUND") == "1"

    # Si ya hay una instancia, pedirle que muestre su ventana y salir.
    if not smoke_test and not _acquire_instance(0):
        _open_existing_instance()
        sys.exit(0)

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
        _write_port_file(port)
        if smoke_test:
            import urllib.request

            print(f"{APP_NAME} {APP_VERSION} - prueba de arranque")
            for path in ("/", "/api/version", "/api/learners"):
                with urllib.request.urlopen(f"{url}{path}", timeout=10) as response:
                    print(f"  {path} -> HTTP {response.status}")
            print("SMOKE_OK")
        else:
            from app.desktop import request_quit
            from app.tray import start_tray_thread

            def _stop():
                server.should_exit = True
                request_quit()

            start_tray_thread(port, _stop)
            run_desktop_window(url, background=background)

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
