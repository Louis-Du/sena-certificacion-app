"""Control de la ventana de escritorio desde otros módulos.

`demo.py` registra aquí los callbacks que permiten mostrar la ventana nativa
(pywebview) cuando el usuario hace clic en "Abrir" desde la bandeja del sistema
o cuando se vuelve a lanzar el ejecutable. La ventana vive en el proceso
principal, por eso no hace falta arrancar una segunda instancia de la
aplicación (que duplicaría memoria y podría bloquearse).
"""

from __future__ import annotations

import threading
from typing import Callable

_lock = threading.Lock()
_show_handler: Callable[[], bool] | None = None
_quit_handler: Callable[[], None] | None = None
_eval_handler: Callable[[str], bool] | None = None


def register_handlers(
    show: Callable[[], bool] | None,
    quit: Callable[[], None] | None = None,
    evaluate: Callable[[str], bool] | None = None,
) -> None:
    global _show_handler, _quit_handler, _eval_handler
    with _lock:
        _show_handler = show
        _quit_handler = quit
        _eval_handler = evaluate


def unregister_handlers() -> None:
    register_handlers(None, None, None)


def request_show() -> bool:
    """Muestra (o vuelve a enfocar) la ventana de escritorio.

    Devuelve ``False`` cuando el proceso actual no tiene una ventana nativa,
    para que el llamador pueda recurrir al navegador.
    """
    with _lock:
        handler = _show_handler
    if handler is None:
        return False
    try:
        return bool(handler())
    except Exception:
        return False


def request_quit() -> bool:
    """Cierra la ventana nativa para que finalice el bucle de pywebview."""
    with _lock:
        handler = _quit_handler
    if handler is None:
        return False
    try:
        handler()
        return True
    except Exception:
        return False


def request_eval(script: str) -> bool:
    """Ejecuta JavaScript en la ventana nativa (por ejemplo, abrir un modal)."""
    with _lock:
        handler = _eval_handler
    if handler is None or not script:
        return False
    try:
        return bool(handler(script))
    except Exception:
        return False
