from __future__ import annotations

import time
from typing import Any


class InputBackendError(RuntimeError):
    """Ошибка выбора библиотеки для управления мышью."""


def _load_backend(preferred: str = "pydirectinput") -> Any:
    """Лениво загружает backend, чтобы импорт проекта не падал без GUI-зависимостей."""
    candidates = [preferred]
    if preferred != "pyautogui":
        candidates.append("pyautogui")
    if preferred != "pydirectinput":
        candidates.append("pydirectinput")

    errors: list[str] = []
    for name in candidates:
        try:
            module = __import__(name)
            if hasattr(module, "PAUSE"):
                module.PAUSE = 0
            if name == "pyautogui" and hasattr(module, "FAILSAFE"):
                module.FAILSAFE = True
            return module
        except ImportError as exc:
            errors.append(f"{name}: {exc}")

    raise InputBackendError("Не установлены pydirectinput/pyautogui: " + "; ".join(errors))


def get_mouse_position() -> tuple[int, int]:
    """Возвращает текущие экранные координаты курсора."""
    backend = _load_backend("pyautogui")
    pos = backend.position()
    return int(pos.x), int(pos.y)


def click(point: dict[str, int], backend_name: str = "pydirectinput", pause_ms: int = 0) -> None:
    backend = _load_backend(backend_name)
    backend.click(int(point["x"]), int(point["y"]))
    if pause_ms > 0:
        time.sleep(pause_ms / 1000)


def double_click(
    point: dict[str, int],
    backend_name: str = "pydirectinput",
    interval_ms: int = 70,
    pause_ms: int = 0,
) -> None:
    backend = _load_backend(backend_name)
    x = int(point["x"])
    y = int(point["y"])
    backend.click(x, y)
    time.sleep(interval_ms / 1000)
    backend.click(x, y)
    if pause_ms > 0:
        time.sleep(pause_ms / 1000)

