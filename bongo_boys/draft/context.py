"""Build a DraftSetup from live Sleeper state (shared by loop, live, board)."""

from __future__ import annotations

import json
from pathlib import Path

from bongo_boys import DRAFT_ID, LEAGUE_ID, MY_ROSTER_ID, SEASON
from bongo_boys.draft.prepare import DraftSetup
from bongo_boys.draft.strategy import PARAMS
from bongo_boys.league import DraftState, LeagueConfig
from bongo_boys.projections import Player, build_pool
from bongo_boys.sleeper import Sleeper

ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = ROOT / "outputs"
BEST_PARAMS = OUTPUTS / "best_strategy.json"


def load_params() -> dict[str, float]:
    """PARAMS from strategy.py, overridden by the best searched set if one exists."""
    params = dict(PARAMS)
    if BEST_PARAMS.exists():
        params.update(json.loads(BEST_PARAMS.read_text()).get("params", {}))
    return params


def load_setup(
    api: Sleeper | None = None, picks_ttl: int = 0
) -> tuple[LeagueConfig, dict[str, Player], DraftState, DraftSetup]:
    api = api or Sleeper()
    league = LeagueConfig.fetch(api, LEAGUE_ID)
    pool = build_pool(api, league, SEASON)
    state = DraftState.fetch(api, DRAFT_ID, MY_ROSTER_ID, picks_ttl=picks_ttl)
    pick_owner = {n: state.owner_of_pick_no(n) for n in range(1, state.teams * state.rounds + 1)}
    taken = {p["pick_no"]: (p["roster_id"], p["player_id"]) for p in state.picks}
    setup = DraftSetup(
        league=league,
        pool=pool,
        teams=state.teams,
        rounds=state.rounds,
        my_roster_id=MY_ROSTER_ID,
        pick_owner=pick_owner,
        taken=taken,
    )
    return league, pool, state, setup


def tiers(players: list[Player], max_tiers: int = 8) -> list[int]:
    """Tier number per player (sorted by value desc). Break where the gap is > mean+1sd of gaps."""
    if len(players) < 3:
        return [1] * len(players)
    top = players[: min(len(players), 40)]
    gaps = [top[i].value - top[i + 1].value for i in range(len(top) - 1)]
    mean = sum(gaps) / len(gaps)
    sd = (sum((g - mean) ** 2 for g in gaps) / len(gaps)) ** 0.5
    thresh = mean + sd
    out, t = [1], 1
    for i in range(1, len(players)):
        gap = players[i - 1].value - players[i].value
        if gap > thresh and t < max_tiers:
            t += 1
        out.append(t)
    return out
