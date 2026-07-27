"""Deste kütüphanesi: oyunun önbelleğinden ve kullanıcının kaydettiği deste
kodlarından desteleri toplar, maça uygun olanı seçer.

Kart kimliği (CATA_560) ile dbfId (122939) arasındaki çeviriyi burada yapıyoruz,
core katmanı yalnızca kart kimlikleriyle çalışır.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from core import deckstring
from core.state import Game

from .cards import CardDB
from .localdecks import LocalDeck, read_all_decks

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser() / "deste"
DECKS_PATH = CONFIG_DIR / "decks.json"


@dataclass
class TrackedDeck:
    name: str
    cards: Counter[str] = field(default_factory=Counter)  # kart kimliği -> adet
    hero_card_id: str = ""
    player_class: str = ""
    format_name: str = ""
    source: str = "local"  # local (oyun önbelleği) veya manual (deste kodu)
    deck_code: str = ""

    @property
    def card_count(self) -> int:
        return sum(self.cards.values())


def _deck_from_dbf(
    cards_db: CardDB,
    name: str,
    dbf_cards: dict[int, int],
    hero_dbf: int,
    format_name: str,
    source: str,
    deck_code: str = "",
) -> TrackedDeck:
    counter: Counter[str] = Counter()
    for dbf_id, count in dbf_cards.items():
        card_id = cards_db.id_from_dbf(dbf_id)
        if card_id:
            counter[card_id] += count
    hero_card_id = cards_db.id_from_dbf(hero_dbf) if hero_dbf else ""
    return TrackedDeck(
        name=name,
        cards=counter,
        hero_card_id=hero_card_id,
        player_class=cards_db.card_class(hero_card_id) if hero_card_id else "",
        format_name=format_name,
        source=source,
        deck_code=deck_code,
    )


def from_local(cards_db: CardDB, deck: LocalDeck) -> TrackedDeck:
    return _deck_from_dbf(
        cards_db, deck.name, deck.cards, deck.hero_dbf, deck.format_name, "local"
    )


def from_deck_code(cards_db: CardDB, code: str, name: str = "") -> TrackedDeck:
    """Deste kodundan takip edilebilir deste üretir."""
    parsed = deckstring.parse(code)
    hero = parsed.heroes[0] if parsed.heroes else 0
    return _deck_from_dbf(
        cards_db,
        name or "Deste kodu",
        parsed.as_counter(),
        hero,
        parsed.format_name,
        "manual",
        code.strip(),
    )


class DeckLibrary:
    """Oyunun önbelleğindeki ve elle eklenen desteler."""

    def __init__(self, cards_db: CardDB, game_dir: Path | None = None):
        self.cards_db = cards_db
        self.game_dir = game_dir
        self.decks: list[TrackedDeck] = []

    def load(self) -> "DeckLibrary":
        self.decks = []
        if self.game_dir is not None:
            for local in read_all_decks(self.game_dir):
                self.decks.append(from_local(self.cards_db, local))
        self.decks.extend(self._load_manual())
        return self

    def _load_manual(self) -> list[TrackedDeck]:
        if not DECKS_PATH.exists():
            return []
        try:
            payload = json.loads(DECKS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        result: list[TrackedDeck] = []
        for entry in payload.get("decks", []):
            code = entry.get("code", "")
            if not code:
                continue
            try:
                result.append(from_deck_code(self.cards_db, code, entry.get("name", "")))
            except deckstring.DeckstringError:
                continue
        return result

    def add_manual(self, code: str, name: str = "") -> TrackedDeck:
        """Deste kodunu kaydeder ve kütüphaneye ekler."""
        deck = from_deck_code(self.cards_db, code, name)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        payload = {"decks": []}
        if DECKS_PATH.exists():
            try:
                payload = json.loads(DECKS_PATH.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        entries = payload.setdefault("decks", [])
        if not any(e.get("code") == deck.deck_code for e in entries):
            entries.append({"name": deck.name, "code": deck.deck_code})
            DECKS_PATH.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        self.decks.append(deck)
        return deck

    # --- eşleştirme -----------------------------------------------------

    def candidates(self, player_class: str) -> list[TrackedDeck]:
        if not player_class:
            return list(self.decks)
        return [d for d in self.decks if d.player_class == player_class]

    def match(self, game: Game) -> TrackedDeck | None:
        """Maça en uygun desteyi seçer.

        Sınıfa göre süzer, sonra destemizden çıkmış kartlarla çelişmeyenleri
        bırakır. Tek aday kalırsa odur; birden fazla aday varsa çıkan kartları
        en çok kapsayan seçilir. Hiçbiri uymuyorsa None döner ve arayüz
        kullanıcıya sorar.
        """
        hero = game.hero_card_id(game.local_player_id)
        player_class = self.cards_db.card_class(hero) if hero else ""
        candidates = self.candidates(player_class)
        if not candidates:
            return None

        consistent = [d for d in candidates if game.deck_list_mismatch(d.cards) == 0]
        pool = consistent or candidates
        if len(pool) == 1:
            return pool[0]

        def coverage(deck: TrackedDeck) -> tuple[int, int]:
            covered = sum(
                min(count, deck.cards.get(card, 0))
                for card, count in game.cards_left_deck.items()
            )
            return (covered, -game.deck_list_mismatch(deck.cards))

        return max(pool, key=coverage)
