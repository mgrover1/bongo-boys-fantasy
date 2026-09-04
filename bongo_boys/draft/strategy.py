"""EDITABLE draft policy. The autoresearch loop mutates this file (or PARAMS) and keeps
whatever scores best under `prepare.evaluate`. Keep tunables in PARAMS."""

from __future__ import annotations

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
    "surplus_penalty": 40.0,  # subtracted once a position is at/over its quota
    "wait_discount": 0.55,  # multiply score if the player will very likely be there next pick
    "wait_margin": 6.0,  # "likely there" = adp > next_pick_no + wait_margin
    "kdef_rounds_from_end": 2,  # never draft K/DEF earlier than this
    "injury_penalty": 60.0,  # subtract miss_rate * this (on top of value already being adjusted)
    "rb_early_bonus": 6.0,  # small scarcity nudge for RB in rounds 1-4
    "qb_earliest_round": 5,
    "te_earliest_round": 3,
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


def score_player(p: Player, ctx: PickContext, params: dict[str, float]) -> float:
    counts = roster_counts(ctx.my_roster)
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
        s -= params["surplus_penalty"]
    if ctx.next_pick_no is not None and p.adp > ctx.next_pick_no + params["wait_margin"]:
        s *= params["wait_discount"] if s > 0 else 1.0
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
    ranked = [(score_player(p, ctx, params), p) for p in ctx.available.values()]
    ranked.sort(key=lambda t: -t[0])
    return ranked


def choose(ctx: PickContext, params: dict[str, float] | None = None) -> str:
    return rank_available(ctx, params)[0][1].id


def make_strategy(params: dict[str, float]):
    def _s(ctx: PickContext) -> str:
        return choose(ctx, params)

    return _s
