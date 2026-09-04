"""Trade finder: surplus/deficit scan plus 1-for-1 and 2-for-1 swaps that help both lineups."""

from __future__ import annotations

from itertools import combinations

from bongo_boys.tools.common import SKILL, Context, fmt, load_context

MIN_MY_GAIN = 3.0
MAX_THEIR_LOSS = 4.0  # offers must be defensible: their lineup value drops by at most this
TOP_N = 9  # candidate players per side


def surplus_matrix(ctx: Context) -> dict[int, dict[str, int]]:
    """Startable players (value >= baseline) minus starting demand per position, per roster."""
    slots: dict[str, int] = {}
    for s in ctx.league.starter_slots:
        if s in SKILL:
            slots[s] = slots.get(s, 0) + 1
    out = {}
    for rid, r in ctx.rosters.items():
        ps = ctx.players_of(r)
        row = {}
        for pos in SKILL:
            startable = sum(1 for p in ps if p.pos == pos and p.value >= ctx.base.get(pos, 0))
            row[pos] = startable - slots.get(pos, 0)
        out[rid] = row
    return out


def find_trades(ctx: Context, partner: int | None = None) -> list[dict]:
    mine = ctx.players_of(ctx.my)
    my_val = ctx.team_value(mine)
    my_cands = sorted((p for p in mine if p.pos in SKILL), key=lambda p: -p.value)[:TOP_N]
    found = []
    for rid, r in ctx.rosters.items():
        if rid == ctx.my.roster_id or (partner is not None and rid != partner):
            continue
        theirs = ctx.players_of(r)
        their_val = ctx.team_value(theirs)
        their_cands = sorted((p for p in theirs if p.pos in SKILL), key=lambda p: -p.value)[:TOP_N]
        give_sets = [(a,) for a in my_cands] + list(combinations(my_cands, 2))
        get_sets = [(b,) for b in their_cands] + list(combinations(their_cands, 2))
        for give in give_sets:
            for get in get_sets:
                if len(give) == 2 and len(get) == 2:
                    continue
                gids = {p.id for p in give}
                tids = {p.id for p in get}
                new_mine = [p for p in mine if p.id not in gids] + list(get)
                new_theirs = [p for p in theirs if p.id not in tids] + list(give)
                dm = ctx.team_value(new_mine) - my_val
                dt = ctx.team_value(new_theirs) - their_val
                if dm >= MIN_MY_GAIN and dt >= -MAX_THEIR_LOSS:
                    found.append(
                        {"roster": r, "give": give, "get": get, "my_gain": dm, "their_gain": dt}
                    )
    found.sort(key=lambda t: -(t["my_gain"] + 0.5 * t["their_gain"]))
    return found


def report(ctx: Context | None = None, partner: str | None = None, top: int = 15) -> str:
    ctx = ctx or load_context()
    pid = None
    if partner:
        pid = next(
            (
                rid
                for rid, r in ctx.rosters.items()
                if r.owner_name.lower() == partner.lower() or str(rid) == partner
            ),
            None,
        )
    lines = [
        f"== Trade finder, week {ctx.week} (trade deadline week {ctx.league.settings.get('trade_deadline')}) =="
    ]
    lines.append("\n-- Surplus(+)/deficit(-) of startable players vs starting slots --")
    sm = surplus_matrix(ctx)
    lines.append(f"{'team':<20} " + " ".join(f"{p:>4}" for p in SKILL) + "  record")
    for rid, row in sm.items():
        r = ctx.rosters[rid]
        tag = " <- me" if rid == ctx.my.roster_id else ""
        lines.append(
            f"{r.owner_name:<20} "
            + " ".join(f"{row[p]:>+4}" for p in SKILL)
            + f"  {r.wins}-{r.losses}{tag}"
        )
    lines.append("\n-- Offers that raise my lineup value and stay defensible for them --")
    for t in find_trades(ctx, pid)[:top]:
        give = " + ".join(p.name for p in t["give"])
        get = " + ".join(p.name for p in t["get"])
        lines.append(
            f"  me +{t['my_gain']:5.1f} / them {t['their_gain']:+5.1f}  to {t['roster'].owner_name:<18} give {give}  for {get}"
        )
    lines.append("\n-- My roster --")
    for p in sorted(ctx.players_of(ctx.my), key=lambda p: -p.value):
        lines.append("   " + fmt(p, ctx.base))
    return "\n".join(lines)
