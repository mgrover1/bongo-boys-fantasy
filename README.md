# bongo-boys-fantasy

Draft optimizer and in-season tools for the **Bongo Bingo Bongo - remastered** Sleeper league.
Everything reads Sleeper's public API (no login, no key) and prints recommendations. Nothing
here makes picks or claims for you; you still click in the Sleeper app.

## Setup

Needs Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone git@github.com:mgrover1/bongo-boys-fantasy.git
cd bongo-boys-fantasy
uv sync
```

Tell it who you are (defaults to mgroverwx if you set nothing):

```bash
export BONGO_USERNAME=<your sleeper username>
```

It looks up your roster and the league's draft from that. Optional overrides:
`BONGO_LEAGUE_ID`, `BONGO_DRAFT_ID`, `BONGO_MY_ROSTER_ID`.

API responses are cached under `~/.cache/bongo-boys` (players daily, projections 6 h,
picks never). Delete that folder to force a refresh.

## Draft day

```bash
uv run bongo draft board          # tiered board for our scoring, written to outputs/board.md
uv run bongo draft live           # live assistant: refreshes every 15 s
uv run bongo draft live --once    # one snapshot
```

The live view shows, for **your next pick**: the strategy's ranked picks with the probability
each player is still there (from rollouts of an ADP-based opponent model), tier labels,
injury flags, value alerts (players a round+ past ADP), and best available by position.
Keep it running before your clock starts; auto-pick fires when the 60 s timer expires.

### Practice on a mock

On the league's predraft page click **Mock Drafts** and start a CPU mock. Copy the draft id
from the URL (`sleeper.com/draft/nfl/<id>`) and your slot number:

```bash
BONGO_DRAFT_ID=<mock id> BONGO_MY_ROSTER_ID=<slot> uv run bongo draft live
```

## During the season

```bash
uv run bongo briefing             # what to do today: injuries, lineup, waivers, trades, news, to-dos
uv run bongo available            # free agents that upgrade your lineup, FAAB class hints, trending adds/drops
uv run bongo trades               # surplus/deficit matrix and offers that help both lineups
uv run bongo trades --partner <display name>
uv run bongo news                 # pull ESPN/RotoWire/CBS headlines + Sleeper injury changes for watched players
```

`briefing` is designed to be run every morning. Lineup suggestions use Sleeper's weekly
projections; trade and waiver suggestions use season values.

## How players are valued

`value` = blended points per game x expected games.

- Points come from Rotowire season projections (via Sleeper) re-scored with **this league's**
  scoring, blended 70/30 with last season's per-game output when the player played 6+ games.
- Expected games = 17 x (1 - 0.6 x share of games missed over 2023-25). Injury-prone
  players lose value; the draft simulator also gives them a wider outcome distribution.
- Draft value (VBD) = value minus the last weekly starter at the position
  (RB24, WR36, QB12, TE12 in this league). K and DEF are punted to the last rounds.

## The draft optimizer (autoresearch)

`bongo_boys/draft/prepare.py` is a fixed simulator: 12-team snake from your slot with the
real keepers loaded, opponents drafting by ADP with noise calibrated from a Sleeper CPU mock,
and a season-outcome sampler (injuries, per-game variance). A drafted team is scored by its
best starting lineup plus bench value over waiver replacement.

`bongo_boys/draft/strategy.py` is the policy the assistant uses. Its `PARAMS` are tuned by:

```bash
uv run bongo draft loop --desc "what I changed"   # evaluate once, keep if best
uv run bongo draft loop --search 30               # random search over PARAMS
uv run bongo draft loop --auto --hours 5          # continuous hill-climb (screen 200 sims, confirm 1000)
```

Results append to `outputs/results.tsv`; the best parameter set is `outputs/best_strategy.json`
and is picked up automatically by `draft live` and `draft board`. See
`bongo_boys/draft/program.md` for the improvement protocol.

## Development

```bash
uv run pytest -q
uv run ruff format . && uv run ruff check .
```

Layout and design notes for AI assistants are in `CLAUDE.md`.
