"""EDITABLE draft policy. The autoresearch loop mutates this file (or PARAMS) and keeps
whatever scores best under `prepare.evaluate`. Keep tunables in PARAMS."""

from __future__ import annotations

import math

from bongo_boys.draft.prepare import PickContext
from bongo_boys.projections import Player

PARAMS: dict[str, float] = {
    # VBD: score = value - baseline[pos]; then adjustments below
    "need_bonus": 25.0,  # added while a dedicated starter slot at that position is empty
    "flex_bonus": 8.0,  # added to RB/WR/TE while the FLEX slot is empty
    "depth_quota_rb": 5,  # roster targets; picks beyond these are discounted
    "depth_quota_wr": 5,
    "depth_quota_te": 2,
    "depth_quota_qb": 2,
    "surplus_penalty": 40.0,
    "bench_bonus": 10.0,  # added to RB/WR once their starter slots are filled  # subtracted once a position is at/over its quota
    "wait_discount": 0.55,  # multiply score if the player will very likely be there next pick
    "wait_margin": 6.0,  # "likely there" = adp > next_pick_no + wait_margin
    "kdef_rounds_from_end": 2,  # never draft K/DEF earlier than this
    "injury_penalty": 60.0,  # subtract miss_rate * this (on top of value already being adjusted)
    "rb_early_bonus": 6.0,  # small scarcity nudge for RB in rounds 1-4
    "qb_earliest_round": 5,
    "te_earliest_round": 3,
    # availability model: P(gone before my next pick) = sigmoid((next_pick - adp) / avail_sigma)
    "avail_sigma": 0.0,  # 0 -> use the hard wait_margin cutoff above
    "avail_strength": 0.6,  # score *= 1 - avail_strength * P(still available next pick)
    # tier cliff: bonus when p is the best left at his position and the drop to the next is big
    "cliff_gap": 0.0,  # 0 -> off; else gap (value points) that counts as a cliff
    "cliff_bonus": 15.0,
}

SKILL = ("QB", "RB", "WR", "TE")


def roster_counts(roster: list[Player]) -> dict[str, int]:
    c: dict[str, int] = {}
    for p in roster:
        c[p.pos] = c.get(p.pos, 0) + 1
    return c


def dedicated_slots(ctx: PickContext) -> dict[str, int]:
    d: dict[str, int] = {}
    for s in ctx.league.starter_slots:
        if s in SKILL or s in ("K", "DEF"):
            d[s] = d.get(s, 0) + 1
    return d


def pos_gaps(ctx: PickContext) -> dict[str, tuple[str, float]]:
    """Per position: (best available player id, value gap to the next best)."""
    best: dict[str, list[float]] = {}
    ids: dict[str, str] = {}
    for p in ctx.available.values():
        lst = best.setdefault(p.pos, [])
        if not lst or p.value > lst[0]:
            if lst:
                lst.insert(0, p.value)
            else:
                lst.append(p.value)
            ids[p.pos] = p.id
        elif len(lst) < 2 or p.value > lst[1]:
            lst.insert(1, p.value)
        del lst[2:]
    return {pos: (ids[pos], (v[0] - v[1]) if len(v) > 1 else 0.0) for pos, v in best.items()}


def p_available(p: Player, ctx: PickContext, params: dict[str, float]) -> float:
    if ctx.next_pick_no is None:
        return 0.0
    sigma = params.get("avail_sigma", 0.0)
    if sigma <= 0:
        return 1.0 if p.adp > ctx.next_pick_no + params["wait_margin"] else 0.0
    x = (p.adp - ctx.next_pick_no) / sigma
    x = max(-30.0, min(30.0, x))
    return 1.0 / (1.0 + math.exp(-x))


def score_player(
    p: Player,
    ctx: PickContext,
    params: dict[str, float],
    counts: dict[str, int] | None = None,
    gaps: dict[str, tuple[str, float]] | None = None,
) -> float:
    counts = counts if counts is not None else roster_counts(ctx.my_roster)
    slots = dedicated_slots(ctx)
    c = counts.get(p.pos, 0)
    limit = ctx.league.position_limits.get(p.pos)
    if limit and c >= limit:
        return -1e9
    from_end = ctx.rounds - ctx.round + 1
    if p.pos in ("K", "DEF"):
        if from_end > params["kdef_rounds_from_end"] or c >= 1:
            return -1e9
        return 1000.0 + (p.value - ctx.baselines.get(p.pos, 0))  # fill when allowed
    if p.pos == "QB" and ctx.round < params["qb_earliest_round"] and c == 0:
        return -1e8
    if p.pos == "TE" and ctx.round < params["te_earliest_round"] and c == 0:
        return -1e8
    s = p.value - ctx.baselines.get(p.pos, 0)
    if c < slots.get(p.pos, 0):
        s += params["need_bonus"]
    flex_filled = sum(max(0, counts.get(x, 0) - slots.get(x, 0)) for x in ("RB", "WR", "TE")) >= 1
    if p.pos in ("RB", "WR", "TE") and not flex_filled and c >= slots.get(p.pos, 0):
        s += params["flex_bonus"]
    quota = params.get(f"depth_quota_{p.pos.lower()}", 9)
    if c >= quota:
        if p.pos in ("QB", "TE"):
            return -1e8  # a 3rd QB / 2nd+ TE never starts; hard cap
        s -= params["surplus_penalty"]
    if p.pos in ("RB", "WR") and c >= slots.get(p.pos, 0):
        s += params["bench_bonus"]  # bench RB/WR cover injuries and byes
    if s > 0 and ctx.next_pick_no is not None:
        if params.get("avail_sigma", 0.0) > 0:
            s *= 1.0 - params["avail_strength"] * p_available(p, ctx, params)
        elif p.adp > ctx.next_pick_no + params["wait_margin"]:
            s *= params["wait_discount"]
    if params.get("cliff_gap", 0.0) > 0 and gaps is not None:
        best_id, gap = gaps.get(p.pos, ("", 0.0))
        if best_id == p.id and gap >= params["cliff_gap"]:
            s += params["cliff_bonus"]
    s -= params["injury_penalty"] * p.miss_rate
    if p.pos == "RB" and ctx.round <= 4:
        s += params["rb_early_bonus"]
    if p.injury_status in ("Out", "IR", "PUP", "Sus"):
        s -= 80.0
    return s


def rank_available(
    ctx: PickContext, params: dict[str, float] | None = None
) -> list[tuple[float, Player]]:
    params = params or PARAMS
    counts = roster_counts(ctx.my_roster)
    gaps = pos_gaps(ctx) if params.get("cliff_gap", 0.0) > 0 else None
    ranked = [(score_player(p, ctx, params, counts, gaps), p) for p in ctx.available.values()]
    ranked.sort(key=lambda t: -t[0])
    return ranked


def choose(ctx: PickContext, params: dict[str, float] | None = None) -> str:
    return rank_available(ctx, params)[0][1].id


class Strategy:
    """Picklable callable so evaluate() can fan out across processes."""

    def __init__(self, params: dict[str, float] | None = None):
        self.params = dict(params or PARAMS)

    def __call__(self, ctx: PickContext) -> str:
        return choose(ctx, self.params)


def make_strategy(params: dict[str, float]) -> Strategy:
    return Strategy(params)
