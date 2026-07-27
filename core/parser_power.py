"""Power.log satır ayrıştırıcısı.

Sadece ``GameState.*`` satırları işlenir. ``PowerTaskList.*`` satırları aynı
içeriğin istemci tarafındaki kopyasıdır, ikisi birden işlenirse her olay iki
kere sayılır. Logda 74927 GameState satırına karşılık 74384 PowerTaskList
satırı var, yani kopya hacmi ciddi.

Ayrıştırıcı durum tutmaz, sadece satırı olaya çevirir. Oyun durumu core.state
tarafından kurulur.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# D 18:50:06.6268596 GameState.DebugPrintPower() -     TAG_CHANGE Entity=3 tag=TURN value=1
LINE_RE = re.compile(
    r"^\w \s*(?P<ts>\d+:\d+:\d+\.\d+) (?P<cls>\w+)\.(?P<fn>\w+)\(\) - (?P<indent>\s*)(?P<body>.*?)\s*$"
)

# [entityName=Confront the Tol'vir id=35 zone=HAND zonePos=0 cardId=CATA_560 player=2]
ENTITY_BRACKET_RE = re.compile(
    r"\[entityName=(?P<name>.*?) id=(?P<id>\d+) zone=(?P<zone>\w+) "
    r"zonePos=(?P<pos>-?\d+) cardId=(?P<card>\w*) player=(?P<player>\d+)\]"
)

FULL_ENTITY_CREATING_RE = re.compile(r"^FULL_ENTITY - Creating ID=(?P<id>\d+) CardID=(?P<card>\w*)$")
FULL_ENTITY_UPDATING_RE = re.compile(r"^FULL_ENTITY - Updating (?P<ref>.+?) CardID=(?P<card>\w*)$")
SHOW_ENTITY_RE = re.compile(r"^SHOW_ENTITY - Updating (?P<ref>.+?) CardID=(?P<card>\w*)$")
HIDE_ENTITY_RE = re.compile(r"^HIDE_ENTITY - Entity=(?P<ref>.+?) tag=(?P<tag>\w+) value=(?P<value>\w+)$")
CHANGE_ENTITY_RE = re.compile(r"^CHANGE_ENTITY - Updating (?P<ref>.+?) CardID=(?P<card>\w*)$")
TAG_CHANGE_RE = re.compile(
    r"^TAG_CHANGE Entity=(?P<ref>.+?) tag=(?P<tag>\w+) value=(?P<value>-?\w+)(?P<rest>.*)$"
)
TAG_LINE_RE = re.compile(r"^tag=(?P<tag>\w+) value=(?P<value>-?\w+)$")
GAME_ENTITY_RE = re.compile(r"^GameEntity EntityID=(?P<id>\d+)$")
PLAYER_ENTITY_RE = re.compile(r"^Player EntityID=(?P<id>\d+) PlayerID=(?P<pid>\d+)")
BLOCK_START_RE = re.compile(
    r"^BLOCK_START BlockType=(?P<type>\w+) Entity=(?P<ref>.+?) EffectCardId=.*?"
    r"EffectIndex=(?P<effect>-?\d+) Target=(?P<target>.+?) SubOption=(?P<sub>-?\d+)"
)
PLAYER_NAME_RE = re.compile(r"^PlayerID=(?P<pid>\d+), PlayerName=(?P<name>.+)$")
KEY_VALUE_RE = re.compile(r"^(?P<key>BuildNumber|GameType|FormatType|ScenarioID)=(?P<value>.+)$")

UNKNOWN_PLAYER = "UNKNOWN HUMAN PLAYER"


@dataclass(slots=True)
class Event:
    """Ayrıştırılmış tek bir log olayı."""

    kind: str
    ts: str
    indent: int
    data: dict = field(default_factory=dict)


@dataclass(slots=True)
class EntityRef:
    """TAG_CHANGE gibi satırlarda varlığa yapılan atıf.

    Üç biçimde gelebilir: sayısal id, oyuncu adı (Oyuncu#12345), ya da köşeli
    parantezli tam blok. Çözümlemeyi core.state yapar, burada sadece taşınır.
    """

    entity_id: int | None = None
    name: str | None = None
    card_id: str = ""
    zone: str = ""
    player: int | None = None


def parse_entity_ref(raw: str) -> EntityRef:
    raw = raw.strip()
    m = ENTITY_BRACKET_RE.search(raw)
    if m:
        return EntityRef(
            entity_id=int(m.group("id")),
            name=m.group("name"),
            card_id=m.group("card"),
            zone=m.group("zone"),
            player=int(m.group("player")),
        )
    if raw.isdigit():
        return EntityRef(entity_id=int(raw))
    if raw == "GameEntity":
        return EntityRef(name="GameEntity")
    return EntityRef(name=raw)


def parse_line(line: str) -> Event | None:
    """Tek bir Power.log satırını olaya çevirir, ilgisizse None döner."""
    m = LINE_RE.match(line)
    if not m:
        return None
    if m.group("cls") != "GameState":
        return None

    ts = m.group("ts")
    indent = len(m.group("indent"))
    body = m.group("body")
    fn = m.group("fn")

    if fn == "DebugPrintGame":
        return _parse_game_meta(ts, indent, body)
    if fn == "DebugPrintPower":
        return _parse_power(ts, indent, body)
    return None


def _parse_game_meta(ts: str, indent: int, body: str) -> Event | None:
    m = KEY_VALUE_RE.match(body)
    if m:
        return Event("game_meta", ts, indent, {"key": m.group("key"), "value": m.group("value")})
    m = PLAYER_NAME_RE.match(body)
    if m:
        return Event(
            "player_name",
            ts,
            indent,
            {"player_id": int(m.group("pid")), "name": m.group("name")},
        )
    return None


def _parse_power(ts: str, indent: int, body: str) -> Event | None:
    if body == "CREATE_GAME":
        return Event("create_game", ts, indent)

    m = FULL_ENTITY_CREATING_RE.match(body)
    if m:
        return Event(
            "full_entity",
            ts,
            indent,
            {"entity_id": int(m.group("id")), "card_id": m.group("card")},
        )

    m = FULL_ENTITY_UPDATING_RE.match(body) or CHANGE_ENTITY_RE.match(body)
    if m:
        ref = parse_entity_ref(m.group("ref"))
        return Event("full_entity", ts, indent, {"ref": ref, "card_id": m.group("card")})

    m = SHOW_ENTITY_RE.match(body)
    if m:
        ref = parse_entity_ref(m.group("ref").removeprefix("Entity="))
        return Event("show_entity", ts, indent, {"ref": ref, "card_id": m.group("card")})

    m = HIDE_ENTITY_RE.match(body)
    if m:
        return Event(
            "hide_entity",
            ts,
            indent,
            {
                "ref": parse_entity_ref(m.group("ref")),
                "tag": m.group("tag"),
                "value": m.group("value"),
            },
        )

    m = TAG_CHANGE_RE.match(body)
    if m:
        return Event(
            "tag_change",
            ts,
            indent,
            {
                "ref": parse_entity_ref(m.group("ref")),
                "tag": m.group("tag"),
                "value": m.group("value"),
            },
        )

    m = GAME_ENTITY_RE.match(body)
    if m:
        return Event("game_entity", ts, indent, {"entity_id": int(m.group("id"))})

    m = PLAYER_ENTITY_RE.match(body)
    if m:
        return Event(
            "player_entity",
            ts,
            indent,
            {"entity_id": int(m.group("id")), "player_id": int(m.group("pid"))},
        )

    m = TAG_LINE_RE.match(body)
    if m:
        # Bir üstteki varlık bloğuna ait etiket satırı.
        return Event("entity_tag", ts, indent, {"tag": m.group("tag"), "value": m.group("value")})

    m = BLOCK_START_RE.match(body)
    if m:
        return Event(
            "block_start",
            ts,
            indent,
            {
                "block_type": m.group("type"),
                "ref": parse_entity_ref(m.group("ref")),
                "target": parse_entity_ref(m.group("target")),
            },
        )

    if body == "BLOCK_END":
        return Event("block_end", ts, indent)

    return None


def parse_lines(lines):
    """Satır dizisini olay dizisine çevirir."""
    for line in lines:
        event = parse_line(line)
        if event is not None:
            yield event
