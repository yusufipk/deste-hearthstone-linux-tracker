"""Kart görselleri: art.hearthstonejson.com'dan indirir, diske önbelleğe alır.

İki boyut kullanılıyor:
    tile   256x59  kart satırının arka planındaki sanat şeridi
    render 256x388 fareyle üzerine gelince gösterilen tam kart (metni dahil)

İndirmeler arka plan iş parçacıklarında yapılır, arayüz beklemez. Yeni bir
görsel hazır olduğunda `generation` sayacı artar; arayüz bu sayacı izleyip
kendini tazeler. Böylece Qt sinyali gerekmiyor ve bu modül stdlib kalıyor.
"""

from __future__ import annotations

import os
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TILE_URL = "https://art.hearthstonejson.com/v1/tiles/{card_id}.png"
RENDER_URL = "https://art.hearthstonejson.com/v1/render/latest/enUS/256x/{card_id}.png"
USER_AGENT = "deste/0.1 (kisisel hearthstone tracker; +local)"

CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", "~/.cache")).expanduser() / "deste" / "images"

TILE = "tile"
RENDER = "render"


class ImageCache:
    def __init__(self, max_workers: int = 4):
        self.generation = 0
        self._lock = threading.Lock()
        self._pending: set[tuple[str, str]] = set()
        self._failed: set[tuple[str, str]] = set()
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="deste-img")
        for kind in (TILE, RENDER):
            (CACHE_DIR / kind).mkdir(parents=True, exist_ok=True)

    def path_for(self, card_id: str, kind: str = TILE) -> Path:
        return CACHE_DIR / kind / f"{card_id}.png"

    def get(self, card_id: str, kind: str = TILE) -> Path | None:
        """Görsel diskteyse yolunu döner, değilse indirmeye alır ve None döner."""
        if not card_id:
            return None
        path = self.path_for(card_id, kind)
        if path.exists():
            return path
        key = (card_id, kind)
        with self._lock:
            if key in self._pending or key in self._failed:
                return None
            self._pending.add(key)
        self._pool.submit(self._download, card_id, kind)
        return None

    def prefetch(self, card_ids, kind: str = TILE) -> None:
        for card_id in card_ids:
            self.get(card_id, kind)

    def _download(self, card_id: str, kind: str) -> None:
        url = (TILE_URL if kind == TILE else RENDER_URL).format(card_id=card_id)
        key = (card_id, kind)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = response.read()
        except (urllib.error.URLError, TimeoutError, OSError):
            with self._lock:
                self._pending.discard(key)
                self._failed.add(key)
            return

        path = self.path_for(card_id, kind)
        try:
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(payload)
            tmp.replace(path)
        except OSError:
            with self._lock:
                self._pending.discard(key)
                self._failed.add(key)
            return

        with self._lock:
            self._pending.discard(key)
            self.generation += 1

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
