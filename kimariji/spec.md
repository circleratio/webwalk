# 百人一首 決まり字 暗記トレーナー 設計仕様書

対象: `requirement.md` に記載した要求を満たす実装（`kimariji/` パッケージ）の
設計内容をまとめたもの。

## 1. アーキテクチャ概要

依存ライブラリを増やさず標準ライブラリのみで完結させるため、以下のように
「ロジック層」と「表示（curses）層」を分離している。ロジック層は curses に
一切依存せず、TTY なしでも import・単体実行できる。

```
kimariji/
├── __init__.py        パッケージ宣言のみ
├── __main__.py         CLI エントリポイント（argparse）
├── data.py              歌データのロード（Poem データクラス）
├── data/
│   └── hyakunin_isshu.json   100首分のデータ本体
├── quiz.py               出題ロジック（候補抽出・重み付け抽選・採点）
├── stats.py              成績の永続化（JSON ファイル読み書き）
└── tui.py                curses による画面描画・入力処理
```

依存関係の向き: `tui.py` → `quiz.py` / `stats.py` / `data.py`。
`quiz.py` は `stats.py` の `Stats` を型として参照するのみで、curses には
一切依存しない。

## 2. データ設計

### 2.1 データソースと決まり字の算出方法

上の句・下の句の本文・読み（ひらがな）は、GitHub 上で公開されている
百人一首データセット（歌人名・上の句・下の句・両者のひらがな読みを含む
CSV）を出典とし、決まり字は以下の手順で機械的に算出した。

1. 各歌の上の句の読み（ひらがな）について、歴史的仮名遣いの範囲で
   現代の発音上区別されない表記のゆれ（を→お、ぢ→じ、づ→ず、ゐ→い、
   ゑ→え、および「あふ」のような母音連続の長音化など）を正規化する。
2. 正規化後の文字列を先頭から1文字ずつ伸ばしていき、他の99首のいずれ
   とも重複しなくなる最小の文字数を求める。これが決まり字の文字数
   （`kimariji_len`）である。
3. 決まり字そのもの（`kimariji` フィールド）は、正規化後ではなく、
   歌本来の（歴史的仮名遣いによる）読みを、2. で求めた文字数だけ
   切り出した文字列とする。これにより、アプリ上の表示は歌本来の
   仮名遣いのまま、文字数だけを標準的な決まり字定義に合わせている。
4. 算出結果の文字数別内訳（一字決まり7・二字決まり42・三字決まり37・
   四字決まり6・五字決まり2・六字決まり6、計100）が、競技かるたで
   知られる標準的な内訳と完全に一致することを確認し、データの妥当性
   を検証した。

この算出・検証はデータ作成時に一度だけ行うオフライン作業であり、
アプリの実行時には行わない（`kimariji/data/hyakunin_isshu.json` に
結果を静的に保存している）。

### 2.2 データスキーマ

`kimariji/data/hyakunin_isshu.json` は以下の形式のオブジェクトを100件
含む JSON 配列。

```json
{
  "no": 1,
  "poet": "天智天皇",
  "kami_kanji": "秋の田のかりほの庵の苫をあらみ",
  "shimo_kanji": "わが衣手は露にぬれつつ",
  "kami_hiragana": "あきのたのかりほのいほのとまをあらみ",
  "shimo_hiragana": "わがころもではつゆにぬれつつ",
  "kimariji": "あきの",
  "kimariji_len": 3
}
```

| フィールド | 型 | 説明 |
| --- | --- | --- |
| `no` | int | 歌番号（1〜100、百人一首の通し番号） |
| `poet` | str | 歌人名（漢字） |
| `kami_kanji` | str | 上の句（漢字仮名交じり） |
| `shimo_kanji` | str | 下の句（漢字仮名交じり） |
| `kami_hiragana` | str | 上の句の読み（ひらがな、歴史的仮名遣い） |
| `shimo_hiragana` | str | 下の句の読み（ひらがな、歴史的仮名遣い） |
| `kimariji` | str | 決まり字（`kami_hiragana` の先頭 `kimariji_len` 文字） |
| `kimariji_len` | int | 決まり字の文字数（1〜6） |

