"""Sleeper fantasy football tooling for the Bongo Bingo Bongo league."""

import os

LEAGUE_ID = "1365790508172992512"

_REAL_DRAFT_ID = "1365790508181377024"
# Point at a mock draft with BONGO_DRAFT_ID=<mock id> BONGO_MY_ROSTER_ID=<my slot>.
DRAFT_ID = os.environ.get("BONGO_DRAFT_ID", _REAL_DRAFT_ID)
USERNAME = "mgroverwx"
USER_ID = "858419887591243776"
MY_ROSTER_ID = int(os.environ.get("BONGO_MY_ROSTER_ID", "5"))
SEASON = "2026"
