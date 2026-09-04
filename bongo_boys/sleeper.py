"""Thin read-only Sleeper API client with an on-disk cache."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import requests

V1 = "https://api.sleeper.app/v1"
V2 = "https://api.sleeper.com"  # undocumented projections / stats host
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")
DAY = 86400


def cache_dir() -> Path:
    d = Path(os.environ.get("BONGO_CACHE", "~/.cache/bongo-boys")).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    return d


class Sleeper:
    def __init__(self, session: requests.Session | None = None, offline: bool = False):
        self.session = session or requests.Session()
        self.offline = offline

    def get(self, url: str, ttl: int = 0) -> Any:
        """GET `url`; reuse a cached copy younger than `ttl` seconds."""
        path = cache_dir() / (hashlib.sha1(url.encode()).hexdigest() + ".json")
        if path.exists() and (ttl < 0 or self.offline or time.time() - path.stat().st_mtime < ttl):
            return json.loads(path.read_text())
        resp = self.session.get(url, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        path.write_text(json.dumps(data))
        return data

    # --- v1 ---------------------------------------------------------------
    def user(self, name: str) -> dict:
        return self.get(f"{V1}/user/{name}", ttl=DAY)

    def state(self) -> dict:
        return self.get(f"{V1}/state/nfl", ttl=3600)

    def league(self, league_id: str) -> dict:
        return self.get(f"{V1}/league/{league_id}", ttl=3600)

    def rosters(self, league_id: str) -> list[dict]:
        return self.get(f"{V1}/league/{league_id}/rosters", ttl=300)

    def users(self, league_id: str) -> list[dict]:
        return self.get(f"{V1}/league/{league_id}/users", ttl=DAY)

    def drafts(self, league_id: str) -> list[dict]:
        return self.get(f"{V1}/league/{league_id}/drafts", ttl=3600)

    def transactions(self, league_id: str, week: int) -> list[dict]:
        return self.get(f"{V1}/league/{league_id}/transactions/{week}", ttl=300)

    def matchups(self, league_id: str, week: int) -> list[dict]:
        return self.get(f"{V1}/league/{league_id}/matchups/{week}", ttl=300)

    def draft(self, draft_id: str) -> dict:
        return self.get(f"{V1}/draft/{draft_id}", ttl=60)

    def picks(self, draft_id: str, ttl: int = 0) -> list[dict]:
        return self.get(f"{V1}/draft/{draft_id}/picks", ttl=ttl)

    def traded_picks(self, draft_id: str) -> list[dict]:
        return self.get(f"{V1}/draft/{draft_id}/traded_picks", ttl=300)

    def players(self) -> dict[str, dict]:
        return self.get(f"{V1}/players/nfl", ttl=DAY)

    def trending(self, kind: str = "add", hours: int = 24, limit: int = 50) -> list[dict]:
        url = f"{V1}/players/nfl/trending/{kind}?lookback_hours={hours}&limit={limit}"
        return self.get(url, ttl=1800)

    # --- undocumented (api.sleeper.com) ------------------------------------
    @staticmethod
    def _pos_query() -> str:
        return "&".join(f"position[]={p}" for p in POSITIONS)

    def season_projections(self, season: str) -> list[dict]:
        url = f"{V2}/projections/nfl/{season}?season_type=regular&{self._pos_query()}&order_by=ppr"
        return self.get(url, ttl=6 * 3600)

    def week_projections(self, season: str, week: int) -> list[dict]:
        url = (
            f"{V2}/projections/nfl/{season}/{week}?season_type=regular"
            f"&{self._pos_query()}&order_by=ppr"
        )
        return self.get(url, ttl=3600)

    def season_stats(self, season: str) -> list[dict]:
        url = f"{V2}/stats/nfl/{season}?season_type=regular&{self._pos_query()}&order_by=pts_ppr"
        return self.get(url, ttl=7 * DAY)
