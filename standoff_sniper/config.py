from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_DIR / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "dry_run": True,
    "emulator": {
        "check_window": False,
        "window_title_keywords": [
            "BlueStacks",
            "LDPlayer",
            "Standoff 2",
            "MSI App Player",
            "Nox",
            "MEmu",
            "MuMu",
        ],
        "last_window": None,
    },
    "coordinates": {
        "refresh_filter": {"x": None, "y": None},
        "first_lot": {"x": None, "y": None},
        "buy_button": {"x": None, "y": None},
    },
    "regions": {
        "first_lot": {"left": None, "top": None, "width": None, "height": None},
        "buy_button_watch": {"left": None, "top": None, "width": None, "height": None},
        "price": {"left": None, "top": None, "width": None, "height": None},
    },
    "templates": {
        "sticker": "templates/sticker.png",
        "buy_button": "templates/buy_button.png",
    },
    "vision": {
        "min_stickers": 3,
        "sticker_threshold": 0.84,
        "buy_button_threshold": 0.82,
        "sticker_min_distance_px": 16,
    },
    "timing": {
        "refresh_double_click_interval_ms": 70,
        "after_refresh_delay_ms": 80,
        "after_lot_click_delay_ms": 35,
        "buy_button_timeout_ms": 650,
        "buy_button_poll_interval_ms": 20,
        "cycle_delay_ms": 40,
    },
    "budget": {
        "enabled": False,
        "max_price": 2.46,
        "decimal_separator": ".",
    },
    "input": {
        "backend": "pydirectinput",
        "click_pause_ms": 15,
        "stop_hotkey": "esc",
        "pause_hotkey": "f4",
    },
    "debug": {
        "save_misses": False,
        "debug_dir": "debug",
    },
    "calibration": {
        "updated_at": None,
    },
}

class ConfigError(RuntimeError):
    """Ошибка чтения или проверки конфигурации."""

def deep_merge(default: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Рекурсивно дополняет пользовательский config новыми полями по умолчанию."""
    result = copy.deepcopy(default)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result

def load_config(path: Path | str = CONFIG_PATH) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        return copy.deepcopy(DEFAULT_CONFIG)

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Не удалось прочитать JSON: {config_path} ({exc})") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"Корень config.json должен быть объектом: {config_path}")

    return deep_merge(DEFAULT_CONFIG, raw)

def save_config(config: dict[str, Any], path: Path | str = CONFIG_PATH) -> None:
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = config_path.with_suffix(config_path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(config_path)

def resolve_project_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return PROJECT_DIR / path

def point_is_ready(point: dict[str, Any]) -> bool:
    return isinstance(point.get("x"), int) and isinstance(point.get("y"), int)

def region_is_ready(region: dict[str, Any]) -> bool:
    keys = ("left", "top", "width", "height")
    return all(isinstance(region.get(key), int) for key in keys) and region["width"] > 0 and region["height"] > 0

def require_point(config: dict[str, Any], name: str) -> dict[str, int]:
    point = config["coordinates"].get(name)
    if not isinstance(point, dict) or not point_is_ready(point):
        raise ConfigError(f"Не откалибрована координата coordinates.{name}")
    return {"x": int(point["x"]), "y": int(point["y"])}

def require_region(config: dict[str, Any], name: str) -> dict[str, int]:
    region = config["regions"].get(name)
    if not isinstance(region, dict) or not region_is_ready(region):
        raise ConfigError(f"Не откалибрована область regions.{name}")
    return {
        "left": int(region["left"]),
        "top": int(region["top"]),
        "width": int(region["width"]),
        "height": int(region["height"]),
    }

def validate_runtime_config(config: dict[str, Any]) -> None:
    """Проверяет только обязательные поля для основного цикла."""
    for point_name in ("refresh_filter", "first_lot", "buy_button"):
        require_point(config, point_name)
    for region_name in ("first_lot", "buy_button_watch"):
        require_region(config, region_name)

    for template_key in ("sticker", "buy_button"):
        template_path = resolve_project_path(config["templates"][template_key])
        if not template_path.exists():
            raise ConfigError(f"Не найден шаблон {template_key}: {template_path}")