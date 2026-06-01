from __future__ import annotations

import argparse
import sys
import time
from typing import Any

try:
    from .actions import click, double_click
    from .config import ConfigError, load_config, require_point, validate_runtime_config
except ImportError:
    from actions import click, double_click
    from config import ConfigError, load_config, require_point, validate_runtime_config


class StopRequested(Exception):
    """Сигнал остановки основного цикла."""


def _configure_console() -> None:
    """Помогает Windows-консолям корректно выводить русские сообщения."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def ensure_emulator_window(config: dict[str, Any]) -> None:
    """Проверяет наличие окна эмулятора, если это включено в config.json."""
    if not bool(config["emulator"]["check_window"]):
        return

    try:
        import pygetwindow as gw
    except ImportError as exc:
        raise RuntimeError("emulator.check_window=true, но pygetwindow не установлен") from exc

    keywords = [str(item).lower() for item in config["emulator"]["window_title_keywords"]]
    for window in gw.getAllWindows():
        title = (window.title or "").lower()
        if any(keyword in title for keyword in keywords):
            return

    raise RuntimeError("Окно эмулятора не найдено. Проверьте emulator.window_title_keywords в config.json.")


def load_vision_module() -> Any:
    """Загружает OpenCV/mss только тогда, когда они реально нужны."""
    try:
        from . import vision
    except ImportError:
        import vision
    return vision


def install_hotkeys(config: dict[str, Any], state: dict[str, bool]) -> None:
    """Подключает Esc для остановки и F4 для паузы, если доступен пакет keyboard."""
    try:
        import keyboard
    except ImportError:
        print("Пакет keyboard не установлен: остановка будет доступна только через Ctrl+C.")
        return

    stop_hotkey = str(config["input"]["stop_hotkey"])
    pause_hotkey = str(config["input"]["pause_hotkey"])

    keyboard.add_hotkey(stop_hotkey, lambda: state.update(stop=True))
    keyboard.add_hotkey(pause_hotkey, lambda: state.update(paused=not state["paused"]))
    print(f"Горячие клавиши: {stop_hotkey} — стоп, {pause_hotkey} — пауза/продолжить.")


def budget_allows_purchase(config: dict[str, Any]) -> bool:
    if not bool(config["budget"]["enabled"]):
        return True

    vision = load_vision_module()
    price = vision.read_price(config)
    if price is None:
        print("OCR не смог прочитать цену, пропускаю лот.")
        return False

    max_price = float(config["budget"]["max_price"])
    if price > max_price:
        print(f"Цена {price:.2f} выше лимита {max_price:.2f}, пропускаю.")
        return False
    return True


def run_once(config: dict[str, Any]) -> None:
    backend_name = str(config["input"]["backend"])
    click_pause_ms = int(config["input"]["click_pause_ms"])

    refresh_point = require_point(config, "refresh_filter")
    first_lot_point = require_point(config, "first_lot")
    buy_button_point = require_point(config, "buy_button")

    double_click(
        refresh_point,
        backend_name=backend_name,
        interval_ms=int(config["timing"]["refresh_double_click_interval_ms"]),
        pause_ms=click_pause_ms,
    )
    time.sleep(int(config["timing"]["after_refresh_delay_ms"]) / 1000)

    vision = load_vision_module()
    stickers_count, matches = vision.count_stickers(config)
    min_stickers = int(config["vision"]["min_stickers"])
    if stickers_count < min_stickers:
        return

    print(f"Найдено наклеек: {stickers_count}, совпадения: {[round(m.score, 3) for m in matches]}")
    if not budget_allows_purchase(config):
        return

    if bool(config["dry_run"]):
        print("dry_run=true: покупка не выполняется. Для реального клика выключите dry_run в config.json.")
        return

    click(first_lot_point, backend_name=backend_name, pause_ms=click_pause_ms)
    time.sleep(int(config["timing"]["after_lot_click_delay_ms"]) / 1000)

    if not vision.wait_for_buy_button(config):
        print("Кнопка покупки не появилась за таймаут, пропускаю.")
        return

    click(buy_button_point, backend_name=backend_name, pause_ms=click_pause_ms)
    print("Клик покупки выполнен.")


def run_loop(config: dict[str, Any], once: bool = False) -> None:
    ensure_emulator_window(config)
    state = {"stop": False, "paused": False}
    install_hotkeys(config, state)

    print("Старт. По умолчанию dry_run=true, поэтому реальные покупки отключены.")
    while not state["stop"]:
        if state["paused"]:
            time.sleep(0.1)
            continue

        run_once(config)
        if once:
            return
        time.sleep(int(config["timing"]["cycle_delay_ms"]) / 1000)


def main() -> int:
    _configure_console()
    parser = argparse.ArgumentParser(description="Standoff 2 Market Sniper")
    parser.add_argument("--config", default=None, help="Путь к config.json")
    parser.add_argument("--once", action="store_true", help="Выполнить один цикл и выйти")
    args = parser.parse_args()

    try:
        config = load_config(args.config) if args.config else load_config()
        validate_runtime_config(config)
        run_loop(config, once=args.once)
    except (ConfigError, RuntimeError, ImportError, KeyboardInterrupt) as exc:
        print(f"Остановка: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
