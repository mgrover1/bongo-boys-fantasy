from types import SimpleNamespace

from bongo_boys.projections import Player
from bongo_boys.tools.briefing import best_weekly_lineup, week_projections


def test_bye_rows_kept_with_zero_points():
    rows = [
        {"player_id": "kelce", "game_id": None, "opponent": None, "stats": {}},
        {"player_id": "kraft", "game_id": "g1", "opponent": "CHI", "stats": {"pts_ppr": 10.8}},
        {"player_id": "none", "game_id": "g2", "opponent": "DAL", "stats": {}},
    ]
    ctx = SimpleNamespace(api=SimpleNamespace(week_projections=lambda season, week: rows))
    wk = week_projections(ctx, 5)
    assert wk["kelce"] == {"pts": 0.0, "opp": None, "bye": True}
    assert wk["kraft"]["pts"] == 10.8 and not wk["kraft"]["bye"]
    assert "none" not in wk


def test_lineup_skips_out_players():
    out = Player(id="o", name="Out WR", pos="WR", team="PHI", injury_status="Out")
    ok = Player(id="k", name="OK WR", pos="WR", team="LAR")
    ctx = SimpleNamespace(league=SimpleNamespace(starter_slots=["WR"]))
    wk = {"o": {"pts": 12.3}, "k": {"pts": 8.0}}
    assert [p.id for _, p, _ in best_weekly_lineup(ctx, [out, ok], wk)] == ["k"]
