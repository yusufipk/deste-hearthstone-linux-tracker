"""Hearthstone kurulumunu, log dizinini ve log.config durumunu bulur.

Oyun Wine/Proton prefix'i içinde çalıştığı için yol sabit değil. Önce
yapılandırma dosyasına, sonra bilinen prefix konumlarına bakılır.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

LOG_DIR_RE = re.compile(r"^Hearthstone_\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}$")

# Gerekli log bileşenleri. Power için Verbose=1 şart, yoksa oyun durumu eksik gelir.
REQUIRED_COMPONENTS = {
    "Power": {"LogLevel": "1", "FilePrinting": "true", "Verbose": "1"},
    "Zone": {"LogLevel": "1", "FilePrinting": "true"},
    "LoadingScreen": {"LogLevel": "1", "FilePrinting": "true"},
    "Arena": {"LogLevel": "1", "FilePrinting": "true"},
}

# Prefix içindeki oyun dizini, kullanıcıya göre değişen kısımlar glob ile.
PREFIX_GLOBS = (
    "~/Games/*/drive_c/Program Files (x86)/Hearthstone",
    "~/Games/*/*/drive_c/Program Files (x86)/Hearthstone",
    "~/.wine/drive_c/Program Files (x86)/Hearthstone",
    "~/.local/share/lutris/prefixes/*/drive_c/Program Files (x86)/Hearthstone",
    "~/.steam/steam/steamapps/compatdata/*/pfx/drive_c/Program Files (x86)/Hearthstone",
)

CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser() / "deste" / "config.json"


@dataclass(slots=True)
class Installation:
    game_dir: Path
    logs_dir: Path
    log_config: Path | None
    client_config: Path


def _expand(pattern: str) -> list[Path]:
    pattern = os.path.expanduser(pattern)
    root = Path("/")
    parts = Path(pattern).parts[1:]
    try:
        return sorted(root.glob(str(Path(*parts))))
    except (OSError, ValueError):
        return []


def find_game_dir(configured: str | None = None) -> Path | None:
    """Hearthstone kurulum dizinini bulur."""
    if configured:
        path = Path(configured).expanduser()
        if (path / "Hearthstone.exe").exists():
            return path
    for pattern in PREFIX_GLOBS:
        for candidate in _expand(pattern):
            if (candidate / "Hearthstone.exe").exists():
                return candidate
    return None


def find_log_config(game_dir: Path) -> Path | None:
    """log.config dosyasını prefix içindeki kullanıcı dizininde arar."""
    # .../drive_c/Program Files (x86)/Hearthstone -> .../drive_c
    drive_c = game_dir.parent.parent
    users = drive_c / "users"
    if not users.is_dir():
        return None
    for user_dir in users.iterdir():
        candidate = user_dir / "AppData" / "Local" / "Blizzard" / "Hearthstone" / "log.config"
        if candidate.parent.is_dir():
            return candidate
    return None


def read_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def detect(configured_dir: str | None = None) -> Installation | None:
    if configured_dir is None:
        configured_dir = read_config().get("game_dir")
    game_dir = find_game_dir(configured_dir)
    if game_dir is None:
        return None
    return Installation(
        game_dir=game_dir,
        logs_dir=game_dir / "Logs",
        log_config=find_log_config(game_dir),
        client_config=game_dir / "client.config",
    )


def latest_log_dir(logs_dir: Path) -> Path | None:
    """En son oturumun log dizini. Oyun her açılışta yenisini oluşturur."""
    if not logs_dir.is_dir():
        return None
    candidates = [d for d in logs_dir.iterdir() if d.is_dir() and LOG_DIR_RE.match(d.name)]
    if not candidates:
        return None
    return max(candidates, key=lambda d: d.stat().st_mtime)


def parse_log_config(path: Path) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return sections
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            current = {}
            sections[line[1:-1]] = current
        elif "=" in line and current is not None:
            key, _, value = line.partition("=")
            current[key.strip()] = value.strip()
    return sections


def check_log_config(path: Path | None) -> list[str]:
    """Eksik veya hatalı log.config ayarlarını insan okur biçimde döner."""
    if path is None or not path.exists():
        return ["log.config bulunamadı"]
    sections = parse_log_config(path)
    problems: list[str] = []
    for component, required in REQUIRED_COMPONENTS.items():
        section = sections.get(component)
        if section is None:
            problems.append(f"[{component}] bölümü eksik")
            continue
        for key, value in required.items():
            actual = section.get(key)
            if actual is None:
                problems.append(f"[{component}] {key} eksik")
            elif actual.lower() != value.lower():
                problems.append(f"[{component}] {key}={actual}, beklenen {value}")
    return problems


def check_client_config(path: Path) -> list[str]:
    """Log boyut limiti açıksa uzun oturumlarda log kesiliyor."""
    if not path.exists():
        return ["client.config yok, log boyut limiti kaldırılmamış"]
    sections = parse_log_config(path)
    limit = sections.get("Log", {}).get("FileSizeLimit.Int")
    if limit != "-1":
        return [f"client.config FileSizeLimit.Int={limit}, beklenen -1"]
    return []
