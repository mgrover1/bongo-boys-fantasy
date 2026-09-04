from bongo_boys.draft.prepare import PickContext
from bongo_boys.draft.strategy import PARAMS, p_available, pos_gaps, rank_available
from bongo_boys.league import LeagueConfig
from bongo_boys.projections import Player


def ctx_with(players, roster=(), next_pick=20):
    league = LeagueConfig(
        "l", "n", 12, ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF", "BN"], {}, {}, "x"
    )
    return PickContext(
        pick_no=5,
        round=1,
        rounds=15,
        my_roster=list(roster),
        available={p.id: p for p in players},
        next_pick_no=next_pick,
        baselines={"RB": 100, "WR": 100, "QB": 200, "TE": 80},
        league=league,
    )


def test_availability_sigmoid_and_cliff():
    a = Player(id="a", name="A", pos="RB", team="X", proj_pts=200, adp=10)
    b = Player(id="b", name="B", pos="RB", team="X", proj_pts=150, adp=40)
    for p in (a, b):
        p.value = p.proj_pts
    ctx = ctx_with([a, b])
    params = dict(PARAMS, avail_sigma=5.0)
    assert p_available(a, ctx, params) < 0.2 < 0.8 < p_available(b, ctx, params)
    assert pos_gaps(ctx)["RB"] == ("a", 50.0)
    top = rank_available(ctx, dict(PARAMS, cliff_gap=10.0, cliff_bonus=500.0))[0][1]
    assert top.id == "a"
