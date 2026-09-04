"""Export the value-ranked board as a rankings CSV (for draft-room tools and spreadsheets)."""

from __future__ import annotations

import csv
from pathlib import Path

from bongo_boys.draft.context import load_setup, tiers
from bongo_boys.draft.prepare import baselines


def export(path: str = "outputs/rankings.csv", limit: int = 320) -> str:
    league, pool, state, setup = load_setup(picks_ttl=300)
    base = baselines(league, pool)
    tier_of: dict[str, int] = {}
    for pos in ("QB", "RB", "WR", "TE", "K", "DEF"):
        ps = sorted([p for p in pool.values() if p.pos == pos], key=lambda x: -x.value)
        for p, t in zip(ps, tiers(ps), strict=False):
            tier_of[p.id] = t
    ranked = sorted(pool.values(), key=lambda p: -(p.value - base.get(p.pos, 0)))
    out = Path(path)
    out.parent.mkdir(exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Rank", "Player", "Position", "Team", "Tier", "Notes"])
        for i, p in enumerate(ranked[:limit], 1):
            note = (
                f"value {p.value:.0f}, VBD {p.value - base.get(p.pos, 0):+.0f}, ADP {p.adp:.0f}, "
                f"missed {p.miss_rate:.0%} of games 2023-25"
                + (f", {p.injury_status}" if p.injury_status else "")
            )
            w.writerow([i, p.name, p.pos, p.team or "FA", tier_of.get(p.id, ""), note])
    return str(out)
