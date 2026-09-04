# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

Tooling to win the "Bongo Bingo Bongo - remastered" Sleeper fantasy football league (2026 season). Three workstreams:

1. **Draft optimizer** — an autoresearch-style loop (modeled on `~/git_repos/autoresearch-mlx`) that iterates on a draft strategy and keeps the version that scores best in simulated drafts.
2. **In-season tools** — CLI commands for waiver-wire availability, trade evaluation, and a daily/weekly "what should I do" briefing.
3. **News tracker** — collect injuries, depth-chart moves, and transactions that affect my roster or the waiver pool.

The user's global `~/.claude/CLAUDE.md` applies: Python + `uv`, ruff, pytest, plain-language communication, no pushes without confirmation.

## Fixed league facts (verified against the Sleeper API, 2026-09-04)

| Fact | Value |
|-|-|
| User | `mgroverwx`, user_id `858419887591243776`, **roster_id 5** |
| League id | `1365790508172992512` (12 teams, snake, PPR) |
| Draft id | `1365790508181377024`, starts 2026-09-05 00:15 UTC (Sep 4 evening US) |
| My draft slot | **11 of 12** (`slot_to_roster_id["11"] == 5`) |
| Rounds | 15, 60-second pick timer, CPU autopick on, position limit QB=3 |
| Starters | QB, RB, RB, WR, WR, TE, FLEX, K, DEF + 6 BN + 2 IR |
| Scoring | Full PPR (rec 1.0), pass TD 4, pass yd 0.04, rush/rec yd 0.1, fum lost -2, int -1; K and DEF scored |
| Keepers | Max 2 per team; keepers appear as `is_keeper: true` picks and **consume that round's pick**. Mine: DeVonta Smith (`7525`, R5 pick 59) and De'Von Achane (`9226`, R1 pick 11) |
| Traded picks | None involve me (roster 5). I hold all 13 non-keeper picks: 14, 35, 38, 62, 83, 86, 107, 110, 131, 134, 155, 158, 179 |
| Season | Week 1 starts 2026-09-09; trade deadline week 11; playoffs week 15, 6 teams; waivers FAAB $100, clear Wednesdays |

Full raw snapshots for the draft session live in the session scratchpad; regenerate them with the API calls below rather than trusting stale copies.

## Sleeper API (read-only, no auth, no key)

Base `https://api.sleeper.app/v1`. All endpoints are plain GET returning JSON.

```
/user/mgroverwx                          -> user_id
/user/<user_id>/leagues/nfl/2026         -> leagues
/league/<league_id>                      -> settings, scoring_settings, roster_positions
/league/<league_id>/rosters              -> per-roster players, starters, keepers, owner_id
/league/<league_id>/users                -> owner display names
/league/<league_id>/drafts               -> draft ids
/league/<league_id>/transactions/<week>  -> adds/drops/trades/waivers
/league/<league_id>/matchups/<week>
/draft/<draft_id>                        -> draft_order, slot_to_roster_id, settings
/draft/<draft_id>/picks                  -> picks so far (keepers pre-populated)
/draft/<draft_id>/traded_picks
/players/nfl                             -> ~12k players, ~15 MB; cache to disk, refresh at most daily
/players/nfl/trending/add?lookback_hours=24&limit=25   -> waiver heat
/state/nfl                               -> current week/season
```

