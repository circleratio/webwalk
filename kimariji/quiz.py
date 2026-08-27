"""出題ロジック（curses に依存しない純粋なロジック）。"""

from __future__ import annotations

import random
from dataclasses import dataclass

from kimariji.data import Poem
from kimariji.stats import Stats


def candidates(poems: tuple[Poem, ...], prefix: str) -> list[Poem]:
    """上の句の読みが prefix で始まる歌の一覧（残り候補）を返す。"""
    return [p for p in poems if p.kami_hiragana.startswith(prefix)]


def weighted_choice(poems: list[Poem], stats: Stats) -> Poem:
    """正答率が低い歌ほど出題されやすくなるように重み付けして1首選ぶ。"""
    weights = []
    for p in poems:
        correct, wrong = stats.record_for(p.no)
        total = correct + wrong
        if total == 0:
            weight = 3.0
        else:
            accuracy = correct / total
            weight = 1.0 + (1.0 - accuracy) * 4.0
        weights.append(weight)
    return random.choices(poems, weights=weights, k=1)[0]


@dataclass
class RoundResult:
    poem: Poem
    revealed_chars: int
    answer_no: int | None
    correct: bool


def grade(poem: Poem, revealed_chars: int, answer_no: int | None) -> RoundResult:
    correct = answer_no is not None and answer_no == poem.no
    return RoundResult(
        poem=poem,
        revealed_chars=revealed_chars,
        answer_no=answer_no,
        correct=correct,
    )
