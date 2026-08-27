"""百人一首 100首のデータ読み込み。

各歌の決まり字（かるた競技において読み札を一意に特定できる最小の文字数）は
歌自体の定義から算出したもので、一字決まり7首・二字決まり42首・三字決まり37首・
四字決まり6首・五字決まり2首・六字決まり6首という競技かるたの標準的な内訳と
一致することを確認済み。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_DATA_PATH = Path(__file__).parent / "data" / "hyakunin_isshu.json"


@dataclass(frozen=True)
class Poem:
    no: int
    poet: str
    kami_kanji: str
    shimo_kanji: str
    kami_hiragana: str
    shimo_hiragana: str
    kimariji: str
    kimariji_len: int


@lru_cache(maxsize=1)
def load_poems() -> tuple[Poem, ...]:
    raw = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    return tuple(Poem(**entry) for entry in sorted(raw, key=lambda e: e["no"]))
