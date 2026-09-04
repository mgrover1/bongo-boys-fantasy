from bongo_boys.projections import Player, blended_value, score_stats


def test_score_stats_uses_league_weights():
    assert score_stats({"rec": 10, "rec_yd": 100, "junk": 5}, {"rec": 1.0, "rec_yd": 0.1}) == 20.0


def test_blended_value_penalises_injury_history():
    healthy = Player(
        id="1",
        name="A",
        pos="RB",
        team="X",
        proj_pts=170,
        prior_ppg=10,
        games_missed=0,
        games_possible=51,
    )
    fragile = Player(
        id="2",
        name="B",
        pos="RB",
        team="X",
        proj_pts=170,
        prior_ppg=10,
        games_missed=15,
        games_possible=51,
    )
    assert blended_value(healthy) == 170.0
    assert blended_value(fragile) < blended_value(healthy)
