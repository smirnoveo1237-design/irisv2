"""Тесты модуля «Ирис кто»."""

from __future__ import annotations

import random

from app.modules.iris_who.service import (
    Candidate,
    build_answer,
    pick_person,
)

CANDIDATES = [
    Candidate(10, "Даша"),
    Candidate(11, "Егор"),
    Candidate(12, "IrisV2", is_bot=True),
]


def test_pick_person_excludes_bots() -> None:
    rng = random.Random(11)
    for _ in range(30):
        person = pick_person(CANDIDATES, rng=rng)
        assert person is not None
        assert person.user_id in {10, 11}


def test_pick_person_excludes_given_ids() -> None:
    person = pick_person(CANDIDATES, exclude_ids={10, 12}, rng=random.Random(1))
    assert person is not None
    assert person.user_id == 11


def test_pick_person_empty() -> None:
    assert pick_person([Candidate(12, "Bot", is_bot=True)]) is None
    assert pick_person([]) is None


def test_text_after_who_is_preserved() -> None:
    answer = build_answer(Candidate(10, "Даша"), "самый смешной человек", rng=random.Random(2))
    assert "самый смешной человек" in answer
    assert "Даша" in answer
    assert 'href="tg://user?id=10"' in answer


def test_default_text_when_empty() -> None:
    answer = build_answer(Candidate(11, "Егор"), "", rng=random.Random(2))
    assert "загадочная личность" in answer


def test_same_template_family() -> None:
    answers = {build_answer(Candidate(10, "Даша"), "тест", rng=random.Random(seed)) for seed in range(12)}
    assert len(answers) >= 2
