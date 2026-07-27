"""Kart verisi: HearthstoneJSON'dan indirir, diske cache'ler.

Not: api.hearthstonejson.com varsayılan urllib User-Agent'ına 403 dönüyor,
bu yüzden kendi UA'mızı göndermek zorunlu.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

CARDS_URL = "https://api.hearthstonejson.com/v1/latest/enUS/cards.json"

# Sınıfın temel kahramanı. Sınıfı simgeleyen bir görsele ihtiyaç duyulduğunda
# (maç geçmişindeki portreler) bu kartın render'ı kullanılıyor.
CLASS_HEROES = {
    "WARRIOR": "HERO_01",
    "SHAMAN": "HERO_02",
    "ROGUE": "HERO_03",
    "PALADIN": "HERO_04",
    "HUNTER": "HERO_05",
    "DRUID": "HERO_06",
    "WARLOCK": "HERO_07",
    "MAGE": "HERO_08",
    "PRIEST": "HERO_09",
    "DEMONHUNTER": "HERO_10",
    "DEATHKNIGHT": "HERO_11",
}

USER_AGENT = "deste/0.1 (kisisel hearthstone tracker; +local)"
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", "~/.cache")).expanduser() / "deste"
CARDS_PATH = CACHE_DIR / "cards.json"
MAX_AGE_SECONDS = 7 * 24 * 3600


def _download(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def cache_is_stale(path: Path = CARDS_PATH, max_age: int = MAX_AGE_SECONDS) -> bool:
    if not path.exists():
        return True
    return (time.time() - path.stat().st_mtime) > max_age


def update_cache(force: bool = False) -> bool:
    """Kart verisini indirir. Ağ yoksa mevcut cache korunur."""
    if not force and not cache_is_stale():
        return True
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        payload = _download(CARDS_URL)
    except (urllib.error.URLError, TimeoutError, OSError):
        return CARDS_PATH.exists()
    tmp = CARDS_PATH.with_suffix(".tmp")
    tmp.write_bytes(payload)
    tmp.replace(CARDS_PATH)
    return True


class CardDB:
    """Kart kimliğinden isim, mana, sınıf gibi alanlara erişim."""

    def __init__(self, cards: list[dict]):
        self.by_id: dict[str, dict] = {c["id"]: c for c in cards if "id" in c}
        self.by_dbf: dict[int, dict] = {c["dbfId"]: c for c in cards if "dbfId" in c}

    @classmethod
    def load(cls, path: Path = CARDS_PATH, auto_update: bool = True) -> "CardDB":
        if auto_update:
            update_cache()
        if not path.exists():
            raise FileNotFoundError(
                f"Kart verisi yok: {path}. İnternete bağlanıp tekrar deneyin."
            )
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def get(self, card_id: str) -> dict:
        return self.by_id.get(card_id, {})

    def name(self, card_id: str) -> str:
        return self.get(card_id).get("name", card_id or "?")

    def cost(self, card_id: str) -> int:
        return self.get(card_id).get("cost", 0)

    def card_class(self, card_id: str) -> str:
        card = self.get(card_id)
        classes = card.get("classes")
        if classes:
            return classes[0]
        return card.get("cardClass", "")

    def rarity(self, card_id: str) -> str:
        return self.get(card_id).get("rarity", "")

    def card_type(self, card_id: str) -> str:
        return self.get(card_id).get("type", "")

    def dbf_id(self, card_id: str) -> int | None:
        return self.get(card_id).get("dbfId")

    def id_from_dbf(self, dbf_id: int) -> str:
        return self.by_dbf.get(dbf_id, {}).get("id", "")

    def collectible_by_dbf(self, dbf_id: int) -> dict:
        return self.by_dbf.get(dbf_id, {})
