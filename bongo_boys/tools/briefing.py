"""Daily / weekly briefing: what to do with my team right now."""

from __future__ import annotations

from datetime import UTC, datetime

from bongo_boys import DRAFT_ID, LEAGUE_ID, SEASON
from bongo_boys.league import FLEX_ELIGIBLE
from bongo_boys.news.collect import recent
from bongo_boys.tools.available import report as available_report
from bongo_boys.tools.common import Context, fmt, load_context
from bongo_boys.tools.trades import find_trades


def week_projections(ctx: Context, week: int) -> dict[str, dict]:
    out = {}
    for row in ctx.api.week_projections(SEASON, week):
        st = row.get("stats") or {}
        if st.get("pts_ppr") is None:
            continue
        out[row["player_id"]] = {
            "pts": float(st["pts_ppr"]),
            "opp": row.get("opponent"),
            "bye": row.get("game_id") is None,
        }
    return out


def best_weekly_lineup(
    ctx: Context, players, wk: dict[str, dict]
) -> list[tuple[str, object, float]]:
    remaining = sorted(players, key=lambda p: -wk.get(p.id, {}).get("pts", 0.0))
    used, out = set(), []
    slots = ctx.league.starter_slots
    for s in [s for s in slots if s not in FLEX_ELIGIBLE] + [
        s for s in slots if s in FLEX_ELIGIBLE
    ]:
        for p in remaining:
            if p.id not in used and p.pos in FLEX_ELIGIBLE.get(s, (s,)):
                used.add(p.id)
                out.append((s, p, wk.get(p.id, {}).get("pts", 0.0)))
                break
    return out


def report(week: int = 0, ctx: Context | None = None) -> str:
    ctx = ctx or load_context()
    week = week or ctx.week
    now = datetime.now(UTC)
    lines = [
        f"== Briefing {now:%Y-%m-%d %H:%MZ} | {ctx.league.name} | week {week} | league status {ctx.league.status} =="
    ]
    my = ctx.my
    mine = ctx.players_of(my)
    lines.append(
        f"Record {my.wins}-{my.losses}, points {my.fpts:.1f}. Roster {len(my.players)} players."
    )

    if ctx.league.status == "pre_draft":
        d = ctx.api.draft(DRAFT_ID)
        start = datetime.fromtimestamp(d["start_time"] / 1000, UTC)
        lines.append(
            f"\n** DRAFT {d['status']} — starts {start:%Y-%m-%d %H:%MZ} ({(start - now).total_seconds() / 3600:.1f} h from now). "
            f"Run `uv run bongo draft live` during the draft, `uv run bongo draft board` to prep. **"
        )

    lines.append("\n-- Injuries / status on my roster --")
    flagged = [p for p in mine if p.injury_status or p.status not in (None, "Active")]
    for p in flagged:
        lines.append(f"   {fmt(p)}  status={p.status}")
    if not flagged:
        lines.append("   all healthy per Sleeper")

    wk = week_projections(ctx, week)
    if wk:
        lines.append(f"\n-- Suggested lineup for week {week} (weekly projections, PPR) --")
        cur = set(my.starters)
        total = 0.0
        for slot, p, pts in best_weekly_lineup(ctx, mine, wk):
            info = wk.get(p.id, {})
            bye = " BYE" if info.get("bye") else ""
            flag = "" if p.id in cur or not cur else "  <- not currently starting"
            total += pts
            lines.append(
                f"   {slot:<5} {p.name:<24} {pts:5.1f} vs {info.get('opp') or '-':<4}{bye}{flag}"
            )
        lines.append(f"   projected total {total:.1f}")
        bench = [
            p for p in mine if p.id not in {x[1].id for x in best_weekly_lineup(ctx, mine, wk)}
        ]
        byes = [p.name for p in mine if wk.get(p.id, {}).get("bye")]
        if byes:
            lines.append("   on bye: " + ", ".join(byes))
        lines.append(
            "   bench: "
            + ", ".join(f"{p.name} {wk.get(p.id, {}).get('pts', 0):.1f}" for p in bench)
        )

    lines.append("\n-- Waiver targets (top upgrades) --")
    av = available_report(ctx)
    sect = av.split("-- Upgrades")[1].split("-- Best available")[0].strip().splitlines()[1:6]
    lines.extend("   " + s.strip() for s in sect)
    lines.append(
        f"   waivers clear on Sleeper day-of-week {ctx.league.settings.get('waiver_day_of_week')} (2=Wed); FAAB budget {ctx.league.settings.get('waiver_budget')}"
    )

    lines.append("\n-- Trade ideas --")
    for t in find_trades(ctx)[:5]:
        give = " + ".join(p.name for p in t["give"])
        get = " + ".join(p.name for p in t["get"])
        lines.append(
            f"   me +{t['my_gain']:.1f}/them {t['their_gain']:+.1f}: give {give} to {t['roster'].owner_name} for {get}"
        )
    dl = ctx.league.settings.get("trade_deadline")
    if dl and week > int(dl):
        lines.append("   (trade deadline passed)")

    lines.append("\n-- League activity this week --")
    try:
        tx = ctx.api.transactions(LEAGUE_ID, week)
    except Exception:
        tx = []
    names = {r.roster_id: r.owner_name for r in ctx.rosters.values()}
    for t in tx[:12]:
        adds = ", ".join(ctx.pool[p].name if p in ctx.pool else p for p in (t.get("adds") or {}))
        drops = ", ".join(ctx.pool[p].name if p in ctx.pool else p for p in (t.get("drops") or {}))
        who = ", ".join(names.get(r, str(r)) for r in (t.get("roster_ids") or []))
        lines.append(f"   {t['type']:<12} {t['status']:<9} {who}: +[{adds}] -[{drops}]")
    if not tx:
        lines.append("   none")

    lines.append("\n-- News for my players (last 48h; run `bongo news` to refresh) --")
    items = recent(48, only_mine=True)
    for it in items[:10]:
        lines.append(f"   ({it['source']}) {it['title']}")
    if not items:
        lines.append("   nothing logged")

    lines.append("\n-- To do --")
    todo = []
    if ctx.league.status == "pre_draft":
        todo.append("prep the board and be at the draft with `bongo draft live` running")
    if any(p.injury_status in ("Out", "IR", "Doubtful") for p in mine):
        todo.append("move Out/IR players to IR slot or bench; check waiver upgrades above")
    if wk and any(wk.get(p.id, {}).get("bye") for p in ctx.starters(mine)):
        todo.append("a projected starter is on bye: fix the lineup")
    if not todo:
        todo.append("no urgent moves; set lineup before Thursday kickoff")
    lines.extend(f"   [ ] {t}" for t in todo)
    return "\n".join(lines)
