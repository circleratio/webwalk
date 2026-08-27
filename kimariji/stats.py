"""学習成績の永続化。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_STATS_PATH = Path.home() / ".kimariji_stats.json"


@dataclass
class Stats:
    path: Path
    per_poem: dict[str, dict[str, int]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path = DEFAULT_STATS_PATH) -> "Stats":
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
        else:
            data = {}
        return cls(path=path, per_poem=data)

    def save(self) -> None:
        self.path.write_text(
            json.dumps(self.per_poem, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def record_for(self, no: int) -> tuple[int, int]:
        entry = self.per_poem.get(str(no), {"correct": 0, "wrong": 0})
        return entry.get("correct", 0), entry.get("wrong", 0)

    def record(self, no: int, correct: bool) -> None:
        entry = self.per_poem.setdefault(str(no), {"correct": 0, "wrong": 0})
        if correct:
            entry["correct"] += 1
        else:
            entry["wrong"] += 1

    def totals(self) -> tuple[int, int]:
        correct = sum(e.get("correct", 0) for e in self.per_poem.values())
        wrong = sum(e.get("wrong", 0) for e in self.per_poem.values())
        return correct, wrong

    def weakest(self, poems, limit: int = 10):
        """正答率が低い順に歌を返す（一定回数以上出題されたもののみ）。"""
        scored = []
        for p in poems:
            correct, wrong = self.record_for(p.no)
            total = correct + wrong
            if total == 0:
                continue
            accuracy = correct / total
            scored.append((accuracy, total, p))
        scored.sort(key=lambda t: (t[0], -t[1]))
        return scored[:limit]

    def reset(self) -> None:
        self.per_poem = {}