### 2.3 `data.py`

- `Poem`: 上記スキーマに対応する `@dataclass(frozen=True)`。
- `load_poems() -> tuple[Poem, ...]`: JSON を読み込み、`no` 昇順にソート
  した `Poem` のタプルを返す。`functools.lru_cache(maxsize=1)` により
  プロセス内では1度だけファイルを読み込む。

## 3. 出題ロジック設計（`quiz.py`）

curses に依存しない純粋関数として実装し、`tui.py` から呼び出される。

- `candidates(poems, prefix) -> list[Poem]`: `kami_hiragana` が `prefix`
  で始まる歌の一覧を返す。決まり字の性質上、`prefix` が実際の決まり字と
  一致する長さであれば、返る歌は必ず1首（またはそれ以上の共通決まり字
  グループの場合はグループ全体）になる。一覧表示のグルーピング検証や
  将来的な「残り候補数を見せる」出題形式の拡張に使える設計としている。
- `weighted_choice(poems, stats) -> Poem`: 出題プールから1首を重み付き
  乱択で選ぶ。
  - 出題実績がない歌: 重み `3.0`。
  - 出題実績がある歌: 重み `1.0 + (1.0 - 正答率) * 4.0`
    （正答率が低いほど重みが大きい。正答率100%でも最低重み1.0は残る
    ため、完全に出題対象から外れることはない）。
  - `random.choices(..., weights=...)` により選択。
- `RoundResult`（`@dataclass`）: `poem` / `revealed_chars`
  （解答時点で表示していた文字数） / `answer_text`（ユーザーが入力した
  ひらがな文字列、未回答は空文字列） / `correct`（正誤）を保持する。
- `grade(poem, revealed_chars, answer_text) -> RoundResult`:
  `answer_text.strip() == poem.shimo_hiragana` であれば正解と判定する
  （下の句の読みと完全一致するかどうかで採点する。前後の空白のみ
  無視する）。

## 4. 成績永続化設計（`stats.py`）

- 保存形式は JSON。トップレベルは歌番号（文字列）をキーとする辞書で、
  値は `{"correct": int, "wrong": int}`。

  ```json
  {
    "1": {"correct": 3, "wrong": 1},
    "57": {"correct": 0, "wrong": 2}
  }
  ```

- 既定の保存先は `~/.kimariji_stats.json`（`DEFAULT_STATS_PATH`）。
  `kimariji/__main__.py` の `--state-file` オプションで変更可能。
- `Stats.load(path)`: ファイルが存在しない、または壊れている
  （JSON デコードエラー・OS エラー）場合は空の状態から開始する
  （エラーで落とさない）。
- `Stats.record(no, correct)`: 該当歌の `correct`/`wrong` を1加算。
- `Stats.save()`: 現在の状態をファイルへ書き出す。出題1問ごと（解答直後）
  に呼び出し、都度永続化することで、アプリが異常終了しても直近の結果
  まで保持されるようにしている。
- `Stats.totals()`: 全体の正解数・不正解数を返す。
- `Stats.weakest(poems, limit)`: 出題実績が1回以上ある歌のみを対象に、
  正答率の低い順（同率の場合は出題回数が多い順）に並べ替え、上位
  `limit` 件を返す。出題実績がない歌は対象外とする（母数が0での
  正答率計算を避けるとともに、単に「一度も出していない」歌と
  「本当に苦手な」歌を区別するため）。
- `Stats.reset()`: 内部状態を空にする（呼び出し側で `save()` するまで
  ファイルには反映されない）。

## 5. UI 設計（`tui.py`）

### 5.1 画面遷移

