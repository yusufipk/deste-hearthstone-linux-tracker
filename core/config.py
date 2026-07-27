"""Kullanıcı ayarları. ~/.config/deste/config.json"""

from __future__ import annotations

import json
import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser() / "deste"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULTS = {
    "game_dir": "",
    "window_mode": "overlay",  # overlay veya window
    "opacity": 0.92,
    "geometry": {},  # mod -> [genişlik, yükseklik]
    "show_draw_chance": True,
    "selected_deck": "",  # boş ise otomatik eşleştirme
    "language": "auto",  # auto, tr, en
}


def load() -> dict:
    data = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            data.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    return data


def save(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONFIG_PATH)
