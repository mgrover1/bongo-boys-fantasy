"""Waiver wire: who is available, who upgrades my lineup, what is trending, who to drop."""

from __future__ import annotations

from bongo_boys.tools.common import SKILL, Context, fmt, load_context

FAAB_CLASS = [
    (0.20, "league-winner? verify role: 55-85% of remaining FAAB"),
    (0.0, "season-long starter: 15-30% of remaining FAAB"),
    (-0.15, "useful depth: 3-8% of remaining"),
    (-9.0, "stash/streamer: $0-1"),
]


def faab_hint(p, my_starters, base) -> str:
    worst = min((s.value for s in my_starters if s.pos == p.pos), default=0.0)
    rel = (p.value - worst) / max(worst, 1.0) if worst else 0.0
    if p.value <= base.get(p.pos, 0) * 0.8:
        return "stash/streamer: $0-1"
    for thr, txt in FAAB_CLASS:
        if rel >= thr:
            return txt
    return FAAB_CLASS[-1][1]


def report(ctx: Context | None = None, per_pos: int = 8) -> str:
    ctx = ctx or load_context()
    fa = ctx.free_agents()
    mine = ctx.players_of(ctx.my)
    my_starters = ctx.starters(mine)
    my_value = ctx.team_value(mine)
    lines = [
        f"== Free agents, week {ctx.week} | my lineup value {my_value:.0f} | FAAB left: see Sleeper =="
    ]
    lines.append(
        "\n-- Upgrades: free agents who raise my lineup value (swap for my weakest droppable) --"
    )
    droppable = sorted(
        (p for p in mine if p not in my_starters and p.pos in SKILL), key=lambda p: p.value
    )
    ups = []
    for p in fa[:150]:
        if p.pos not in SKILL:
            continue
        for d in droppable[:3]:
            gain = ctx.team_value([x for x in mine if x.id != d.id] + [p]) - my_value
            if gain > 2:
                ups.append((gain, p, d))
                break
    for gain, p, d in sorted(ups, key=lambda t: -t[0])[:12]:
        lines.append(
            f"  +{gain:5.1f}  {fmt(p, ctx.base)}   drop {d.name}   | {faab_hint(p, my_starters, ctx.base)}"
        )
    if not ups:
        lines.append("  none")
    lines.append("\n-- Best available by position --")
    for pos in ("QB", "RB", "WR", "TE", "K", "DEF"):
        lines.append(f"[{pos}]")
        for p in [x for x in fa if x.pos == pos][:per_pos]:
            lines.append("   " + fmt(p, ctx.base))
    lines.append("\n-- Trending adds (24h, league-wide on Sleeper) --")
    taken = ctx.rostered_ids()
    for t in ctx.api.trending("add", 24, 30):
        p = ctx.pool.get(t["player_id"])
        if p:
            lines.append(
                f"   {t['count']:>7,}  {fmt(p)}  {'(rostered here)' if p.id in taken else 'FREE'}"
            )
    lines.append("\n-- Trending drops --")
    for t in ctx.api.trending("drop", 24, 15):
        p = ctx.pool.get(t["player_id"])
        if p:
            lines.append(f"   {t['count']:>7,}  {fmt(p)}")
    lines.append("\n-- My drop candidates (lowest-value bench) --")
    for d in droppable[:5]:
        lines.append("   " + fmt(d, ctx.base))
    return "\n".join(lines)
