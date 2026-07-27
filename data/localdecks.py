"""Oyunun çevrimdışı önbelleğinden destelerimizi okur.

Hearthstone, hesabın destelerini şu dosyada saklıyor:
    <prefix>/users/<kullanıcı>/AppData/Local/Blizzard/Hearthstone/Cache/Offline/
        offlineData_<hi>_<lo>_REGION_<bölge>.cache

Dosya 12 baytlık bir başlıktan sonra bölümler halinde ilerliyor:
    [u32 kayıt sayısı] ( [u32 uzunluk] [protobuf payload] ) * sayı

Protobuf şemaları resmî değil, bayt seviyesinden çıkarıldı:
    Deste kaydı     : 1=id, 2=isim, 4=kahraman dbfId, 19=format
    İçerik kaydı    : 2=deste id, 3=tekrarlı yığın
        yığın       : 1={1=kart dbfId, 2=premium}, 3=adet

Bu biçim resmî olmadığı için her şey savunmacı yazıldı: çözülemeyen kayıt
sessizce atlanır, hiçbir durumda çökmez. Okuma başarısız olursa deste kodu
yapıştırma yolu devrede kalır.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

HEADER_SIZE = 12
MAX_RECORDS_PER_SECTION = 10_000

# Protobuf alan numaraları
F_DECK_ID = 1
F_DECK_NAME = 2
F_DECK_HERO = 4
F_DECK_FORMAT = 19
F_CONTENTS_DECK_ID = 2
F_CONTENTS_STACK = 3
F_STACK_CARD = 1
F_STACK_COUNT = 3
F_CARD_DBF = 1

FORMAT_NAMES = {1: "WILD", 2: "STANDARD", 3: "CLASSIC", 4: "TWIST"}


@dataclass(slots=True)
class LocalDeck:
    deck_id: int
    name: str
    hero_dbf: int = 0
    format_id: int = 0
    cards: dict[int, int] = field(default_factory=dict)  # dbfId -> adet

    @property
    def format_name(self) -> str:
        return FORMAT_NAMES.get(self.format_id, "")

    @property
    def card_count(self) -> int:
        return sum(self.cards.values())


# --- asgari protobuf okuyucu -------------------------------------------


def _varint(data: bytes, index: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while index < len(data):
        byte = data[index]
        index += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, index
        shift += 7
        if shift > 70:
            break
    raise ValueError("bozuk varint")


def parse_message(data: bytes) -> dict[int, list]:
    """Protobuf mesajını {alan: [değer]} sözlüğüne çevirir.

    Uzunluk belirtilmiş alanlar ham bayt olarak döner, gerekirse çağıran
    tarafından tekrar çözülür.
    """
    fields: dict[int, list] = {}
    index = 0
    while index < len(data):
        key, index = _varint(data, index)
        field_number, wire_type = key >> 3, key & 7
        if field_number == 0:
            raise ValueError("geçersiz alan numarası")
        if wire_type == 0:
            value, index = _varint(data, index)
        elif wire_type == 2:
            length, index = _varint(data, index)
            if index + length > len(data):
                raise ValueError("uzunluk taşması")
            value = data[index : index + length]
            index += length
        elif wire_type == 5:
            value = data[index : index + 4]
            index += 4
        elif wire_type == 1:
            value = data[index : index + 8]
            index += 8
        else:
            raise ValueError(f"bilinmeyen wire type {wire_type}")
        fields.setdefault(field_number, []).append(value)
    return fields


def iter_records(data: bytes):
    """Dosyadaki bölümleri gezip her kaydın ham baytını verir."""
    index = HEADER_SIZE
    while index + 4 <= len(data):
        (count,) = struct.unpack_from("<I", data, index)
        index += 4
        if count == 0 or count > MAX_RECORDS_PER_SECTION:
            return
        for _ in range(count):
            if index + 4 > len(data):
                return
            (length,) = struct.unpack_from("<I", data, index)
            index += 4
            if length == 0 or index + length > len(data):
                return
            yield data[index : index + length]
            index += length


# --- kayıt sınıflandırma -----------------------------------------------


def _as_text(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace").strip()


def _parse_deck_record(fields: dict[int, list]) -> LocalDeck | None:
    name_values = fields.get(F_DECK_NAME)
    id_values = fields.get(F_DECK_ID)
    if not name_values or not id_values:
        return None
    if not isinstance(name_values[0], bytes) or not isinstance(id_values[0], int):
        return None
    hero = fields.get(F_DECK_HERO, [0])[0]
    fmt = fields.get(F_DECK_FORMAT, [0])[0]
    return LocalDeck(
        deck_id=id_values[0],
        name=_as_text(name_values[0]),
        hero_dbf=hero if isinstance(hero, int) else 0,
        format_id=fmt if isinstance(fmt, int) else 0,
    )


def _parse_contents_record(fields: dict[int, list]) -> tuple[int, dict[int, int]] | None:
    deck_ids = fields.get(F_CONTENTS_DECK_ID)
    stacks = fields.get(F_CONTENTS_STACK)
    if not deck_ids or not stacks or not isinstance(deck_ids[0], int):
        return None
    cards: dict[int, int] = {}
    for stack_raw in stacks:
        if not isinstance(stack_raw, bytes):
            continue
        try:
            stack = parse_message(stack_raw)
        except ValueError:
            continue
        card_raw = stack.get(F_STACK_CARD, [None])[0]
        count = stack.get(F_STACK_COUNT, [0])[0]
        if not isinstance(card_raw, bytes) or not isinstance(count, int) or count <= 0:
            continue
        try:
            card = parse_message(card_raw)
        except ValueError:
            continue
        dbf = card.get(F_CARD_DBF, [None])[0]
        if isinstance(dbf, int):
            # Aynı kartın normal ve altın kopyaları ayrı yığın olarak geliyor.
            cards[dbf] = cards.get(dbf, 0) + count
    if not cards:
        return None
    return deck_ids[0], cards


def read_decks(cache_path: Path) -> list[LocalDeck]:
    """Önbellekten desteleri okur. Hata durumunda boş liste döner."""
    try:
        data = cache_path.read_bytes()
    except OSError:
        return []

    decks: dict[int, LocalDeck] = {}
    contents: dict[int, dict[int, int]] = {}

    for raw in iter_records(data):
        try:
            fields = parse_message(raw)
        except ValueError:
            continue
        deck = _parse_deck_record(fields)
        if deck is not None:
            # Aynı deste birden fazla bölümde tekrar edebiliyor.
            decks.setdefault(deck.deck_id, deck)
            continue
        parsed = _parse_contents_record(fields)
        if parsed is not None:
            deck_id, cards = parsed
            contents.setdefault(deck_id, cards)

    for deck_id, cards in contents.items():
        if deck_id in decks:
            decks[deck_id].cards = cards

    # Oyun aynı desteyi "yerel" ve "orijinal" olmak üzere iki kopya halinde
    # önbelleğe alıyor. İsim ve içerik aynıysa tek deste olarak gösteriyoruz.
    unique: dict[tuple, LocalDeck] = {}
    for deck in decks.values():
        if not deck.cards:
            continue
        signature = (deck.name, tuple(sorted(deck.cards.items())))
        unique.setdefault(signature, deck)
    return list(unique.values())


def find_cache_files(game_dir: Path) -> list[Path]:
    """Prefix içindeki çevrimdışı önbellek dosyalarını bulur.

    Wine prefix'lerinde users/<isim> çoğu zaman users/steamuser'a sembolik
    bağdır, aynı dosyayı iki kez okumamak için gerçek yola göre tekilleştiriyoruz.
    """
    drive_c = game_dir.parent.parent
    users = drive_c / "users"
    if not users.is_dir():
        return []
    seen: dict[Path, Path] = {}
    for user_dir in sorted(users.iterdir()):
        offline = (
            user_dir / "AppData" / "Local" / "Blizzard" / "Hearthstone" / "Cache" / "Offline"
        )
        if not offline.is_dir():
            continue
        for cache_file in sorted(offline.glob("offlineData_*.cache")):
            seen.setdefault(cache_file.resolve(), cache_file)
    return list(seen.values())


def read_all_decks(game_dir: Path) -> list[LocalDeck]:
    decks: list[LocalDeck] = []
    for cache_file in find_cache_files(game_dir):
        decks.extend(read_decks(cache_file))
    return decks
