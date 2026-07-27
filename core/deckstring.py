"""Hearthstone deste kodu (deckstring) çözücü ve kodlayıcı.

Biçim: base64 içinde varint akışı.
    0x00, sürüm(1), format, kahraman sayısı + kahramanlar,
    tek kopyalı kart sayısı + kartlar,
    çift kopyalı kart sayısı + kartlar,
    n kopyalı kart sayısı + (kart, adet) çiftleri,
    isteğe bağlı sideboard bölümü (ETC gibi kartlar için).

Kartlar dbfId ile tutulur, kart kimliğine çevirmek için data.cards gerekir.
Tamamen stdlib.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field

DECKSTRING_VERSION = 1

FORMAT_UNKNOWN = 0
FORMAT_WILD = 1
FORMAT_STANDARD = 2
FORMAT_CLASSIC = 3
FORMAT_TWIST = 4

FORMAT_NAMES = {
    FORMAT_UNKNOWN: "UNKNOWN",
    FORMAT_WILD: "WILD",
    FORMAT_STANDARD: "STANDARD",
    FORMAT_CLASSIC: "CLASSIC",
    FORMAT_TWIST: "TWIST",
}


class DeckstringError(ValueError):
    """Geçersiz ya da bozuk deste kodu."""


@dataclass(slots=True)
class Deck:
    cards: list[tuple[int, int]] = field(default_factory=list)  # (dbfId, adet)
    heroes: list[int] = field(default_factory=list)
    format_id: int = FORMAT_UNKNOWN
    # (dbfId, adet, sahip kartın dbfId'si)
    sideboards: list[tuple[int, int, int]] = field(default_factory=list)

    @property
    def format_name(self) -> str:
        return FORMAT_NAMES.get(self.format_id, "UNKNOWN")

    @property
    def card_count(self) -> int:
        return sum(count for _, count in self.cards)

    def as_counter(self) -> dict[int, int]:
        result: dict[int, int] = {}
        for dbf_id, count in self.cards:
            result[dbf_id] = result.get(dbf_id, 0) + count
        return result


class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.index = 0

    def byte(self) -> int:
        if self.index >= len(self.data):
            raise DeckstringError("deste kodu beklenenden kısa")
        value = self.data[self.index]
        self.index += 1
        return value

    def varint(self) -> int:
        value = 0
        shift = 0
        while True:
            byte = self.byte()
            value |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return value
            shift += 7
            if shift > 63:
                raise DeckstringError("bozuk varint")

    @property
    def at_end(self) -> bool:
        return self.index >= len(self.data)


def _write_varint(chunks: list[bytes], value: int) -> None:
    while True:
        piece = value & 0x7F
        value >>= 7
        if value:
            chunks.append(bytes((piece | 0x80,)))
        else:
            chunks.append(bytes((piece,)))
            return


def parse(deckstring: str) -> Deck:
    """Deste kodunu çözer. Geçersizse DeckstringError fırlatır."""
    text = deckstring.strip()
    if not text:
        raise DeckstringError("boş deste kodu")
    # Oyundan kopyalanan kodlarda başta yorum satırları olabiliyor.
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            text = line
            break
    try:
        raw = base64.b64decode(text + "=" * (-len(text) % 4))
    except (ValueError, TypeError) as exc:
        raise DeckstringError("base64 çözülemedi") from exc

    reader = _Reader(raw)
    if reader.byte() != 0:
        raise DeckstringError("geçersiz deste kodu başlığı")
    version = reader.varint()
    if version != DECKSTRING_VERSION:
        raise DeckstringError(f"desteklenmeyen sürüm: {version}")

    deck = Deck(format_id=reader.varint())

    for _ in range(reader.varint()):
        deck.heroes.append(reader.varint())
    deck.heroes.sort()

    for _ in range(reader.varint()):
        deck.cards.append((reader.varint(), 1))
    for _ in range(reader.varint()):
        deck.cards.append((reader.varint(), 2))
    for _ in range(reader.varint()):
        card = reader.varint()
        deck.cards.append((card, reader.varint()))
    deck.cards.sort()

    # Sideboard bölümü isteğe bağlı, eski kodlarda hiç yok.
    if not reader.at_end and reader.byte() == 1:
        for _ in range(reader.varint()):
            deck.sideboards.append((reader.varint(), 1, reader.varint()))
        for _ in range(reader.varint()):
            deck.sideboards.append((reader.varint(), 2, reader.varint()))
        for _ in range(reader.varint()):
            card = reader.varint()
            count = reader.varint()
            deck.sideboards.append((card, count, reader.varint()))
        deck.sideboards.sort(key=lambda item: (item[2], item[0]))

    return deck


def write(deck: Deck) -> str:
    """Desteyi tekrar deste koduna çevirir."""
    chunks: list[bytes] = [b"\0"]
    _write_varint(chunks, DECKSTRING_VERSION)
    _write_varint(chunks, deck.format_id)

    _write_varint(chunks, len(deck.heroes))
    for hero in sorted(deck.heroes):
        _write_varint(chunks, hero)

    singles = sorted(c for c, n in deck.cards if n == 1)
    doubles = sorted(c for c, n in deck.cards if n == 2)
    others = sorted((c, n) for c, n in deck.cards if n not in (1, 2))

    _write_varint(chunks, len(singles))
    for card in singles:
        _write_varint(chunks, card)
    _write_varint(chunks, len(doubles))
    for card in doubles:
        _write_varint(chunks, card)
    _write_varint(chunks, len(others))
    for card, count in others:
        _write_varint(chunks, card)
        _write_varint(chunks, count)

    if deck.sideboards:
        chunks.append(b"\1")
        for wanted in (1, 2):
            group = sorted(
                (card, owner) for card, count, owner in deck.sideboards if count == wanted
            )
            _write_varint(chunks, len(group))
            for card, owner in group:
                _write_varint(chunks, card)
                _write_varint(chunks, owner)
        group_n = sorted(
            (card, count, owner)
            for card, count, owner in deck.sideboards
            if count not in (1, 2)
        )
        _write_varint(chunks, len(group_n))
        for card, count, owner in group_n:
            _write_varint(chunks, card)
            _write_varint(chunks, count)
            _write_varint(chunks, owner)

    return base64.b64encode(b"".join(chunks)).decode("ascii")
