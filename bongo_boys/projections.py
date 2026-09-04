"""Player pool: projections scored in this league, prior-season form, injury history."""

from __future__ import annotations

from dataclasses import dataclass, field

from bongo_boys.league import LeagueConfig
from bongo_boys.sleeper import Sleeper

GAMES = 17
PRIOR_SEASONS = 3
# Positions whose projection components are complete enough to re-score with league rules.
RESCORE_POSITIONS = {"QB", "RB", "WR", "TE"}
# Default blend: how much to trust last season's per-game output vs the projection.
PRIOR_WEIGHT = 0.30
# Weight of ESPN's season projection when blending with Rotowire (via Sleeper).
ESPN_WEIGHT = 0.5
# How much of a player's historical missed-game rate to apply to expected games.
INJURY_WEIGHT = 0.6
MIN_PRIOR_GAMES = 6


@dataclass
class Player:
    id: str
    name: str
    pos: str
    team: str | None
    proj_pts: float = 0.0  # full-season projection in league scoring
    adp: float = 999.0  # Sleeper PPR ADP (overall pick number)
    search_rank: int = 9999
    injury_status: str | None = None
    status: str | None = None
    age: int | None = None
    years_exp: int | None = None
    prior: dict[str, dict] = field(default_factory=dict)  # season -> {gp, pts, ppg, rank}
    prior_ppg: float | None = None  # last season, if enough games
    proj_sources: dict[str, float] = field(default_factory=dict)  # rotowire / espn season points
    games_missed: int = 0
    games_possible: int = 0
    value: float = 0.0  # injury-adjusted, prior-blended season points (the number tools rank on)

    @property
    def proj_ppg(self) -> float:
        return self.proj_pts / GAMES if self.proj_pts else 0.0

    @property
    def miss_rate(self) -> float:
        return self.games_missed / self.games_possible if self.games_possible else 0.0

    @property
    def expected_games(self) -> float:
        return GAMES * (1 - INJURY_WEIGHT * self.miss_rate)

    @property
    def label(self) -> str:
        return f"{self.name} ({self.pos} {self.team or 'FA'})"


def score_stats(stats: dict, scoring: dict[str, float]) -> float:
    return sum(float(stats.get(k, 0) or 0) * w for k, w in scoring.items())


def blended_value(p: Player) -> float:
    ppg = p.proj_ppg
    if p.prior_ppg is not None and ppg > 0:
        ppg = (1 - PRIOR_WEIGHT) * ppg + PRIOR_WEIGHT * p.prior_ppg
    return round(ppg * p.expected_games, 1)


def build_pool(api: Sleeper, league: LeagueConfig, season: str) -> dict[str, Player]:
    """Every projected player, keyed by Sleeper id. Includes team defenses (id = team abbr)."""
    meta = api.players()
    pool: dict[str, Player] = {}
    for row in api.season_projections(season):
        st = row.get("stats") or {}
        pid = row["player_id"]
        info = row.get("player") or {}
        pos = info.get("position") or (meta.get(pid) or {}).get("position")
        if pos not in RESCORE_POSITIONS and pos not in {"K", "DEF"}:
            continue
        pts_ppr = float(st.get("pts_ppr") or 0)
        if not pts_ppr:
            continue
        proj = score_stats(st, league.scoring) if pos in RESCORE_POSITIONS else pts_ppr
        m = meta.get(pid) or {}
        name = (
            m.get("full_name")
            or f"{info.get('first_name', '')} {info.get('last_name', '')}".strip()
        )
        pool[pid] = Player(
            id=pid,
            name=name,
            pos=pos,
            team=row.get("team") or m.get("team"),
            proj_pts=round(proj, 1),
            adp=float(st.get("adp_ppr") or 999),
            search_rank=m.get("search_rank") or 9999,
            injury_status=m.get("injury_status"),
            status=m.get("status"),
            age=m.get("age"),
            years_exp=m.get("years_exp"),
        )
    _blend_espn(api, pool, meta, season)
    _attach_history(api, pool, league, season)
    for p in pool.values():
        p.value = blended_value(p)
    return pool


def _blend_espn(api: Sleeper, pool: dict[str, Player], meta: dict, season: str) -> None:
    """Average Rotowire and ESPN season projections where both exist (QB/RB/WR/TE only)."""
    try:
        espn = api.espn_projections(season)
    except Exception:  # ESPN down: keep single-source projections
        return
    by_name = {(_norm(v["name"]), v["pos"]): v["pts"] for v in espn.values()}
    for p in pool.values():
        p.proj_sources["rotowire"] = p.proj_pts
        eid = (meta.get(p.id) or {}).get("espn_id")
        e = (
            espn[str(eid)]["pts"]
            if eid and str(eid) in espn
            else by_name.get((_norm(p.name), p.pos))
        )
        if e and p.pos in RESCORE_POSITIONS:
            p.proj_sources["espn"] = round(e, 1)
            p.proj_pts = round((1 - ESPN_WEIGHT) * p.proj_pts + ESPN_WEIGHT * e, 1)


def _norm(name: str) -> str:
    n = name.lower().replace(".", "").replace("'", "").replace("-", " ")
    for suf in (" jr", " sr", " ii", " iii", " iv"):
        if n.endswith(suf):
            n = n[: -len(suf)]
    return " ".join(n.split())


def _attach_history(
    api: Sleeper, pool: dict[str, Player], league: LeagueConfig, season: str
) -> None:
    last = str(int(season) - 1)
    for back in range(1, PRIOR_SEASONS + 1):
        yr = str(int(season) - back)
        for row in api.season_stats(yr):
            p = pool.get(row["player_id"])
            st = row.get("stats") or {}
            if p is None or not st.get("gp"):
                continue
            gp = int(st["gp"])
            pts = (
                score_stats(st, league.scoring)
                if p.pos in RESCORE_POSITIONS
                else float(st.get("pts_ppr") or 0)
            )
            p.prior[yr] = {
                "gp": gp,
                "pts": round(pts, 1),
                "ppg": round(pts / gp, 2),
                "rank": st.get("pos_rank_ppr"),
            }
            if p.pos != "DEF":
                p.games_possible += GAMES
                p.games_missed += max(0, GAMES - gp)
            if yr == last and gp >= MIN_PRIOR_GAMES:
                p.prior_ppg = pts / gp


def by_position(
    pool: dict[str, Player], available: set[str] | None = None
) -> dict[str, list[Player]]:
    out: dict[str, list[Player]] = {}
    for p in pool.values():
        if available is not None and p.id not in available:
            continue
        out.setdefault(p.pos, []).append(p)
    for lst in out.values():
        lst.sort(key=lambda x: -x.value)
    return out
