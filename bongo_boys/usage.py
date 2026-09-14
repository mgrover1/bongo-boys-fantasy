"""In-season usage: snap share, targets, carries -> rest-of-season value.

One week of points is noise; opportunity is signal. Each completed week the tools trust
usage a little more than the preseason projection, until usage dominates around week 6.
"""

from __future__ import annotations

from dataclasses import dataclass

from bongo_boys.league import LeagueConfig
from bongo_boys.projections import GAMES, INJURY_WEIGHT, Player, score_stats
from bongo_boys.sleeper import Sleeper

INSEASON_RAMP = 0.12  # in-season weight grows this much per completed week ...
INSEASON_MAX = 0.65  # ... capped here (reached after 6 weeks)
OPP_WEIGHT = 0.7  # within the in-season component: opportunity-implied ppg vs actual ppg
RECENT_WEEKS = 4  # trailing window for usage rates
PTS_PER_TARGET = {"WR": 1.75, "TE": 1.65, "RB": 1.55}  # full-PPR expected points per target
PTS_PER_CARRY = 0.62
PTS_PER_RZ_TOUCH = 1.2  # bonus on top of the base rate
PTS_PER_PASS_ATT = 0.48  # QB
PTS_PER_QB_RUSH = 0.75
MIN_SNAP_SHARE_FLAG = 0.5  # starters below this over the last two games get a to-do
HEAT_FLAG = 6.0  # |actual - opportunity| ppg beyond this is a buy-low / sell-high candidate


@dataclass
class Usage:
    games: int = 0
    snap_share: float = 0.0
    tgt_pg: float = 0.0
    carry_pg: float = 0.0
    rz_pg: float = 0.0
    actual_ppg: float = 0.0
    opp_ppg: float = 0.0
    recent_snap_share: float = 0.0  # last two games only
    weight: float = 0.0  # in-season weight used in the blend

    @property
    def heat(self) -> float:
        """Points per game above (+) or below (-) what the usage implies."""
        return self.actual_ppg - self.opp_ppg

    @property
    def inseason_ppg(self) -> float:
        return OPP_WEIGHT * self.opp_ppg + (1 - OPP_WEIGHT) * self.actual_ppg


def opportunity_ppg(
    pos: str, tgt_pg: float, carry_pg: float, rz_pg: float, pass_att_pg: float
) -> float:
    if pos == "QB":
        return PTS_PER_PASS_ATT * pass_att_pg + PTS_PER_QB_RUSH * carry_pg
    if pos in PTS_PER_TARGET:
        return PTS_PER_TARGET[pos] * tgt_pg + PTS_PER_CARRY * carry_pg + PTS_PER_RZ_TOUCH * rz_pg
    return 0.0


def completed_weeks(api: Sleeper, season: str, week: int) -> list[dict[str, dict]]:
    """Weekly stat tables for every finished week, oldest first.

    The current week counts once every team with a scheduled game has posted offensive snaps.
    """
    weeks = [api.week_stats(season, w, week) for w in range(1, week)]
    scheduled = {
        r.get("team")
        for r in api.week_projections(season, week)
        if r.get("game_id") and r.get("team")
    }
    cur = api.week_stats(season, week, week)
    played = {
        (api.players().get(pid) or {}).get("team") for pid, v in cur.items() if v.get("tm_off_snp")
    }
    if scheduled and scheduled <= played:
        weeks.append(cur)
    return weeks


def usage_from_weeks(p: Player, weeks: list[dict[str, dict]], scoring: dict[str, float]) -> Usage:
    rows = [w[p.id] for w in weeks[-RECENT_WEEKS:] if w.get(p.id, {}).get("gp")]
    u = Usage(games=len(rows))
    if not rows:
        return u
    n = len(rows)

    def tot(k: str, rs=rows) -> float:
        return sum(float(r.get(k) or 0) for r in rs)

    u.snap_share = tot("off_snp") / tot("tm_off_snp") if tot("tm_off_snp") else 0.0
    last2 = rows[-2:]
    u.recent_snap_share = (
        tot("off_snp", last2) / tot("tm_off_snp", last2) if tot("tm_off_snp", last2) else 0.0
    )
    u.tgt_pg = tot("rec_tgt") / n
    u.carry_pg = tot("rush_att") / n
    u.rz_pg = (tot("rush_rz_att") + tot("rec_rz_tgt")) / n
    u.actual_ppg = (
        sum(score_stats(r, scoring) for r in rows) / n
        if p.pos in PTS_PER_TARGET or p.pos == "QB"
        else tot("pts_ppr") / n
    )
    u.opp_ppg = opportunity_ppg(p.pos, u.tgt_pg, u.carry_pg, u.rz_pg, tot("pass_att") / n)
    if p.pos not in PTS_PER_TARGET and p.pos != "QB":
        u.opp_ppg = u.actual_ppg  # K / DEF: no usage model, heat is zero
    return u


def rest_of_season_value(p: Player, u: Usage, done: int) -> float:
    pre_ppg = p.pre_value / p.expected_games if p.expected_games else 0.0
    w = min(INSEASON_MAX, INSEASON_RAMP * done) if u.games else 0.0
    u.weight = w
    ros_ppg = (1 - w) * pre_ppg + w * u.inseason_ppg
    remaining = (GAMES - done) * (1 - INJURY_WEIGHT * p.miss_rate)
    return round(ros_ppg * remaining, 1)


def attach_usage(
    api: Sleeper, pool: dict[str, Player], league: LeagueConfig, season: str, week: int
) -> int:
    """Rewrite every Player.value to a usage-blended rest-of-season number. Returns weeks used."""
    weeks = completed_weeks(api, season, week)
    for p in pool.values():
        p.pre_value = p.value
        p.usage = usage_from_weeks(p, weeks, league.scoring)
        p.value = rest_of_season_value(p, p.usage, len(weeks))
    return len(weeks)


def heat_lists(pool: dict[str, Player], min_games: int = 1) -> tuple[list[Player], list[Player]]:
    """(sell-high, buy-low): skill players whose scoring is far above / below their usage."""
    skill = [
        p
        for p in pool.values()
        if p.usage and p.usage.games >= min_games and p.pos in ("QB", "RB", "WR", "TE")
    ]
    hot = sorted((p for p in skill if p.usage.heat >= HEAT_FLAG), key=lambda p: -p.usage.heat)
    cold = sorted(
        (p for p in skill if p.usage.heat <= -HEAT_FLAG and p.usage.opp_ppg >= 8),
        key=lambda p: p.usage.heat,
    )
    return hot, cold
