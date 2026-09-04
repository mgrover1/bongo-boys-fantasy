"""Pre-draft tiered board (markdown) for this league's scoring and roster."""

from __future__ import annotations

from bongo_boys.draft.context import load_setup, tiers
from bongo_boys.draft.prepare import baselines, starter_demand


def board(per_pos: int = 36) -> str:
    league, pool, state, setup = load_setup(picks_ttl=300)
    base = baselines(league, pool)
    demand = starter_demand(league, pool)
    drafted = state.drafted_player_ids()
    out = [f"# Draft board: {league.name} (slot {state.my_slot} of {state.teams})", ""]
    out.append(
        "Baselines (last weekly starter): "
        + ", ".join(f"{k} {v:.0f} (n={demand.get(k, 0)})" for k, v in sorted(base.items()))
    )
    out.append(f"My remaining picks: {state.remaining_picks_for(state.my_roster_id)}")
    out.append("")
    for pos in ("RB", "WR", "TE", "QB", "K", "DEF"):
        ps = sorted([p for p in pool.values() if p.pos == pos], key=lambda x: -x.value)[:per_pos]
        ts = tiers(ps)
        out.append(f"## {pos}\n")
        out.append("|Tier|Player|Team|Value|VBD|ADP|Proj|'25 ppg|Miss%|Status|")
        out.append("|-|-|-|-|-|-|-|-|-|-|")
        for p, t in zip(ps, ts, strict=False):
            st = "KEPT" if p.id in drafted else (p.injury_status or "")
            prior = f"{p.prior_ppg:.1f}" if p.prior_ppg else "-"
            out.append(
                f"|{t}|{p.name}|{p.team or 'FA'}|{p.value:.0f}|{p.value - base.get(pos, 0):+.0f}|{p.adp:.0f}|{p.proj_pts:.0f}|{prior}|{p.miss_rate:.0%}|{st}|"
            )
        out.append("")
    return "\n".join(out)