```
main_menu
 ├─ [1] practice_screen(poems 全体)
 ├─ [2] length_filter_menu → practice_screen(文字数で絞った poems)
 ├─ [3] practice_screen(苦手上位30首プール, weak_only)
 ├─ [4] browse_screen
 ├─ [5] stats_screen
 ├─ [6] reset_stats_screen
 └─ [q] 終了
```

各画面はブロッキングな `while` ループで構成し、ユーザー操作で
`return` することで `main_menu` の呼び出し元へ戻る（画面遷移スタックは
Python の関数呼び出しスタックそのものを利用しており、専用の状態機械は
持たない）。

### 5.2 出題画面（`practice_screen`）のフロー

1. `weighted_choice` で1首選択し、`revealed`（表示済み文字数）を
   `1`（1文字目は最初から表示する）、`buf`（解答入力バッファ、
   ひらがな文字列）を空文字列で初期化する。
2. 内側ループでキー入力を待つ。ひらがな（全角）文字を1文字単位で
   取得する必要があるため、バイト単位の `getch()` ではなく
   `stdscr.get_wch()` を使用する（`get_wch()` は特殊キーを `int`、
   通常の文字を `str` として返すため、`isinstance` で分岐する）。
   - Space（`buf` が空の場合のみ）: `revealed` を1増やして再描画。
   - Enter（`\n`/`\r`、または `curses.KEY_ENTER`）: `buf` が空なら
     Space と同様に `revealed` を1増やす。`buf` が非空なら、それを
     解答として確定しループを抜ける。
   - Backspace（`\x08`/`\x7f`、または `curses.KEY_BACKSPACE`）:
     `buf` の末尾1文字を削除する。
   - ESC（`\x1b` または `27`）、または `buf` が空の状態での `q`:
     出題モードを終了しメニューへ戻る（`buf` が非空のときの `q` は
     通常の入力文字として扱う）。
   - `s`（`buf` が空の場合のみ）: 現在の問題をスキップ（不正解として
     は記録しない）。`buf` が非空の場合は通常の入力文字として扱われる
     （ひらがな入力中に IME 変換前の英字が紛れ込むことはない前提）。
   - それ以外の印字可能な文字（`str.isprintable()`）: `buf` に追加する。
   - 入力中はカーソルを表示し（`curses.curs_set(1)`）、`buf` の表示
     位置に `stdscr.move()` でカーソルを追従させる。ループを抜けた
     ら `curses.curs_set(0)` に戻す（`try`/`finally` で保証）。
3. スキップ以外の場合、`grade(poem, revealed, buf)` で採点し
   `stats.record()` / `stats.save()` を行った上で `_show_result()`
   を表示する。採点は入力された `buf`（前後の空白を除く）が
   `poem.shimo_hiragana`（下の句の読み）と完全一致するかどうかで
   判定する。
4. `_show_result()` で何かキーが押されたら 1. に戻り次の問題へ進む。

`weak_only=True` の場合は、`stats.weakest()` の上位30首を出題プールと
する。30首未満（学習初期で出題実績が少ない）場合は通常の全体プールに
フォールバックする。

### 5.3 一覧表示画面（`browse_screen`）

- 表示対象の歌を `(kimariji_len, kimariji, no)` でソートし、決まり字の
  文字数が変わるタイミングでグループ見出し行（例:
  `── 二字決まり ──`）を挿入した行リストを事前に構築する。
- スクロールは表示開始行インデックス `top` を保持し、`j`/`↓` で+1、
  `k`/`↑` で-1、PageDown/PageUp で画面の行数分だけ移動する。
  `top` は `[0, len(lines) - body_height]` の範囲にクランプする。

### 5.4 全角文字対応（表示幅の扱い）

curses の `addstr` は端末上のカラム数ではなく Python 文字列の文字数で
文字列を扱わないため、そのまま `len()` で切り詰めると、全角文字
（漢字・ひらがな、`unicodedata.east_asian_width` が `W`/`F` の文字）が
半角文字と同じ1カラムとして計算され、実際の表示幅を超えて書き込みが
発生する。これは狭い端末幅で行が折り返され、次の行の描画内容と
視覚的に混ざる不具合の原因になるため、以下のヘルパーで対処している。

