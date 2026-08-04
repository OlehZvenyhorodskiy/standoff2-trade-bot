from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import mss
import numpy as np

try:
    from .config import require_region, resolve_project_path
except ImportError:
    from config import require_region, resolve_project_path

@dataclass(frozen=True)
class TemplateMatch:
    x: int
    y: int
    score: float
    width: int
    height: int

class VisionError(RuntimeError):
    """Ошибка захвата экрана, шаблонов или OCR."""

def capture_region(region: dict[str, int]) -> np.ndarray:
    """Быстро снимает область экрана через mss и возвращает BGR-изображение для OpenCV."""
    monitor = {
        "left": int(region["left"]),
        "top": int(region["top"]),
        "width": int(region["width"]),
        "height": int(region["height"]),
    }
    with mss.mss() as sct:
        frame = np.array(sct.grab(monitor))
    return frame[:, :, :3]

def load_template(path_value: str | Path) -> np.ndarray:
    template_path = resolve_project_path(path_value)
    template = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
    if template is None:
        raise VisionError(f"Не удалось загрузить шаблон: {template_path}")
    return template

def match_template(
    image: np.ndarray,
    template: np.ndarray,
    threshold: float,
    min_distance_px: int = 12,
) -> list[TemplateMatch]:
    """Ищет шаблон и отсекает дубли рядом с уже найденными совпадениями."""
    if image.shape[0] < template.shape[0] or image.shape[1] < template.shape[1]:
        return []

    result = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
    ys, xs = np.where(result >= float(threshold))
    candidates = sorted(
        ((int(x), int(y), float(result[y, x])) for x, y in zip(xs, ys)),
        key=lambda item: item[2],
        reverse=True,
    )

    accepted: list[TemplateMatch] = []
    template_h, template_w = template.shape[:2]
    min_distance_sq = int(min_distance_px) ** 2

    for x, y, score in candidates:
        cx = x + template_w // 2
        cy = y + template_h // 2
        too_close = False
        for match in accepted:
            mx = match.x + match.width // 2
            my = match.y + match.height // 2
            if (cx - mx) ** 2 + (cy - my) ** 2 <= min_distance_sq:
                too_close = True
                break
        if not too_close:
            accepted.append(TemplateMatch(x=x, y=y, score=score, width=template_w, height=template_h))

    return accepted

def count_stickers(config: dict[str, Any]) -> tuple[int, list[TemplateMatch]]:
    lot_region = require_region(config, "first_lot")
    frame = capture_region(lot_region)
    template = load_template(config["templates"]["sticker"])
    matches = match_template(
        frame,
        template,
        threshold=float(config["vision"]["sticker_threshold"]),
        min_distance_px=int(config["vision"]["sticker_min_distance_px"]),
    )
    return len(matches), matches

def wait_for_buy_button(config: dict[str, Any]) -> bool:
    """Ждет, пока в заданной области появится кнопка покупки по шаблону."""
    region = require_region(config, "buy_button_watch")
    template = load_template(config["templates"]["buy_button"])
    threshold = float(config["vision"]["buy_button_threshold"])
    timeout_s = int(config["timing"]["buy_button_timeout_ms"]) / 1000
    poll_s = int(config["timing"]["buy_button_poll_interval_ms"]) / 1000
    deadline = time.perf_counter() + timeout_s

    while time.perf_counter() < deadline:
        frame = capture_region(region)
        if match_template(frame, template, threshold=threshold, min_distance_px=8):
            return True
        time.sleep(poll_s)
    return False

def read_price(config: dict[str, Any]) -> float | None:
    """Опциональный OCR цены. Используйте только если скорость цикла остается приемлемой."""
    if not bool(config["budget"]["enabled"]):
        return None

    try:
        import pytesseract
    except ImportError as exc:
        raise VisionError("budget.enabled=true, но pytesseract не установлен") from exc

    price_region = require_region(config, "price")
    frame = capture_region(price_region)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    text = pytesseract.image_to_string(
        binary,
        config="--psm 7 -c tessedit_char_whitelist=0123456789.,",
    )
    match = re.search(r"\d+(?:[.,]\d+)?", text)
    if not match:
        return None

    decimal_separator = str(config["budget"].get("decimal_separator", "."))
    normalized = match.group(0).replace(",", ".")
    if decimal_separator == ",":
        normalized = normalized.replace(",", ".")
    return float(normalized)