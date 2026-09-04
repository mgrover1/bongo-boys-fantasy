"""Shared loaders for in-season tools."""

from __future__ import annotations

from dataclasses import dataclass

from bongo_boys import LEAGUE_ID, MY_ROSTER_ID, SEASON
from bongo_boys.draft.prepare import baselines, lineup_value, replacement_levels
from bongo_boys.league import LeagueConfig, Roster, fetch_rosters
from bongo_boys.projections import Player, build_pool
from bongo_boys.sleeper import Sleeper

SKILL = ("QB", "RB", "WR", "TE")


@dataclass
class Context:
    api: Sleeper
    league: LeagueConfig
    pool: dict[str, Player]
    rosters: dict[int, Roster]
    base: dict[str, float]
    week: int
    my: Roster

    def players_of(self, roster: Roster) -> list[Player]:
        return [self.pool[p] for p in roster.players if p in self.pool]

    def rostered_ids(self) -> set[str]:
        return {p for r in self.rosters.values() for p in r.players}

    def free_agents(self) -> list[Player]:
        taken = self.rostered_ids()
        return sorted((p for p in self.pool.values() if p.id not in taken), key=lambda p: -p.value)

    def team_value(self, players: list[Player]) -> float:
        repl = replacement_levels(self.league, self.pool)
        return lineup_value(players, self.league, {p.id: p.value for p in players}, repl)

    def starters(self, players: list[Player]) -> list[Player]:
        """Deterministic best lineup by season value (same slot logic as the sim metric)."""
        from bongo_boys.league import FLEX_ELIGIBLE

        remaining = sorted(players, key=lambda p: -p.value)
        used, out = set(), []
        slots = self.league.starter_slots
        for s in [s for s in slots if s not in FLEX_ELIGIBLE] + [
            s for s in slots if s in FLEX_ELIGIBLE
        ]:
            for p in remaining:
                if p.id not in used and p.pos in FLEX_ELIGIBLE.get(s, (s,)):
                    used.add(p.id)
                    out.append(p)
                    break
        return out


def load_context(api: Sleeper | None = None) -> Context:
    api = api or Sleeper()
    league = LeagueConfig.fetch(api, LEAGUE_ID)
    pool = build_pool(api, league, SEASON)
    rosters = fetch_rosters(api, LEAGUE_ID)
    week = int(api.state().get("week") or 1)
    return Context(api, league, pool, rosters, baselines(league, pool), week, rosters[MY_ROSTER_ID])


def fmt(p: Player, base: dict[str, float] | None = None) -> str:
    inj = f" [{p.injury_status}]" if p.injury_status else ""
    vbd = f" vbd {p.value - base.get(p.pos, 0):+6.1f}" if base else ""
    return f"{p.name:<24} {p.pos:<3} {p.team or 'FA':<4} val {p.value:6.1f}{vbd} adp {p.adp:5.0f} miss {p.miss_rate:.0%}{inj}"
