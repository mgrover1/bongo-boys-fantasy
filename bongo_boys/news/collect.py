"""News and movement tracker.

Sources: RSS headlines (ESPN, RotoWire, CBS), Sleeper injury-status changes for players I
care about, and Sleeper trending adds/drops. Appends new items to `news/log.jsonl`.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

import requests

from bongo_boys.tools.common import Context, load_context

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "news" / "log.jsonl"
SNAPSHOT = ROOT / "news" / "injury_snapshot.json"
FEEDS = {
    "espn": "https://www.espn.com/espn/rss/nfl/news",
    "rotowire": "https://www.rotowire.com/rss/news.php?sport=NFL",
    "cbs": "https://www.cbssports.com/rss/headlines/nfl/",
}
WATCH_TOP = 150  # top players by value are always watched


def _load_log() -> list[dict]:
    if not LOG.exists():
        return []
    return [json.loads(line) for line in LOG.read_text().splitlines() if line.strip()]


def _append(items: list[dict]) -> None:
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a") as f:
        for it in items:
            f.write(json.dumps(it) + "\n")


def fetch_rss(name: str, url: str) -> list[dict]:
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "bongo-boys/0.1"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception as e:  # feed down: skip, don't crash
        return [{"source": name, "title": f"feed error: {e}", "link": url, "kind": "error"}]
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = re.sub(r"<[^>]+>", "", item.findtext("description") or "").strip()[:400]
        out.append(
            {
                "source": name,
                "title": title,
                "link": link,
                "summary": desc,
                "kind": "rss",
                "published": item.findtext("pubDate"),
            }
        )
    return out


def watched_players(ctx: Context) -> dict[str, str]:
    """player_id -> name for my roster plus the top of the pool."""
    names = {p: ctx.pool[p].name for p in ctx.my.players if p in ctx.pool}
    for p in sorted(ctx.pool.values(), key=lambda x: -x.value)[:WATCH_TOP]:
        names[p.id] = p.name
    return names


def injury_changes(ctx: Context, watched: dict[str, str]) -> list[dict]:
    meta = ctx.api.players()
    now = {pid: (meta.get(pid) or {}).get("injury_status") for pid in watched}
    prev = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else {}
    SNAPSHOT.parent.mkdir(exist_ok=True)
    SNAPSHOT.write_text(json.dumps(now))
    out = []
    for pid, status in now.items():
        if pid in prev and prev[pid] != status:
            m = meta.get(pid) or {}
            out.append(
                {
                    "source": "sleeper",
                    "kind": "injury",
                    "player_id": pid,
                    "title": f"{watched[pid]} ({m.get('team')}): {prev[pid]} -> {status}",
                    "summary": m.get("injury_notes") or m.get("injury_body_part") or "",
                    "link": "",
                }
            )
    return out


def run(show_all: bool = False, ctx: Context | None = None) -> str:
    ctx = ctx or load_context()
    watched = watched_players(ctx)
    mine = {ctx.pool[p].name for p in ctx.my.players if p in ctx.pool}
    seen = {(it.get("source"), it.get("title")) for it in _load_log()}
    fresh: list[dict] = []
    for name, url in FEEDS.items():
        fresh.extend(fetch_rss(name, url))
    fresh.extend(injury_changes(ctx, watched))
    for kind in ("add", "drop"):
        for t in ctx.api.trending(kind, 24, 10):
            p = ctx.pool.get(t["player_id"])
            if p:
                fresh.append(
                    {
                        "source": "sleeper",
                        "kind": f"trending_{kind}",
                        "player_id": p.id,
                        "title": f"{p.name} ({p.pos} {p.team}) trending {kind}: {t['count']:,}",
                        "link": "",
                        "summary": "",
                    }
                )
    stamp = datetime.now(UTC).isoformat()
    new = []
    for it in fresh:
        key = (it.get("source"), it.get("title"))
        if key in seen:
            continue
        seen.add(key)
        text = f"{it.get('title', '')} {it.get('summary', '')}"
        it["mentions"] = sorted({n for n in watched.values() if n and n in text})
        it["mine"] = sorted(mine & set(it["mentions"]))
        it["seen_at"] = stamp
        new.append(it)
    _append(new)
    lines = [f"== News refresh {stamp[:16]}Z: {len(new)} new items ({len(fresh)} fetched) =="]
    shown = [it for it in new if show_all or it["mine"] or it["kind"] != "rss" or it["mentions"]]
    for it in shown:
        tag = " ** MINE **" if it["mine"] else ""
        who = f" [{', '.join(it['mentions'][:4])}]" if it["mentions"] else ""
        lines.append(f"- ({it['source']}/{it['kind']}) {it['title']}{who}{tag}")
        if it.get("link"):
            lines.append(f"    {it['link']}")
    if not shown:
        lines.append("  nothing new for watched players")
    return "\n".join(lines)


def recent(hours: int = 48, only_mine: bool = False) -> list[dict]:
    cutoff = datetime.now(UTC).timestamp() - hours * 3600
    out = []
    for it in _load_log():
        try:
            ts = datetime.fromisoformat(it["seen_at"]).timestamp()
        except Exception:
            continue
        if ts >= cutoff and (it["mine"] if only_mine else (it["mentions"] or it["kind"] != "rss")):
            out.append(it)
    return out
