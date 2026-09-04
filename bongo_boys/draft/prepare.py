"""FIXED draft-simulation harness. Do not edit during autoresearch runs.

Defines the opponent model, the season-outcome sampler, the team-value metric, and
`evaluate()`. Strategies in `strategy.py` are scored against this file.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from bongo_boys.league import FLEX_ELIGIBLE, LeagueConfig, slot_of_pick
from bongo_boys.projections import Player

# --- fixed constants ----------------------------------------------------------
N_SIMS = 200
ADP_NOISE_BASE = 3.0  # picks of noise every opponent applies to ADP
ADP_NOISE_FRAC = 0.12  # plus this fraction of the ADP itself (late picks are chaotic)
UNDRAFTED_ADP_OFFSET = 180  # players with no ADP are ordered by search_rank after this
OPP_MAX_AT_POS = {"QB": 2, "RB": 7, "WR": 7, "TE": 2, "K": 1, "DEF": 1}
OPP_KDEF_EARLIEST_ROUND_FROM_END = 4  # opponents ignore K/DEF until the last 4 rounds
OPP_KDEF_FILL_ROUNDS_FROM_END = 2  # ... and fill a missing K/DEF in the last 2
OPP_NEED_BONUS = 12.0  # ADP picks shaved off a candidate that fills an empty starter slot
SEASON_SIGMA = {"QB": 0.20, "RB": 0.32, "WR": 0.30, "TE": 0.35, "K": 0.25, "DEF": 0.30}
INJURY_PRIOR_GAMES = 17  # shrink each player's miss rate toward the league average
INJURY_PRIOR_RATE = 0.12
BENCH_WEIGHT = 0.20  # season value credited for each of the best `BENCH_DEPTH` bench players
BENCH_DEPTH = 3
BASELINE_DEPTH_FUZZ = 0  # reserved


# --- baselines ------------------------------------------------------------------
def starter_demand(league: LeagueConfig, pool: dict[str, Player]) -> dict[str, int]:
    """How many players per position the league starts each week (flex share derived)."""
    slots = league.starter_slots
    dedicated: dict[str, int] = {}
    flex_slots: list[tuple[str, ...]] = []
    for s in slots:
        if s in FLEX_ELIGIBLE:
            flex_slots.append(FLEX_ELIGIBLE[s])
        else:
            dedicated[s] = dedicated.get(s, 0) + 1
    demand = {p: n * league.num_teams for p, n in dedicated.items()}
    by_pos: dict[str, list[Player]] = {}
    for p in pool.values():
        by_pos.setdefault(p.pos, []).append(p)
    for lst in by_pos.values():
        lst.sort(key=lambda x: -x.value)
    for eligible in flex_slots:
        cands = []
        for pos in eligible:
            cands.extend(by_pos.get(pos, [])[demand.get(pos, 0) :])
        cands.sort(key=lambda x: -x.value)
        for p in cands[: league.num_teams]:
            demand[p.pos] = demand.get(p.pos, 0) + 1
    return demand


def baselines(league: LeagueConfig, pool: dict[str, Player]) -> dict[str, float]:
    """Value of the last weekly starter at each position (VBD baseline)."""
    demand = starter_demand(league, pool)
    by_pos: dict[str, list[Player]] = {}
    for p in pool.values():
        by_pos.setdefault(p.pos, []).append(p)
    out = {}
    for pos, lst in by_pos.items():
        lst.sort(key=lambda x: -x.value)
        n = demand.get(pos, 0)
        out[pos] = lst[min(n, len(lst)) - 1].value if n and lst else 0.0
    return out


# --- season outcome sampler --------------------------------------------------------
def shrunk_miss_rate(p: Player) -> float:
    return (p.games_missed + INJURY_PRIOR_RATE * INJURY_PRIOR_GAMES) / (
        p.games_possible + INJURY_PRIOR_GAMES
    )


def sample_season(p: Player, rng: random.Random) -> float:
    """One plausible season total for `p`: injury-shrunk games x lognormal per-game output."""
    if p.value <= 0:
        return 0.0
    ppg = p.value / p.expected_games
    games = sum(1 for _ in range(17) if rng.random() > shrunk_miss_rate(p))
    sigma = SEASON_SIGMA.get(p.pos, 0.3)
    return ppg * games * math.exp(rng.gauss(-(sigma**2) / 2, sigma))


def lineup_value(players: list[Player], league: LeagueConfig, realized: dict[str, float]) -> float:
    """Best starting lineup by season totals plus a bench credit."""
    remaining = sorted(players, key=lambda p: -realized.get(p.id, 0.0))
    used: set[str] = set()
    total = 0.0
    slots = league.starter_slots
    # dedicated slots first, flex after
    for s in [s for s in slots if s not in FLEX_ELIGIBLE] + [
        s for s in slots if s in FLEX_ELIGIBLE
    ]:
        eligible = FLEX_ELIGIBLE.get(s, (s,))
        for p in remaining:
            if p.id not in used and p.pos in eligible:
                used.add(p.id)
                total += realized.get(p.id, 0.0)
                break
    bench = [
        realized.get(p.id, 0.0)
        for p in remaining
        if p.id not in used and p.pos in ("QB", "RB", "WR", "TE")
    ]
    total += BENCH_WEIGHT * sum(sorted(bench, reverse=True)[:BENCH_DEPTH])
    return total


# --- simulated draft ----------------------------------------------------------------
@dataclass
class PickContext:
    pick_no: int
    round: int
    rounds: int
    my_roster: list[Player]
    available: dict[str, Player]
    next_pick_no: int | None
    baselines: dict[str, float]
    league: LeagueConfig
    remaining_my_picks: list[int] = field(default_factory=list)

    @property
    def picks_until_next(self) -> int | None:
        return None if self.next_pick_no is None else self.next_pick_no - self.pick_no


def _effective_adp(p: Player) -> float:
    return p.adp if p.adp < 999 else UNDRAFTED_ADP_OFFSET + p.search_rank / 10


def opponent_pick(
    available: dict[str, Player],
    roster: list[Player],
    rnd: int,
    rounds: int,
    league: LeagueConfig,
    rng: random.Random,
) -> Player:
    counts: dict[str, int] = {}
    for p in roster:
        counts[p.pos] = counts.get(p.pos, 0) + 1
    limits = league.position_limits
    from_end = rounds - rnd + 1
    need_kdef = [pos for pos in ("K", "DEF") if counts.get(pos, 0) == 0]
    if from_end <= OPP_KDEF_FILL_ROUNDS_FROM_END and need_kdef:
        cands = [p for p in available.values() if p.pos in need_kdef]
        if cands:
            return max(cands, key=lambda p: p.value)
    starters_needed = {s: 0 for s in ("QB", "RB", "WR", "TE")}
    for s in league.starter_slots:
        if s in starters_needed:
            starters_needed[s] += 1
    best, best_score = None, float("inf")
    for p in available.values():
        c = counts.get(p.pos, 0)
        if c >= OPP_MAX_AT_POS.get(p.pos, 9) or c >= limits.get(p.pos, 99):
            continue
        if p.pos in ("K", "DEF") and from_end > OPP_KDEF_EARLIEST_ROUND_FROM_END:
            continue
        adp = _effective_adp(p)
        score = adp + rng.gauss(0, ADP_NOISE_BASE + ADP_NOISE_FRAC * adp)
        if c < starters_needed.get(p.pos, 0) and rnd > 2:
            score -= OPP_NEED_BONUS
        if score < best_score:
            best, best_score = p, score
    return best or next(iter(available.values()))


@dataclass
class DraftSetup:
    league: LeagueConfig
    pool: dict[str, Player]
    teams: int
    rounds: int
    my_roster_id: int
    pick_owner: dict[int, int]  # pick_no -> roster_id
    taken: dict[int, tuple[int, str]]  # pick_no -> (roster_id, player_id) already made (keepers)


def simulate_draft(setup: DraftSetup, strategy, rng: random.Random) -> dict[int, list[Player]]:
    rosters: dict[int, list[Player]] = {r: [] for r in set(setup.pick_owner.values())}
    available = {pid: p for pid, p in setup.pool.items()}
    for _pick_no, (rid, pid) in setup.taken.items():
        if pid in available:
            rosters.setdefault(rid, []).append(available.pop(pid))
    base = baselines(setup.league, setup.pool)
    my_picks = sorted(
        n for n, r in setup.pick_owner.items() if r == setup.my_roster_id and n not in setup.taken
    )
    total = setup.teams * setup.rounds
    for pick_no in range(1, total + 1):
        if pick_no in setup.taken:
            continue
        rid = setup.pick_owner[pick_no]
        rnd, _ = slot_of_pick(pick_no, setup.teams)
        if rid == setup.my_roster_id:
            future = [n for n in my_picks if n > pick_no]
            ctx = PickContext(
                pick_no=pick_no,
                round=rnd,
                rounds=setup.rounds,
                my_roster=rosters[rid],
                available=available,
                next_pick_no=future[0] if future else None,
                baselines=base,
                league=setup.league,
                remaining_my_picks=future,
            )
            choice = strategy(ctx)
            p = available.pop(choice)
        else:
            p = opponent_pick(available, rosters[rid], rnd, setup.rounds, setup.league, rng)
            available.pop(p.id)
        rosters[rid].append(p)
    return rosters


def evaluate(setup: DraftSetup, strategy, n_sims: int = N_SIMS, seed: int = 0) -> dict:
    scores, ranks = [], []
    sample_roster: list[Player] = []
    pick_counts: dict[str, int] = {}
    for i in range(n_sims):
        rng = random.Random(seed * 100_003 + i)
        rosters = simulate_draft(setup, strategy, rng)
        realized = {pid: sample_season(p, rng) for pid, p in setup.pool.items()}
        vals = {rid: lineup_value(ps, setup.league, realized) for rid, ps in rosters.items()}
        mine = vals[setup.my_roster_id]
        scores.append(mine)
        ranks.append(1 + sum(1 for v in vals.values() if v > mine))
        if i == 0:
            sample_roster = rosters[setup.my_roster_id]
        for p in rosters[setup.my_roster_id]:
            pick_counts[p.name] = pick_counts.get(p.name, 0) + 1
    mean = sum(scores) / len(scores)
    std = (sum((s - mean) ** 2 for s in scores) / max(1, len(scores) - 1)) ** 0.5
    return {
        "score": round(mean, 1),
        "score_std": round(std, 1),
        "mean_rank": round(sum(ranks) / len(ranks), 2),
        "p_top3": round(sum(1 for r in ranks if r <= 3) / len(ranks), 3),
        "n_sims": n_sims,
        "sample_roster": [p.label for p in sample_roster],
        "most_drafted": sorted(pick_counts.items(), key=lambda kv: -kv[1])[:15],
    }
