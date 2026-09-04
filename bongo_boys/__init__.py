"""Sleeper fantasy football tooling for the Bongo Bingo Bongo league.

Configuration is by environment variable so anyone in the league can use it:

    BONGO_USERNAME      Sleeper username (default mgroverwx)
    BONGO_LEAGUE_ID     league id (default Bongo Bingo Bongo - remastered)
    BONGO_DRAFT_ID      draft id (default: the league's current draft; set to a mock draft id)
    BONGO_MY_ROSTER_ID  roster id / mock slot (default: looked up from BONGO_USERNAME)
"""

from __future__ import annotations

import os

USERNAME = os.environ.get("BONGO_USERNAME", "mgroverwx")
LEAGUE_ID = os.environ.get("BONGO_LEAGUE_ID", "1365790508172992512")
SEASON = os.environ.get("BONGO_SEASON", "2026")
_DEFAULTS = {"mgroverwx": ("858419887591243776", 5, "1365790508181377024")}


def _lookup() -> tuple[str, int, str]:
    """user_id, roster_id, draft_id for USERNAME in LEAGUE_ID (cached by the client)."""
    if USERNAME in _DEFAULTS and LEAGUE_ID == "1365790508172992512":
        return _DEFAULTS[USERNAME]
    from bongo_boys.sleeper import Sleeper

    api = Sleeper()
    uid = api.user(USERNAME)["user_id"]
    roster = next((r for r in api.rosters(LEAGUE_ID) if r.get("owner_id") == uid), None)
    drafts = api.drafts(LEAGUE_ID)
    return uid, roster["roster_id"] if roster else 0, drafts[0]["draft_id"] if drafts else ""


USER_ID, _roster, _draft = _lookup()
MY_ROSTER_ID = int(os.environ.get("BONGO_MY_ROSTER_ID", _roster))
DRAFT_ID = os.environ.get("BONGO_DRAFT_ID", _draft)
