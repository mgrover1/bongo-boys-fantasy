"""Typed views over league, roster, and draft state."""

from __future__ import annotations

from dataclasses import dataclass, field

from bongo_boys.sleeper import Sleeper

BENCH_SLOTS = {"BN", "IR", "TAXI"}
FLEX_ELIGIBLE = {
    "FLEX": ("RB", "WR", "TE"),
    "SUPER_FLEX": ("QB", "RB", "WR", "TE"),
    "REC_FLEX": ("WR", "TE"),
}


def snake_pick_no(rnd: int, slot: int, teams: int) -> int:
    """1-based overall pick number for a snake draft."""
    return (rnd - 1) * teams + slot if rnd % 2 == 1 else rnd * teams - slot + 1


def slot_of_pick(pick_no: int, teams: int) -> tuple[int, int]:
    rnd = (pick_no - 1) // teams + 1
    pos = (pick_no - 1) % teams + 1
    return rnd, pos if rnd % 2 == 1 else teams - pos + 1


@dataclass
class LeagueConfig:
    league_id: str
    name: str
    num_teams: int
    roster_positions: list[str]
    scoring: dict[str, float]
    settings: dict
    status: str

    @property
    def starter_slots(self) -> list[str]:
        return [p for p in self.roster_positions if p not in BENCH_SLOTS]

    @property
    def bench_count(self) -> int:
        return sum(1 for p in self.roster_positions if p == "BN")

    @property
    def position_limits(self) -> dict[str, int]:
        limits = {}
        for k, v in self.settings.items():
            if k.startswith("position_limit_") and v:
                limits[k.removeprefix("position_limit_").upper()] = int(v)
        return limits

    @classmethod
    def fetch(cls, api: Sleeper, league_id: str) -> LeagueConfig:
        lg = api.league(league_id)
        return cls(
            league_id=league_id,
            name=lg["name"],
            num_teams=lg["settings"]["num_teams"],
            roster_positions=lg["roster_positions"],
            scoring=lg["scoring_settings"],
            settings=lg["settings"],
            status=lg["status"],
        )


@dataclass
class Roster:
    roster_id: int
    owner_id: str
    owner_name: str
    players: list[str]
    starters: list[str]
    keepers: list[str]
    wins: int = 0
    losses: int = 0
    fpts: float = 0.0


def fetch_rosters(api: Sleeper, league_id: str) -> dict[int, Roster]:
    names = {u["user_id"]: u["display_name"] for u in api.users(league_id)}
    out = {}
    for r in api.rosters(league_id):
        s = r.get("settings") or {}
        out[r["roster_id"]] = Roster(
            roster_id=r["roster_id"],
            owner_id=r.get("owner_id") or "",
            owner_name=names.get(r.get("owner_id"), "?"),
            players=r.get("players") or [],
            starters=r.get("starters") or [],
            keepers=r.get("keepers") or [],
            wins=s.get("wins", 0),
            losses=s.get("losses", 0),
            fpts=s.get("fpts", 0) + s.get("fpts_decimal", 0) / 100,
        )
    return out


@dataclass
class DraftState:
    draft_id: str
    teams: int
    rounds: int
    slot_to_roster: dict[int, int]
    picks: list[dict]
    traded: list[dict]
    status: str
    my_roster_id: int
    settings: dict = field(default_factory=dict)

    @classmethod
    def fetch(
        cls, api: Sleeper, draft_id: str, my_roster_id: int, picks_ttl: int = 0
    ) -> DraftState:
        d = api.draft(draft_id)
        slot_to_roster = {int(k): v for k, v in d["slot_to_roster_id"].items()}
        picks = api.picks(draft_id, ttl=picks_ttl)
        for p in picks:  # mock drafts leave roster_id empty; derive it from the slot
            if p.get("roster_id") is None and p.get("draft_slot"):
                p["roster_id"] = slot_to_roster.get(int(p["draft_slot"]))
        return cls(
            draft_id=draft_id,
            teams=d["settings"]["teams"],
            rounds=d["settings"]["rounds"],
            slot_to_roster=slot_to_roster,
            picks=picks,
            traded=api.traded_picks(draft_id),
            status=d["status"],
            my_roster_id=my_roster_id,
            settings=d["settings"],
        )

    @property
    def roster_to_slot(self) -> dict[int, int]:
        return {r: s for s, r in self.slot_to_roster.items()}

    @property
    def my_slot(self) -> int:
        return self.roster_to_slot[self.my_roster_id]

    def pick_owner(self, rnd: int, slot: int) -> int:
        """Roster that owns the pick at (round, slot), after trades."""
        original = self.slot_to_roster[slot]
        for t in self.traded:
            if t["round"] == rnd and t["roster_id"] == original:
                return t["owner_id"]
        return original

    def owner_of_pick_no(self, pick_no: int) -> int:
        rnd, slot = slot_of_pick(pick_no, self.teams)
        return self.pick_owner(rnd, slot)

    def taken_pick_nos(self) -> set[int]:
        return {p["pick_no"] for p in self.picks}

    def drafted_player_ids(self) -> set[str]:
        return {p["player_id"] for p in self.picks}

    def picks_for(self, roster_id: int) -> list[int]:
        """All pick numbers owned by `roster_id`, including ones already used."""
        return [
            snake_pick_no(r, s, self.teams)
            for r in range(1, self.rounds + 1)
            for s in range(1, self.teams + 1)
            if self.pick_owner(r, s) == roster_id
        ]

    def remaining_picks_for(self, roster_id: int) -> list[int]:
        taken = self.taken_pick_nos()
        return sorted(p for p in self.picks_for(roster_id) if p not in taken)

    def next_pick_no(self) -> int | None:
        taken = self.taken_pick_nos()
        for n in range(1, self.teams * self.rounds + 1):
            if n not in taken:
                return n
        return None

    def roster_players(self, roster_id: int) -> list[str]:
        return [p["player_id"] for p in self.picks if p["roster_id"] == roster_id]

    def keepers_by_roster(self) -> dict[int, list[str]]:
        out: dict[int, list[str]] = {}
        for p in self.picks:
            if p.get("is_keeper"):
                out.setdefault(p["roster_id"], []).append(p["player_id"])
        return out
