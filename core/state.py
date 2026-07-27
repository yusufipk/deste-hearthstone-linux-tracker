"""Oyun durumu makinesi.

Power.log olaylarını alıp varlık tablosunu, bölge geçişlerini ve maç
metadatasını kurar. Tamamen stdlib, UI ve ağ bilmez.

Tasarım notu: olaylar sayılmaz, durum tutulur. Log satırları tekrar edebildiği
için "her DECK -> HAND satırında sayacı bir azalt" yaklaşımı yanlış sonuç verir.
Bunun yerine her varlığın bölgesi saklanır ve yalnızca gerçek bölge değişimi
işlenir.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .parser_power import UNKNOWN_PLAYER, EntityRef, Event

DECK = "DECK"
HAND = "HAND"
PLAY = "PLAY"
GRAVEYARD = "GRAVEYARD"
SETASIDE = "SETASIDE"
REMOVEDFROMGAME = "REMOVEDFROMGAME"
SECRET = "SECRET"

# Mulligan bitene kadar süren adımlar. Bunlardan sonrası artık oyun içidir.
OPENING_STEPS = frozenset(
    {"BEGIN_FIRST", "BEGIN_SHUFFLE", "BEGIN_DRAW", "BEGIN_MULLIGAN", "INVALID"}
)


@dataclass(slots=True)
class Entity:
    entity_id: int
    card_id: str = ""
    name: str = ""
    tags: dict[str, str] = field(default_factory=dict)
    # Varlığın oyuna girerken bulunduğu ilk bölge. İlk yerleşim geçiş sayılmaz.
    initial_zone: str | None = None
    # Maç açılışında (mulligan öncesi) yaratıldı mı? Oyun sırasında desteye
    # karıştırılan kartları başlangıç destesinden ayırmak için gerekli.
    from_opening: bool = False
    # Oyun sırasında destemizden çıkıp da kimliği o an bilinmeyen kartları
    # sonradan çözebilmek için işaretliyoruz.
    left_deck_unknown: bool = False
    # Doğrudan destenin içinde yaratılan kart bir kez sayılsın diye.
    counted_shuffle_in: bool = False

    @property
    def controller(self) -> int | None:
        value = self.tags.get("CONTROLLER")
        return int(value) if value and value.isdigit() else None

    @property
    def zone(self) -> str:
        return self.tags.get("ZONE", "")


@dataclass(slots=True)
class CardEvent:
    """Arayüzde gösterilecek tek bir kart olayı."""

    card_id: str
    name: str
    turn: int
    kind: str  # drawn, played, discarded, revealed, mulliganed
    entity_id: int = 0


@dataclass
class Game:
    started_ts: str = ""
    ended_ts: str = ""
    meta: dict[str, str] = field(default_factory=dict)
    entities: dict[int, Entity] = field(default_factory=dict)
    player_entity_ids: dict[int, int] = field(default_factory=dict)  # player_id -> entity_id
    player_names: dict[int, str] = field(default_factory=dict)
    game_entity_id: int | None = None
    local_player_id: int | None = None
    first_player_id: int | None = None
    turn: int = 0
    result: str = ""  # WON / LOST / TIED
    concluded: bool = False
    opening_done: bool = False

    # Kendi destem. Takip, hangi destenin oynandığından bağımsız yürür:
    # sadece "destemden ne çıktı" ve "desteme ne karıştı" kaydedilir, kalan
    # liste istenen an bir deste listesine göre hesaplanır. Böylece deste
    # maçın ortasında da seçilebilir, sonradan da atanabilir.
    deck_list: Counter[str] | None = None
    cards_left_deck: Counter[str] = field(default_factory=Counter)
    cards_shuffled_in: Counter[str] = field(default_factory=Counter)
    unresolved_left_deck: int = 0  # kimliği hiç açığa çıkmadan destemden çıkanlar

    my_events: list[CardEvent] = field(default_factory=list)
    opponent_events: list[CardEvent] = field(default_factory=list)

    @property
    def opponent_player_id(self) -> int | None:
        if self.local_player_id is None:
            return None
        return 2 if self.local_player_id == 1 else 1

    @property
    def my_name(self) -> str:
        return self.player_names.get(self.local_player_id or 0, "")

    @property
    def opponent_name(self) -> str:
        return self.player_names.get(self.opponent_player_id or 0, "")

    def hero_card_id(self, player_id: int | None) -> str:
        """Oyuncunun kahraman kartı. Sınıf tespiti için kullanılır."""
        if player_id is None:
            return ""
        player_entity_id = self.player_entity_ids.get(player_id)
        if player_entity_id is None:
            return ""
        hero_id = self.entities.get(player_entity_id, Entity(0)).tags.get("HERO_ENTITY")
        if hero_id and hero_id.isdigit():
            return self.entities.get(int(hero_id), Entity(0)).card_id
        return ""

    def zone_count(self, player_id: int | None, zone: str) -> int:
        if player_id is None:
            return 0
        return sum(
            1
            for e in self.entities.values()
            if e.controller == player_id and e.zone == zone and e.entity_id != self.game_entity_id
        )

    @property
    def my_deck_count(self) -> int:
        return self.zone_count(self.local_player_id, DECK)

    @property
    def my_hand_count(self) -> int:
        return self.zone_count(self.local_player_id, HAND)

    @property
    def opponent_deck_count(self) -> int:
        return self.zone_count(self.opponent_player_id, DECK)

    @property
    def opponent_hand_count(self) -> int:
        return self.zone_count(self.opponent_player_id, HAND)

    @property
    def game_turn(self) -> int:
        """Oyuncu turu (her iki oyuncunun sırası birlikte bir tur sayılır)."""
        return (self.turn + 1) // 2

    def set_deck_list(self, cards: Counter[str]) -> None:
        self.deck_list = Counter(cards)

    def remaining_deck(self, deck_list: Counter[str] | None = None) -> Counter[str]:
        """Destede kaldığı bilinen kartlar.

        Çıkan kartlar listeden düşülür, oyun içinde karıştırılanlar eklenir.
        Listede olmayan bir kart çıktıysa (yanlış deste seçilmiş olabilir)
        eksiye düşmemek için kırpılır.
        """
        source = deck_list if deck_list is not None else self.deck_list
        if source is None:
            return Counter()
        remaining = Counter(source)
        remaining.update(self.cards_shuffled_in)
        remaining.subtract(self.cards_left_deck)
        return Counter({card: count for card, count in remaining.items() if count > 0})

    def deck_list_mismatch(self, deck_list: Counter[str] | None = None) -> int:
        """Seçilen destede olmayıp destemizden çıkan kart sayısı.

        Sıfırdan büyükse büyük ihtimalle yanlış deste seçilidir. Deste otomatik
        eşleştirmede aday elemek için kullanılır.
        """
        source = deck_list if deck_list is not None else self.deck_list
        if source is None:
            return 0
        available = Counter(source)
        available.update(self.cards_shuffled_in)
        mismatch = 0
        for card, count in self.cards_left_deck.items():
            extra = count - available.get(card, 0)
            if extra > 0:
                mismatch += extra
        return mismatch


class Tracker:
    """Olay akışını tüketip Game nesnelerini üretir."""

    def __init__(self, on_game_end=None, on_update=None):
        self.game: Game | None = None
        self.games: list[Game] = []
        self._current_entity: Entity | None = None
        self._pending_meta: dict[str, str] = {}
        self._pending_names: dict[int, str] = {}
        # Maçın ilk anlarında hangi oyuncunun biz olduğu daha belli değildir,
        # ama kartlar çoktan dağıtılmaya başlar. Bu geçişleri tamponlayıp
        # yerel oyuncu belirlenince işliyoruz.
        self._pending_zone: list[tuple[Entity, str, str]] = []
        self._on_game_end = on_game_end
        self._on_update = on_update

    # --- olay girişi ---------------------------------------------------

    def feed(self, events) -> None:
        for event in events:
            self.handle(event)

    def handle(self, event: Event) -> None:
        handler = getattr(self, f"_on_{event.kind}", None)
        if handler is not None:
            handler(event)

    # --- oyun sınırları ------------------------------------------------

    def _on_create_game(self, event: Event) -> None:
        self._finish_game(event.ts)
        self.game = Game(started_ts=event.ts, meta=dict(self._pending_meta))
        for player_id, name in self._pending_names.items():
            self._set_player_name(self.game, player_id, name)
        self._pending_meta.clear()
        self._pending_names.clear()
        self._pending_zone.clear()
        self.games.append(self.game)
        self._current_entity = None

    def _finish_game(self, ts: str) -> None:
        game = self.game
        if game is None:
            return
        game.ended_ts = ts
        game.concluded = True
        if self._on_game_end is not None:
            self._on_game_end(game)
        self.game = None

    def close(self) -> None:
        """Akış bittiğinde açık maçı kapatır."""
        self._finish_game(self.game.ended_ts if self.game else "")

    # --- metadata ------------------------------------------------------

    def _on_game_meta(self, event: Event) -> None:
        key, value = event.data["key"], event.data["value"]
        if self.game is not None and not self.game.concluded:
            self.game.meta[key] = value
        else:
            self._pending_meta[key] = value

    def _on_player_name(self, event: Event) -> None:
        player_id, name = event.data["player_id"], event.data["name"]
        if self.game is not None and not self.game.concluded:
            self._set_player_name(self.game, player_id, name)
        else:
            self._pending_names[player_id] = name

    def _set_player_name(self, game: Game, player_id: int, name: str) -> None:
        game.player_names[player_id] = name
        # Maç başında yalnızca bizim adımız bilinir, rakip UNKNOWN HUMAN PLAYER
        # olarak yazılır. Yerel oyuncuyu bu farktan tespit ediyoruz. İki isim
        # hangi sırada gelirse gelsin çalışması için her seferinde yeniden
        # değerlendiriyoruz.
        if game.local_player_id is not None:
            return
        known = [pid for pid, n in game.player_names.items() if n != UNKNOWN_PLAYER]
        unknown = [pid for pid, n in game.player_names.items() if n == UNKNOWN_PLAYER]
        if len(known) == 1 and len(unknown) == 1:
            game.local_player_id = known[0]
            self._flush_pending_zone()

    def _flush_pending_zone(self) -> None:
        """Yerel oyuncu belirlendi, bekleyen bölge geçişlerini şimdi işle."""
        pending, self._pending_zone = self._pending_zone, []
        for entity, old_zone, new_zone in pending:
            self._dispatch_zone_change(entity, old_zone, new_zone)

    # --- varlıklar -----------------------------------------------------

    def _entity(self, entity_id: int) -> Entity:
        game = self.game
        assert game is not None
        entity = game.entities.get(entity_id)
        if entity is None:
            entity = Entity(entity_id)
            game.entities[entity_id] = entity
        return entity

    def _resolve(self, ref: EntityRef) -> Entity | None:
        game = self.game
        if game is None:
            return None
        if ref.entity_id is not None:
            entity = self._entity(ref.entity_id)
            if ref.card_id and not entity.card_id:
                self._set_card_id(entity, ref.card_id)
            if ref.name and not entity.name:
                entity.name = ref.name
            return entity
        if ref.name == "GameEntity":
            return self._entity(game.game_entity_id) if game.game_entity_id else None
        if ref.name:
            for player_id, name in game.player_names.items():
                if name == ref.name:
                    entity_id = game.player_entity_ids.get(player_id)
                    if entity_id is not None:
                        return self._entity(entity_id)
        return None

    def _on_game_entity(self, event: Event) -> None:
        if self.game is None:
            return
        entity = self._entity(event.data["entity_id"])
        self.game.game_entity_id = entity.entity_id
        self._current_entity = entity

    def _on_player_entity(self, event: Event) -> None:
        if self.game is None:
            return
        entity = self._entity(event.data["entity_id"])
        self.game.player_entity_ids[event.data["player_id"]] = entity.entity_id
        self._current_entity = entity

    def _on_full_entity(self, event: Event) -> None:
        if self.game is None:
            return
        ref = event.data.get("ref")
        entity_id = event.data.get("entity_id")
        entity = self._entity(entity_id) if entity_id is not None else self._resolve(ref)
        if entity is None:
            return
        if event.data.get("card_id"):
            self._set_card_id(entity, event.data["card_id"])
        self._current_entity = entity

    def _on_show_entity(self, event: Event) -> None:
        if self.game is None:
            return
        entity = self._resolve(event.data["ref"])
        if entity is None:
            return
        if event.data.get("card_id"):
            self._set_card_id(entity, event.data["card_id"])
        self._current_entity = entity

    def _on_hide_entity(self, event: Event) -> None:
        if self.game is None:
            return
        entity = self._resolve(event.data["ref"])
        if entity is None:
            return
        self._apply_tag(entity, event.data["tag"], event.data["value"])

    def _on_entity_tag(self, event: Event) -> None:
        if self.game is None or self._current_entity is None:
            return
        self._apply_tag(self._current_entity, event.data["tag"], event.data["value"])

    def _on_tag_change(self, event: Event) -> None:
        if self.game is None:
            return
        entity = self._resolve(event.data["ref"])
        if entity is None:
            return
        self._apply_tag(entity, event.data["tag"], event.data["value"])
        self._current_entity = None

    # --- etiket uygulaması ---------------------------------------------

    def _apply_tag(self, entity: Entity, tag: str, value: str) -> None:
        game = self.game
        assert game is not None

        if tag == "ZONE":
            self._apply_zone(entity, value)
            return

        entity.tags[tag] = value

        if tag == "CONTROLLER":
            # Kontrolcü artık biliniyor, destede yaratılmış kartı şimdi sayabiliriz.
            self._maybe_register_shuffle_in(entity)

        if tag == "TURN" and entity.entity_id == game.game_entity_id and value.isdigit():
            game.turn = int(value)
        elif tag == "FIRST_PLAYER" and value == "1":
            for player_id, entity_id in game.player_entity_ids.items():
                if entity_id == entity.entity_id:
                    game.first_player_id = player_id
        elif tag == "STEP" and value not in OPENING_STEPS:
            game.opening_done = True
        elif tag == "PLAYSTATE" and value in ("WON", "LOST", "TIED"):
            for player_id, entity_id in game.player_entity_ids.items():
                if entity_id == entity.entity_id and player_id == game.local_player_id:
                    game.result = value

    def _apply_zone(self, entity: Entity, new_zone: str) -> None:
        game = self.game
        assert game is not None
        old_zone = entity.tags.get("ZONE")
        entity.tags["ZONE"] = new_zone

        if old_zone is None:
            # İlk yerleşim, geçiş değil.
            entity.initial_zone = new_zone
            entity.from_opening = not game.opening_done
            self._maybe_register_shuffle_in(entity)
            return
        if old_zone == new_zone:
            return

        if game.local_player_id is None:
            # Maçın ilk anları: kimin kim olduğu henüz belli değil, sonra işlenecek.
            self._pending_zone.append((entity, old_zone, new_zone))
            return

        self._dispatch_zone_change(entity, old_zone, new_zone)

    def _dispatch_zone_change(self, entity: Entity, old_zone: str, new_zone: str) -> None:
        game = self.game
        assert game is not None
        controller = entity.controller
        if controller is None:
            return
        if controller == game.local_player_id:
            self._track_my_zone_change(entity, old_zone, new_zone)
        elif controller == game.opponent_player_id:
            self._track_opponent_zone_change(entity, old_zone, new_zone)

    def _track_my_zone_change(self, entity: Entity, old_zone: str, new_zone: str) -> None:
        game = self.game
        assert game is not None

        if old_zone == DECK:
            self._remove_from_deck(entity)
            if new_zone == HAND:
                game.my_events.append(
                    CardEvent(entity.card_id, entity.name, game.game_turn, "drawn", entity.entity_id)
                )
        elif new_zone == DECK:
            # Oyun sırasında desteye karıştırılan kart.
            if entity.card_id:
                game.cards_shuffled_in[entity.card_id] += 1
        if old_zone == HAND and new_zone == PLAY:
            game.my_events.append(
                CardEvent(entity.card_id, entity.name, game.game_turn, "played", entity.entity_id)
            )

    def _track_opponent_zone_change(self, entity: Entity, old_zone: str, new_zone: str) -> None:
        game = self.game
        assert game is not None
        if old_zone == HAND and new_zone in (PLAY, SECRET):
            kind = "played"
        elif old_zone == HAND and new_zone == GRAVEYARD:
            kind = "discarded"
        else:
            return
        game.opponent_events.append(
            CardEvent(entity.card_id, entity.name, game.game_turn, kind, entity.entity_id)
        )

    def _maybe_register_shuffle_in(self, entity: Entity) -> None:
        """Oyun sırasında doğrudan destenin içinde yaratılan kartı listeye ekler.

        Tracking gibi etkiler kartı desteye "karıştırırken" yeni bir varlık
        yaratır, bu varlık HAND -> DECK geçişi yapmaz. Saymazsak kart daha
        sonra desteden çıktığında kalan liste eksiye kayar.
        """
        game = self.game
        if game is None or entity.counted_shuffle_in:
            return
        if entity.initial_zone != DECK or entity.from_opening:
            return
        if entity.controller is None or entity.controller != game.local_player_id:
            return
        if not entity.card_id:
            return
        entity.counted_shuffle_in = True
        game.cards_shuffled_in[entity.card_id] += 1

    def _remove_from_deck(self, entity: Entity) -> None:
        """Kart destemizden çıktı. Kimliği henüz bilinmiyorsa işaretle."""
        game = self.game
        assert game is not None
        if not entity.card_id:
            if not entity.left_deck_unknown:
                entity.left_deck_unknown = True
                game.unresolved_left_deck += 1
            return
        game.cards_left_deck[entity.card_id] += 1

    def _set_card_id(self, entity: Entity, card_id: str) -> None:
        """Kart kimliği sonradan açığa çıktığında geciken düşümü tamamla."""
        entity.card_id = card_id
        game = self.game
        if game is not None and game.local_player_id is None:
            # Yedek tespit: isimlerden çözülemediyse (yeniden bağlanma gibi),
            # elindeki kartı bize açık olan oyuncu biziz.
            if entity.zone == HAND and entity.controller is not None:
                game.local_player_id = entity.controller
                self._flush_pending_zone()
        self._maybe_register_shuffle_in(entity)
        if entity.left_deck_unknown:
            entity.left_deck_unknown = False
            if game is not None:
                game.unresolved_left_deck -= 1
            self._remove_from_deck(entity)
