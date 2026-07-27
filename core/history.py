"""Maç geçmişi: sqlite, sadece stdlib.

Biten her maç tek bir satır: mod, sınıflar, deste, sonuç, tur sayısı. Amaç
"hangi deste hangi sınıfa karşı ne yapıyor" sorusunun tek sorguyla
cevaplanabilmesi.

Aynı maçın iki kez yazılmasını (kaynak oturum dizini, maçın başlangıç saati)
çifti engelliyor. Böylece canlı takip ile eski logların içe aktarımı aynı
veritabanında çakışmadan birleşiyor, içe aktarma istendiği kadar tekrarlanabilir.

Veritabanı erişilemezse (izin, bozuk dosya) sınıf sessizce devre dışı kalır:
geçmiş tutulamıyor diye maç takibi durmasın.
"""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .state import Game

DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", "~/.local/share")).expanduser() / "deste"
DB_PATH = DATA_DIR / "history.db"

# Kırılım alınabilen sütunlar. Sorgu metnine doğrudan gömüldüğü için whitelist.
GROUPS = ("deck", "my_class", "opponent_class", "mode", "format_type")

SOURCE_RE = re.compile(r"(\d{4})_(\d{2})_(\d{2})_(\d{2})_(\d{2})_(\d{2})$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    started_ts TEXT NOT NULL,
    played_at TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL DEFAULT '',
    format_type TEXT NOT NULL DEFAULT '',
    deck TEXT NOT NULL DEFAULT '',
    my_class TEXT NOT NULL DEFAULT '',
    opponent_class TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL DEFAULT '',
    turns INTEGER NOT NULL DEFAULT 0,
    went_first INTEGER NOT NULL DEFAULT 0,
    UNIQUE (source, started_ts)
);
CREATE INDEX IF NOT EXISTS matches_played_at ON matches (played_at);
"""

COLUMNS = (
    "source",
    "started_ts",
    "played_at",
    "mode",
    "format_type",
    "deck",
    "my_class",
    "opponent_class",
    "result",
    "turns",
    "went_first",
)

INSERT = (
    f"INSERT OR IGNORE INTO matches ({', '.join(COLUMNS)}) "
    f"VALUES ({', '.join('?' * len(COLUMNS))})"
)


@dataclass(slots=True)
class MatchRecord:
    source: str = ""  # oturum log dizininin adı
    started_ts: str = ""  # log içi saat, maçın CREATE_GAME anı
    played_at: str = ""  # YYYY-MM-DD HH:MM:SS, dizin tarihi ile birleştirilmiş
    mode: str = ""  # RANKED, CASUAL, ARENA ...
    format_type: str = ""  # STANDARD, WILD
    deck: str = ""  # takip edilen deste adı, eşleşmediyse boş
    my_class: str = ""
    opponent_class: str = ""
    result: str = ""  # WON / LOST / TIED
    turns: int = 0
    went_first: bool = False

    def as_row(self) -> tuple:
        return (
            self.source,
            self.started_ts,
            self.played_at,
            self.mode,
            self.format_type,
            self.deck,
            self.my_class,
            self.opponent_class,
            self.result,
            int(self.turns),
            int(self.went_first),
        )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "MatchRecord":
        return cls(
            source=row["source"],
            started_ts=row["started_ts"],
            played_at=row["played_at"],
            mode=row["mode"],
            format_type=row["format_type"],
            deck=row["deck"],
            my_class=row["my_class"],
            opponent_class=row["opponent_class"],
            result=row["result"],
            turns=row["turns"],
            went_first=bool(row["went_first"]),
        )


@dataclass(slots=True)
class Stat:
    """Bir kırılımın (deste, sınıf, mod) galibiyet dökümü."""

    key: str = ""
    wins: int = 0
    losses: int = 0
    ties: int = 0

    @property
    def total(self) -> int:
        return self.wins + self.losses + self.ties

    @property
    def decided(self) -> int:
        return self.wins + self.losses

    @property
    def winrate(self) -> float | None:
        """Yüzde olarak galibiyet oranı, beraberlikler dışarıda.

        Hiç sonuçlanmış maç yoksa None: sıfır göstermek "hep kaybetmiş" gibi
        okunuyor, oysa bilinmiyor.
        """
        return (100.0 * self.wins / self.decided) if self.decided else None


def played_at(source: str, started_ts: str) -> str:
    """Oturum dizininin tarihiyle log içi saati birleştirir.

    Power.log satırları yalnızca saati yazıyor, tarih dizin adında duruyor
    (Hearthstone_2026_07_25_20_29_50). Oturum gece yarısını geçtiyse saat
    geriye sarar, o durumda bir gün ekliyoruz.
    """
    match = SOURCE_RE.search(source)
    if match is None or not started_ts:
        return ""
    parts = started_ts.split(":")
    if len(parts) < 3:
        return ""
    try:
        session = datetime(*(int(g) for g in match.groups()))
        stamp = session.replace(
            hour=int(parts[0]), minute=int(parts[1]), second=int(float(parts[2]))
        )
    except ValueError:
        return ""
    if stamp < session:
        stamp += timedelta(days=1)
    return stamp.strftime("%Y-%m-%d %H:%M:%S")


def from_game(
    game: Game,
    source: str,
    my_class: str = "",
    opponent_class: str = "",
    deck: str = "",
) -> MatchRecord:
    """Biten maçtan kayıt üretir.

    Sınıflar dışarıdan geliyor: kahraman kartından sınıfa çeviren kart
    veritabanı data katmanında, core oraya bakmaz.
    """
    return MatchRecord(
        source=source,
        started_ts=game.started_ts,
        played_at=played_at(source, game.started_ts),
        mode=game.meta.get("GameType", "").removeprefix("GT_"),
        format_type=game.meta.get("FormatType", "").removeprefix("FT_"),
        deck=deck,
        my_class=my_class,
        opponent_class=opponent_class,
        result=game.result,
        turns=game.game_turn,
        went_first=game.first_player_id is not None
        and game.first_player_id == game.local_player_id,
    )


class History:
    def __init__(self, path: Path | str = DB_PATH):
        self.path = Path(path)
        self.conn: sqlite3.Connection | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(str(self.path))
            self.conn.row_factory = sqlite3.Row
            self.conn.executescript(SCHEMA)
        except (sqlite3.Error, OSError):
            self.conn = None

    @property
    def available(self) -> bool:
        return self.conn is not None

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    # --- yazma ----------------------------------------------------------

    def add(self, record: MatchRecord) -> bool:
        """Maçı yazar. Zaten kayıtlıysa dokunmaz ve False döner."""
        if self.conn is None:
            return False
        try:
            with self.conn:
                cursor = self.conn.execute(INSERT, record.as_row())
        except sqlite3.Error:
            return False
        return cursor.rowcount > 0

    def add_many(self, records) -> int:
        return sum(1 for record in records if self.add(record))

    # --- okuma ----------------------------------------------------------

    def _query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        if self.conn is None:
            return []
        try:
            return self.conn.execute(sql, params).fetchall()
        except sqlite3.Error:
            return []

    @staticmethod
    def _filter(mode: str) -> tuple[str, tuple]:
        return (" WHERE mode = ?", (mode,)) if mode else ("", ())

    def matches(self, limit: int = 200, mode: str = "") -> list[MatchRecord]:
        """En yeni maçtan başlayarak kayıtlar."""
        where, params = self._filter(mode)
        sql = f"SELECT * FROM matches{where} ORDER BY played_at DESC, id DESC LIMIT ?"
        return [MatchRecord.from_row(row) for row in self._query(sql, params + (limit,))]

    def summary(self, group: str, mode: str = "") -> list[Stat]:
        """Bir sütuna göre galibiyet dökümü, çok oynanan üstte."""
        if group not in GROUPS:
            raise ValueError(f"bilinmeyen kırılım: {group}")
        where, params = self._filter(mode)
        sql = (
            f"SELECT {group} AS key, "
            "SUM(result = 'WON') AS wins, "
            "SUM(result = 'LOST') AS losses, "
            "SUM(result = 'TIED') AS ties "
            f"FROM matches{where} GROUP BY {group} ORDER BY COUNT(*) DESC, key ASC"
        )
        return [
            Stat(row["key"] or "", row["wins"] or 0, row["losses"] or 0, row["ties"] or 0)
            for row in self._query(sql, params)
        ]

    def totals(self, mode: str = "") -> Stat:
        where, params = self._filter(mode)
        sql = (
            "SELECT SUM(result = 'WON') AS wins, "
            "SUM(result = 'LOST') AS losses, "
            "SUM(result = 'TIED') AS ties "
            f"FROM matches{where}"
        )
        rows = self._query(sql, params)
        if not rows:
            return Stat()
        row = rows[0]
        return Stat("", row["wins"] or 0, row["losses"] or 0, row["ties"] or 0)

    def deck_classes(self) -> dict[str, str]:
        """Deste adı -> en çok oynandığı sınıf. Deste listesindeki portreler için."""
        sql = (
            "SELECT deck, my_class, COUNT(*) AS n FROM matches "
            "GROUP BY deck, my_class ORDER BY n ASC"
        )
        # Artan sırada gezilince en çok oynanan sınıf en sona, yani sözlükte
        # kalan değer olur.
        return {row["deck"]: row["my_class"] for row in self._query(sql)}

    def modes(self) -> list[str]:
        sql = "SELECT mode, COUNT(*) AS n FROM matches GROUP BY mode ORDER BY n DESC"
        return [row["mode"] for row in self._query(sql) if row["mode"]]
