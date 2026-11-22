"""Тесты модуля «Шипперим»."""

from __future__ import annotations

import random

from app.modules.shipper.service import (
    ENDINGS,
    TITLES,
    Candidate,
    build_ship_message,
    choose_pair,
)

CANDIDATES = [
    Candidate(1, "Аня", "anya"),
    Candidate(2, "Борис", None),
    Candidate(3, "Вика", "vika"),
    Candidate(4, "Гоша", "gosha"),
    Candidate(5, "Робот", "robot", is_bot=True),
    Candidate(0, "IrisV2", "IrisV2Bot", is_bot=True, is_self=True),
]


def test_choose_pair_excludes_other_bots() -> None:
    rng = random.Random(7)
    for _ in range(50):
        picked = choose_pair(CANDIDATES, rng=rng)
        assert picked is not None
        first, second, _ = picked
        assert first.user_id != 5 and second.user_id != 5
        assert first.user_id != second.user_id
        assert not first.is_bot or first.is_self
        assert not second.is_bot or second.is_self


def test_choose_pair_can_pick_iris() -> None:
    candidates = [Candidate(1, "Аня", "anya"), Candidate(0, "IrisV2", "IrisV2Bot", is_bot=True, is_self=True)]
    picked = choose_pair(candidates, rng=random.Random(1))
    assert picked is not None
    first, second, _ = picked
    assert {first.user_id, second.user_id} == {0, 1}


def test_choose_pair_excludes_initiator_when_possible() -> None:
    rng = random.Random(3)
    for _ in range(50):
        first, second, _ = choose_pair(CANDIDATES, initiator_id=1, rng=rng)
        assert 1 not in {first.user_id, second.user_id}


def test_choose_pair_falls_back_to_initiator() -> None:
    picked = choose_pair([Candidate(1, "Аня"), Candidate(2, "Борис")], initiator_id=1)
    assert picked is not None
    first, second, _ = picked
    assert {first.user_id, second.user_id} == {1, 2}


def test_choose_pair_requires_two_members() -> None:
    assert choose_pair([Candidate(1, "Аня")]) is None
    assert choose_pair([Candidate(1, "Аня"), Candidate(2, "Бот", is_bot=True)]) is None
    assert choose_pair([]) is None


def test_choose_pair_avoids_recent_pairs() -> None:
    candidates = [Candidate(1, "Аня"), Candidate(2, "Борис"), Candidate(3, "Вика")]
    recent = {frozenset((1, 2)), frozenset((1, 3))}
    first, second, repeated = choose_pair(candidates, recent_pairs=recent, rng=random.Random(1))
    assert frozenset((first.user_id, second.user_id)) == frozenset((2, 3))
    assert repeated is False


def test_choose_pair_marks_repeat_when_all_pairs_seen() -> None:
    candidates = [Candidate(1, "Аня"), Candidate(2, "Борис")]
    first, second, repeated = choose_pair(
        candidates, recent_pairs={frozenset((1, 2))}, rng=random.Random(5)
    )
    assert {first.user_id, second.user_id} == {1, 2}
    assert repeated is True


def test_message_has_links_and_no_percent() -> None:
    text = build_ship_message(CANDIDATES[0], CANDIDATES[1], random.Random(2))
    assert "Аня" in text and "Борис" in text
    assert "https://t.me/anya" in text
    assert "tg://user?id=2" in text
    assert "%" not in text
    assert any(text.startswith(title) for title in TITLES)
    assert any(text.endswith(ending) for ending in ENDINGS)


def test_message_variations() -> None:
    messages = {
        build_ship_message(CANDIDATES[0], CANDIDATES[2], random.Random(seed))
        for seed in range(15)
    }
    assert len(messages) >= 2
