from bongo_boys.projections import Player
from bongo_boys.usage import (
    INSEASON_MAX,
    INSEASON_RAMP,
    Usage,
    heat_lists,
    rest_of_season_value,
    usage_from_weeks,
)

SCORING = {"rec": 1.0, "rec_yd": 0.1, "rush_yd": 0.1, "rush_td": 6, "rec_td": 6}


def wr(pid="1", pre=170.0):
    return Player(id=pid, name="A", pos="WR", team="X", proj_pts=pre, pre_value=pre, value=pre)


def week(pid, **st):
    return {pid: {"gp": 1, "off_snp": 50, "tm_off_snp": 60, **st}}


def test_usage_rates_and_heat():
    p = wr()
    weeks = [
        week("1", rec_tgt=10, rec=7, rec_yd=90, rec_td=1),
        week("1", rec_tgt=6, rec=3, rec_yd=30),
    ]
    u = usage_from_weeks(p, weeks, SCORING)
    assert u.games == 2
    assert abs(u.snap_share - 100 / 120) < 1e-9
    assert u.tgt_pg == 8.0
    assert u.actual_ppg == (7 + 9 + 6 + 3 + 3) / 2
    assert u.opp_ppg == 1.75 * 8
    assert u.heat == u.actual_ppg - u.opp_ppg


def test_zero_games_keeps_preseason_ppg_but_fewer_games():
    p = wr()
    u = Usage()
    assert rest_of_season_value(p, u, done=1) == round(170 / 17 * 16, 1)
    assert u.weight == 0.0


def test_weight_ramps_and_caps():
    p = wr()
    u = Usage(games=1, actual_ppg=30.0, opp_ppg=30.0)
    v1 = rest_of_season_value(p, u, done=1)
    assert u.weight == INSEASON_RAMP
    assert v1 > 170 / 17 * 16  # hot usage raises the rest-of-season number
    rest_of_season_value(p, u, done=10)
    assert u.weight == INSEASON_MAX


def test_heat_lists_split_hot_and_cold():
    hot = wr("h")
    hot.usage = Usage(games=1, actual_ppg=25, opp_ppg=8)
    cold = wr("c")
    cold.usage = Usage(games=1, actual_ppg=3, opp_ppg=15)
    thin = wr("t")
    thin.usage = Usage(games=1, actual_ppg=0, opp_ppg=4)  # cold but no real role
    h, c = heat_lists({"h": hot, "c": cold, "t": thin})
    assert [p.id for p in h] == ["h"]
    assert [p.id for p in c] == ["c"]
