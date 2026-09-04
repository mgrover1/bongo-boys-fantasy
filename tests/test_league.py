from bongo_boys.league import DraftState, slot_of_pick, snake_pick_no


def test_snake_pick_numbers():
    assert snake_pick_no(1, 11, 12) == 11
    assert snake_pick_no(2, 11, 12) == 14
    assert snake_pick_no(3, 11, 12) == 35
    assert slot_of_pick(14, 12) == (2, 11)
    assert slot_of_pick(35, 12) == (3, 11)


def make_state(picks=None, traded=None):
    return DraftState(
        draft_id="d",
        teams=12,
        rounds=15,
        slot_to_roster={s: (s + 6) % 12 + 1 for s in range(1, 13)} | {11: 5, 6: 4},
        picks=picks or [],
        traded=traded or [],
        status="pre_draft",
        my_roster_id=5,
    )


def test_traded_pick_ownership_and_keepers():
    st = make_state(
        picks=[{"pick_no": 11, "round": 1, "roster_id": 5, "player_id": "9226", "is_keeper": True}],
        traded=[{"round": 4, "roster_id": 5, "owner_id": 12, "previous_owner_id": 5}],
    )
    assert st.my_slot == 11
    assert st.pick_owner(4, 11) == 12
    assert st.pick_owner(2, 11) == 5
    mine = st.remaining_picks_for(5)
    assert 11 not in mine and 14 in mine and snake_pick_no(4, 11, 12) not in mine
    assert st.next_pick_no() == 1
    assert st.keepers_by_roster() == {5: ["9226"]}
