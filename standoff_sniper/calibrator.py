from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from typing import Any

try:
    from .actions import InputBackendError, get_mouse_position
    from .config import CONFIG_PATH, load_config, save_config
except ImportError:
    from actions import InputBackendError, get_mouse_position
    from config import CONFIG_PATH, load_config, save_config


POINT_STEPS = [
    ("refresh_filter", "кнопку/чекбокс фильтра «Только с наклейками»"),
    ("first_lot", "центр первого лота, по которому нужно кликать"),
    ("buy_button", "центр кнопки «Купить» в окне подтверждения"),
]

REGION_STEPS = [
    ("first_lot", "область первого лота, где видны наклейки"),
    ("buy_button_watch", "область появления кнопки «Купить»"),
]


def _configure_console() -> None:
    """Помогает Windows-консолям корректно выводить русские сообщения."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _print_header() -> None:
    print("\n=== Калибровка Standoff 2 Market Sniper ===")
    print("Не кликайте по эмулятору во время калибровки: просто наведите курсор и нажмите Enter в консоли.")
    print("Если окно консоли потеряло фокус, верните его Alt+Tab и повторите шаг.\n")


def _read_yes_no(question: str, default: bool = False) -> bool:
    suffix = "Y/n" if default else "y/N"
    answer = input(f"{question} [{suffix}]: ").strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes", "д", "да"}


def _read_int(question: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    while True:
        raw = input(f"{question} [{default}]: ").strip()
        if not raw:
            value = default
        else:
            try:
                value = int(raw)
            except ValueError:
                print("Введите целое число.")
                continue

        if minimum is not None and value < minimum:
            print(f"Минимум: {minimum}")
            continue
        if maximum is not None and value > maximum:
            print(f"Максимум: {maximum}")
            continue
        return value


def _read_float(question: str, default: float, minimum: float | None = None) -> float:
    while True:
        raw = input(f"{question} [{default}]: ").strip().replace(",", ".")
        if not raw:
            value = default
        else:
            try:
                value = float(raw)
            except ValueError:
                print("Введите число, например 2.46")
                continue
        if minimum is not None and value < minimum:
            print(f"Минимум: {minimum}")
            continue
        return value


def capture_point(description: str) -> dict[str, int]:
    input(f"Наведи курсор на {description} и нажми Enter...")
    x, y = get_mouse_position()
    print(f"  записано: x={x}, y={y}")
    return {"x": x, "y": y}


def capture_region(description: str) -> dict[str, int]:
    print(f"\nНастройка области: {description}")
    left_top = capture_point("левый верхний угол области")
    right_bottom = capture_point("правый нижний угол области")

    left = min(left_top["x"], right_bottom["x"])
    top = min(left_top["y"], right_bottom["y"])
    width = abs(right_bottom["x"] - left_top["x"])
    height = abs(right_bottom["y"] - left_top["y"])

    if width <= 0 or height <= 0:
        raise ValueError("Область должна иметь ненулевую ширину и высоту.")

    region = {"left": left, "top": top, "width": width, "height": height}
    print(f"  область: left={left}, top={top}, width={width}, height={height}")
    return region


def find_emulator_window(keywords: list[str]) -> dict[str, Any] | None:
    """Опционально ищет окно эмулятора через pygetwindow, если пакет установлен."""
    try:
        import pygetwindow as gw
    except ImportError:
        print("pygetwindow не установлен: пропускаю автоматический поиск окна эмулятора.")
        return None

    lowered_keywords = [keyword.lower() for keyword in keywords]
    for window in gw.getAllWindows():
        title = (window.title or "").strip()
        if not title:
            continue
        if any(keyword in title.lower() for keyword in lowered_keywords):
            return {
                "title": title,
                "left": int(window.left),
                "top": int(window.top),
                "width": int(window.width),
                "height": int(window.height),
            }
    return None


def calibrate(config: dict[str, Any]) -> dict[str, Any]:
    _print_header()

    if _read_yes_no("Попробовать найти окно эмулятора автоматически?", default=False):
        window = find_emulator_window(config["emulator"]["window_title_keywords"])
        if window:
            config["emulator"]["last_window"] = window
            print(f"Найдено окно: {window['title']} ({window['width']}x{window['height']})")
        else:
            print("Окно эмулятора не найдено. Продолжаю ручную калибровку координат.")

    for key, description in POINT_STEPS:
        config["coordinates"][key] = capture_point(description)

    for key, description in REGION_STEPS:
        config["regions"][key] = capture_region(description)

    use_ocr = _read_yes_no("\nНужна проверка бюджета через OCR цены?", default=bool(config["budget"]["enabled"]))
    config["budget"]["enabled"] = use_ocr
    if use_ocr:
        config["regions"]["price"] = capture_region("область цены первого лота")
        config["budget"]["max_price"] = _read_float(
            "Максимальная цена для покупки",
            float(config["budget"]["max_price"]),
            minimum=0,
        )

    config["vision"]["min_stickers"] = _read_int(
        "\nМинимальное количество наклеек для покупки",
        int(config["vision"]["min_stickers"]),
        minimum=1,
        maximum=4,
    )
    config["vision"]["sticker_threshold"] = _read_float(
        "Порог совпадения шаблона наклейки",
        float(config["vision"]["sticker_threshold"]),
        minimum=0.1,
    )
    config["vision"]["buy_button_threshold"] = _read_float(
        "Порог совпадения шаблона кнопки покупки",
        float(config["vision"]["buy_button_threshold"]),
        minimum=0.1,
    )
    config["calibration"]["updated_at"] = datetime.now(timezone.utc).isoformat()

    return config


def main() -> int:
    _configure_console()
    parser = argparse.ArgumentParser(description="Калибровка координат для Standoff 2 Market Sniper")
    parser.add_argument("--config", default=str(CONFIG_PATH), help="Путь к config.json")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
        config = calibrate(config)
        save_config(config, args.config)
    except (InputBackendError, ValueError, KeyboardInterrupt) as exc:
        print(f"\nКалибровка остановлена: {exc}")
        return 1

    print(f"\nГотово. Конфигурация сохранена: {args.config}")
    time.sleep(0.2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
