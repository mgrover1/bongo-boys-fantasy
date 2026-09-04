"""Live draft assistant: polls Sleeper picks and prints recommendations for my next pick."""

from __future__ import annotations

import random
import time

from bongo_boys.draft.context import load_params, load_setup, tiers
from bongo_boys.draft.prepare import PickContext, baselines, opponent_pick
from bongo_boys.draft.strategy import rank_available
from bongo_boys.league import slot_of_pick
from bongo_boys.projections import Player


def _fmt(p: Player, base: dict[str, float], tier: int | None = None) -> str:
    inj = f" [{p.injury_status}]" if p.injury_status else ""
    t = f" T{tier}" if tier else ""
    return (
        f"{p.name:<24} {p.pos:<3} {p.team or 'FA':<4} val {p.value:6.1f} vbd {p.value - base.get(p.pos, 0):6.1f}"
        f" adp {p.adp:6.1f} miss {p.miss_rate:.0%}{t}{inj}"
    )


def report(top: int = 12) -> str:
    league, pool, state, setup = load_setup(picks_ttl=0)
    base = baselines(league, pool)
    params = load_params()
    drafted = state.drafted_player_ids()
    available = {pid: p for pid, p in pool.items() if pid not in drafted}
    mine = [pool[pid] for pid in state.roster_players(state.my_roster_id) if pid in pool]
    my_picks = state.remaining_picks_for(state.my_roster_id)
    nxt = state.next_pick_no()
    lines = [
        f"== {league.name} | draft {state.status} | picks made {len(state.picks)}/{state.teams * state.rounds}"
    ]
    if nxt is None:
        lines.append("Draft complete.")
        lines.append("My roster: " + ", ".join(p.label for p in mine))
        return "\n".join(lines)
    rnd, slot = slot_of_pick(nxt, state.teams)
    on_clock = state.owner_of_pick_no(nxt)
    my_next = my_picks[0] if my_picks else None
    after = [n for n in my_picks if my_next is not None and n > my_next]
    lines.append(
        f"On the clock: pick {nxt} (R{rnd}.{slot}) roster {on_clock}{'  <-- ME' if on_clock == state.my_roster_id else ''}"
    )
    lines.append(
        f"My next pick: {my_next}  (then {after[:2]})  picks until mine: {(my_next or nxt) - nxt}"
    )
    lines.append(
        "My roster: " + (", ".join(f"{p.name} ({p.pos})" for p in mine) or "(keepers only)")
    )
    if my_next is None:
        return "\n".join(lines)
    ctx = PickContext(
        pick_no=my_next,
        round=slot_of_pick(my_next, state.teams)[0],
        rounds=state.rounds,
        my_roster=mine,
        available=available,
        next_pick_no=after[0] if after else None,
        baselines=base,
        league=league,
        remaining_my_picks=after,
    )
    avail_prob = availability(state, pool, available, league, nxt, my_next)
    ranked = rank_available(ctx, params)
    tier_of: dict[str, int] = {}
    for pos in ("QB", "RB", "WR", "TE"):
        ps = sorted([p for p in available.values() if p.pos == pos], key=lambda x: -x.value)
        for p, t in zip(ps, tiers(ps), strict=False):
            tier_of[p.id] = t
    lines.append(
        f"\n-- Strategy picks for pick {my_next} (gap to following pick: {ctx.picks_until_next}) --"
    )
    shown = 0
    for s, p in ranked:
        pa = avail_prob.get(p.id, 1.0)
        if pa < 0.15:
            continue
        lines.append(f"{s:7.1f}  P(avail) {pa:4.0%}  {_fmt(p, base, tier_of.get(p.id))}")
        shown += 1
        if shown >= top:
            break
    lines.append("\n-- Likely gone before my pick (top strategy scores, P(avail) < 50%) --")
    for s, p in ranked[:25]:
        pa = avail_prob.get(p.id, 1.0)
        if pa < 0.5:
            lines.append(f"{s:7.1f}  P(avail) {pa:4.0%}  {_fmt(p, base, tier_of.get(p.id))}")
    lines.append("\n-- Value alerts (ADP a round+ earlier than current pick) --")
    for p in sorted(available.values(), key=lambda x: x.adp):
        if p.adp < nxt - state.teams and p.pos in ("QB", "RB", "WR", "TE"):
            lines.append("   " + _fmt(p, base, tier_of.get(p.id)))
    lines.append("\n-- Best available by position (value) --")
    for pos in ("QB", "RB", "WR", "TE", "K", "DEF"):
        ps = sorted([p for p in available.values() if p.pos == pos], key=lambda x: -x.value)[:5]
        lines.append(f"{pos}: " + " | ".join(f"{p.name} {p.value:.0f}" for p in ps))
    return "\n".join(lines)


def availability(
    state, pool, available, league, from_pick: int, my_pick: int, n: int = 150
) -> dict[str, float]:
    """P(player still available at my_pick) from rollouts of the opponent model."""
    if my_pick <= from_pick:
        return {pid: 1.0 for pid in available}
    counts = {pid: 0 for pid in available}
    rosters = {
        rid: [pool[x] for x in state.roster_players(rid) if x in pool]
        for rid in state.slot_to_roster.values()
    }
    for i in range(n):
        rng = random.Random(i)
        avail = dict(available)
        rs = {rid: list(ps) for rid, ps in rosters.items()}
        for pick_no in range(from_pick, my_pick):
            rid = state.owner_of_pick_no(pick_no)
            if rid == state.my_roster_id:
                continue
            rnd, _ = slot_of_pick(pick_no, state.teams)
            p = opponent_pick(avail, rs[rid], rnd, state.rounds, league, rng)
            avail.pop(p.id)
            rs[rid].append(p)
        for pid in avail:
            counts[pid] += 1
    return {pid: c / n for pid, c in counts.items()}


def watch(interval: int = 15) -> None:
    last = None
    while True:
        try:
            out = report()
        except Exception as e:  # network hiccup: keep polling
            out = f"error: {e}"
        if out != last:
            print("\033[2J\033[H" + time.strftime("%H:%M:%S"))
            print(out)
            last = out
        time.sleep(interval)
