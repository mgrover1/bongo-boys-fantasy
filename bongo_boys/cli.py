"""`bongo` command line entry point."""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="bongo")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("draft").add_subparsers(dest="sub", required=True)
    lp = d.add_parser("loop", help="evaluate strategy / random search")
    lp.add_argument("--desc", default="")
    lp.add_argument("--search", type=int, default=0)
    lp.add_argument("--sims", type=int, default=0)
    lp.add_argument("--seed", type=int, default=0)
    lv = d.add_parser("live", help="live draft assistant")
    lv.add_argument("--once", action="store_true")
    lv.add_argument("--interval", type=int, default=15)
    bd = d.add_parser("board", help="tiered draft board (markdown)")
    bd.add_argument("--out", default="outputs/board.md")

    sub.add_parser("available", help="waiver wire / free agents")
    tr = sub.add_parser("trades", help="trade finder")
    tr.add_argument("--partner", default=None)
    br = sub.add_parser("briefing", help="daily/weekly status")
    br.add_argument("--week", type=int, default=0)
    nw = sub.add_parser("news", help="refresh news log")
    nw.add_argument("--all", action="store_true", help="show all, not just my players/watchlist")

    a = ap.parse_args(argv)
    if a.cmd == "draft" and a.sub == "loop":
        from bongo_boys.draft.loop import run

        run(desc=a.desc, search=a.search, n_sims=a.sims, seed=a.seed)
    elif a.cmd == "draft" and a.sub == "live":
        from bongo_boys.draft.live import report, watch

        print(report()) if a.once else watch(a.interval)
    elif a.cmd == "draft" and a.sub == "board":
        from pathlib import Path

        from bongo_boys.draft.board import board

        md = board()
        Path(a.out).write_text(md)
        print(md)
        print(f"\nwritten to {a.out}")
    elif a.cmd == "available":
        from bongo_boys.tools.available import report

        print(report())
    elif a.cmd == "trades":
        from bongo_boys.tools.trades import report

        print(report(partner=a.partner))
    elif a.cmd == "briefing":
        from bongo_boys.tools.briefing import report

        print(report(week=a.week))
    elif a.cmd == "news":
        from bongo_boys.news.collect import run

        print(run(show_all=a.all))


if __name__ == "__main__":
    main()