Player ids are strings (`"7525"`); team defenses use the team abbreviation (`"BAL"`). `players/nfl` entries carry `full_name`, `position`, `fantasy_positions`, `team`, `age`, `injury_status`, `status`, `search_rank` (Sleeper's overall rank, useful as an ADP proxy). Sleeper rate-limits around 1000 calls/minute; never poll `players/nfl` in a loop.

Sleeper has no write API. Draft picks and waiver claims are made by hand in the app; tools here produce recommendations.

## Layout

```
bongo_boys/
  sleeper.py           read-only API client, disk cache in ~/.cache/bongo-boys (BONGO_CACHE)
  league.py            LeagueConfig, Roster, DraftState (snake math, traded picks, keepers)
  projections.py       Player pool: Rotowire season projections re-scored with league scoring,
                       Sleeper PPR ADP, 2023-25 stats, injury history -> `value`
  draft/
    prepare.py         FIXED sim harness: opponent model, season sampler, lineup metric, evaluate()
    strategy.py        EDITABLE policy (VBD + needs + wait discount); PARAMS dict is tunable
    loop.py            evaluate/log/keep-best; --search N random-perturbs PARAMS
    live.py            live assistant: polls picks, P(available at my pick), tiers, alerts
    board.py           tiered markdown board
    context.py         load_setup() from live Sleeper state; best-params loader; tiers()
    program.md         instructions for the agent-driven improvement loop
  tools/
    common.py          Context loader shared by in-season tools
    available.py       free agents, lineup upgrades, FAAB class hint, trending, drop candidates
    trades.py          surplus/deficit matrix, 1-for-1 and 2-for-1 offers good for both lineups
    briefing.py        daily/weekly: injuries, weekly lineup, waivers, trades, activity, news, todo
  news/collect.py      RSS (ESPN, RotoWire, CBS) + Sleeper injury diffs + trending -> news/log.jsonl
outputs/               results.tsv, best_strategy.json (committed); board.md, logs (ignored)
```

## Commands

```bash
uv sync
uv run bongo draft board                 # tiered board -> outputs/board.md
uv run bongo draft live [--once]         # live draft assistant (polls every 15 s)
uv run bongo draft loop --desc "..."     # evaluate current strategy.py, log, keep if best
uv run bongo draft loop --search 30      # random search over PARAMS (~20 s per iteration)
uv run bongo available                   # waiver wire report
uv run bongo trades [--partner NAME]     # trade finder
uv run bongo briefing [--week N]         # what to do today / this week
uv run bongo news [--all]                # refresh news log; prints items about watched players
uv run pytest -q                         # tests/test_league.py::test_snake_pick_numbers for one
uv run ruff format . && uv run ruff check .
```

Everything reads live Sleeper state. Cached responses have per-endpoint TTLs; delete
`~/.cache/bongo-boys` to force a refresh. `BEST_PARAMS` (`outputs/best_strategy.json`) overrides
`strategy.PARAMS` when present, so `live` and `board` use the best searched parameters.

## Valuation

`Player.value` = blended per-game points x expected games. Blend = 70% projection + 30% last
season's per-game output (if >= 6 games). Expected games = 17 x (1 - 0.6 x miss rate over
2023-25). The sim harness additionally samples games from a shrunk miss rate and lognormal
per-game noise, so injury-prone players are penalised twice: in value and in variance.

## Autoresearch protocol (adapted from autoresearch-mlx)

- `draft/prepare.py` defines the ground truth: simulated snake drafts from slot 11 with keepers and traded picks loaded, opponents picking by ADP with calibrated noise, and the metric = sampled season lineup value (starters + 0.2 x top-3 bench). Do not edit it inside the loop; changing it invalidates results.tsv, so reset best_strategy.json when you do.
- `draft/strategy.py` is the only file the loop mutates. Keep tunables in PARAMS. `evaluate()` runs sims across all cores (BONGO_WORKERS=1 for serial); never edit strategy.py while a search is running, worker processes re-import it.
- Each iteration appends a row to `outputs/results.tsv`: `commit score score_std mean_rank p_top3 n_sims status description`. Keep the change if `score` improves; otherwise revert.
- Prefer simpler strategies when scores are within one standard deviation.
- Reality check every strategy against the real `/picks` feed: keepers already remove 24 players from the pool.

## Mock drafts (Sleeper, via Chrome)

Sleeper's "Mock Drafts" button on the league predraft page creates a private CPU mock with the
league's keepers and my slot. The mock has its own draft id, readable from the same API:

```bash
BONGO_DRAFT_ID=<mock id> BONGO_MY_ROSTER_ID=<my slot> uv run bongo draft live
```

Lessons from the 2026-09-04 mock (id 1401637665899618304): CPU opponents pick within about
5 picks of Sleeper ADP (sd 5.5) and shift ~5 picks early because keepers thin the pool; first
DEF went at pick 87. CPU picks arrive every few seconds, so the clock is the constraint: keep
`bongo draft live` (watch mode) running so the recommendation is on screen before my clock
starts. Auto-pick fires when the 60 s timer expires, in mocks and in the real draft.