- `_char_width(ch)`: `unicodedata.east_asian_width(ch)` が `"W"` または
  `"F"` の場合は2、それ以外は1を返す。
- `_display_width(text)`: 文字列全体の表示カラム数を返す。
- `_truncate_to_width(text, max_width)`: 表示カラム数の累積が
  `max_width` を超えない範囲で文字列を切り詰める。
- `_safe_addstr(win, y, x, text, attr)`: 全ての画面描画箇所が経由する
  共通描画関数。以下を行う:
  1. 描画位置 `(y, x)` がウィンドウ範囲外なら何もしない。
  2. `_truncate_to_width` により、書き込み可能な残りカラム数
     （`max_x - x - 1`、右端1カラムは curses の仕様上の安全マージン）
     を超えないように切り詰める。
  3. `curses.error`（端末右下端への書き込み等、curses 自体が起こす
     例外）を捕捉して無視する。
- メインメニューのタイトル中央寄せも、`len(title) * 2`
  （全角前提の決め打ち）ではなく `_display_width(title)` を用いる
  ことで、半角混じりの文字列でも正しく中央寄せされる。

### 5.5 色・装飾

- `curses.has_colors()` が真の場合のみ、正解=緑（`color_pair(1)`）、
  不正解=赤（`color_pair(2)`）を初期化して結果画面の見出しに使用する。
  カラー非対応端末でも `A_BOLD` 等の属性のみで機能する。

### 5.6 ロケール・エントリポイント

- `main(stats_path)`: `locale.setlocale(locale.LC_ALL, "")` を実行して
  実行環境のロケールに合わせた文字幅処理・エンコーディングを有効化した
  上で、`curses.wrapper(run, ...)` を呼び出す。`curses.wrapper` は
  端末初期化・後始末（`curs_set` の復元、`endwin()` 等）を保証し、
  例外発生時にも端末を壊れた状態のまま残さない。
- `run(stdscr, stats_path)`: カーソル非表示化、特殊キー（矢印キー等）の
  有効化、カラーペアの初期化、データ・成績のロードを行い、
  `main_menu` を呼び出す。

## 6. CLI 設計（`__main__.py`）

```
python -m kimariji [--state-file PATH]
```

- `--state-file`: 成績保存先のパス（既定値: `stats.DEFAULT_STATS_PATH`
  = `~/.kimariji_stats.json`）。既存の EU 監視ツール
  （`monitor_notified_bodies.py`）が `--state-file` オプションで状態
  ファイルを指定する規約と揃えている。

## 7. エラー処理・堅牢性についての設計方針

- 成績ファイルの読み込み失敗（存在しない・壊れている）はアプリの
  起動を妨げず、空の成績として扱う。
- 画面描画は全て `_safe_addstr` を経由させることで、ウィンドウ範囲外
  への書き込みや、想定より小さい端末サイズによる `curses.error` で
  アプリ全体がクラッシュしないようにしている。
- キー入力は、想定外のキーコード（特殊キー、範囲外の値）が来ても
  無視されるだけで例外を発生させない設計とする（`0 <= ch < 256` の
  範囲チェックを都度行う）。

## 8. テスト方針

- `data.py` / `quiz.py` / `stats.py` は curses に依存しないため、
  実端末（TTY）なしで import・関数呼び出しレベルの検証が可能。
  データ整合性（決まり字文字数の内訳が標準的な7/42/37/6/2/6と一致する
  こと、全100件でフィールド欠落がないこと等）はこの層で検証済み。
- `tui.py` は実際のターミナル（PTY）上で `python -m kimariji` を起動し、
  各画面への遷移・キー入力・スクロール・端末幅を変えた場合の表示崩れ
  の有無を目視確認する形で検証する。
