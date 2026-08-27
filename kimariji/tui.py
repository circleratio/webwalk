"""curses ベースの TUI 画面。"""

from __future__ import annotations

import curses
import locale
import unicodedata

from kimariji.data import Poem, load_poems
from kimariji.quiz import grade, weighted_choice
from kimariji.stats import DEFAULT_STATS_PATH, Stats

KIMARIJI_GROUP_LABEL = {
    1: "一字決まり",
    2: "二字決まり",
    3: "三字決まり",
    4: "四字決まり",
    5: "五字決まり",
    6: "六字決まり",
}


def _char_width(ch: str) -> int:
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def _display_width(text: str) -> int:
    return sum(_char_width(c) for c in text)


def _truncate_to_width(text: str, max_width: int) -> str:
    if max_width <= 0:
        return ""
    out = []
    used = 0
    for ch in text:
        w = _char_width(ch)
        if used + w > max_width:
            break
        out.append(ch)
        used += w
    return "".join(out)


def _safe_addstr(win, y: int, x: int, text: str, attr: int = 0) -> None:
    max_y, max_x = win.getmaxyx()
    if y < 0 or y >= max_y or x < 0 or x >= max_x:
        return
    try:
        win.addstr(y, x, _truncate_to_width(text, max_x - x - 1), attr)
    except curses.error:
        pass


class BackToMenu(Exception):
    pass


class QuitApp(Exception):
    pass


def _wait_key(stdscr) -> int:
    return stdscr.getch()


def main_menu(stdscr, poems: tuple[Poem, ...], stats: Stats) -> None:
    items = [
        ("1", "出題モード（全100首からランダム）", lambda: practice_screen(stdscr, poems, stats, None)),
        ("2", "出題モード（決まり字の文字数を指定）", lambda: length_filter_menu(stdscr, poems, stats)),
        ("3", "苦手な歌を優先して出題", lambda: practice_screen(stdscr, poems, stats, None, weak_only=True)),
        ("4", "一覧表示（決まり字順）", lambda: browse_screen(stdscr, poems)),
        ("5", "成績を見る", lambda: stats_screen(stdscr, poems, stats)),
        ("6", "成績をリセット", lambda: reset_stats_screen(stdscr, stats)),
        ("q", "終了", None),
    ]
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        title = "百人一首 決まり字 暗記トレーナー"
        _safe_addstr(stdscr, 1, max(0, (w - _display_width(title)) // 2), title, curses.A_BOLD)
        correct, wrong = stats.totals()
        total = correct + wrong
        acc = f"{correct}/{total} 正解 ({correct / total * 100:.1f}%)" if total else "まだ記録がありません"
        _safe_addstr(stdscr, 3, 4, f"これまでの成績: {acc}")

        for i, (key, label, _) in enumerate(items):
            _safe_addstr(stdscr, 6 + i, 6, f"[{key}] {label}")

        _safe_addstr(stdscr, 7 + len(items), 4, "キーを押して選択してください。", curses.A_DIM)
        stdscr.refresh()

        ch = _wait_key(stdscr)
        try:
            key_char = chr(ch) if 0 <= ch < 256 else ""
        except ValueError:
            key_char = ""

        if key_char == "q" or ch == 27:
            return

        for key, _label, action in items:
            if key_char == key and action is not None:
                try:
                    action()
                except BackToMenu:
                    pass
                break


def length_filter_menu(stdscr, poems, stats) -> None:
    while True:
        stdscr.erase()
        _safe_addstr(stdscr, 1, 4, "決まり字の文字数を選んでください", curses.A_BOLD)
        for n in range(1, 7):
            count = sum(1 for p in poems if p.kimariji_len == n)
            _safe_addstr(
                stdscr,
                3 + n,
                6,
                f"[{n}] {KIMARIJI_GROUP_LABEL[n]}（{count}首）",
            )
        _safe_addstr(stdscr, 11, 6, "[b] 戻る")
        stdscr.refresh()

        ch = _wait_key(stdscr)
        try:
            key_char = chr(ch)
        except ValueError:
            key_char = ""

        if key_char == "b" or ch == 27:
            return
        if key_char in "123456":
            n = int(key_char)
            filtered = [p for p in poems if p.kimariji_len == n]
            practice_screen(stdscr, filtered, stats, n)
            return


def practice_screen(
    stdscr,
    poems: tuple[Poem, ...],
    stats: Stats,
    length_filter: int | None,
    weak_only: bool = False,
) -> None:
    pool = list(poems)
    if weak_only:
        weak = stats.weakest(poems, limit=30)
        if weak:
            pool = [p for _acc, _total, p in weak]

    question_no = 0
    while True:
        question_no += 1
        poem = weighted_choice(pool, stats)
        revealed = 0
        buf = ""
        skipped = False

        curses.curs_set(1)
        try:
            while True:
                stdscr.erase()
                header = f"第{question_no}問"
                if length_filter:
                    header += f"（{KIMARIJI_GROUP_LABEL[length_filter]}のみ）"
                _safe_addstr(stdscr, 1, 4, header, curses.A_BOLD)

                shown = poem.kami_hiragana[:revealed]
                hidden = "・" * (len(poem.kami_hiragana) - revealed)
                _safe_addstr(stdscr, 3, 4, "上の句（読み）:")
                _safe_addstr(stdscr, 4, 6, shown + hidden, curses.A_UNDERLINE)

                _safe_addstr(stdscr, 6, 4, "下の句（ひらがな）を入力してください:")
                _safe_addstr(stdscr, 7, 6, buf, curses.A_UNDERLINE)

                _safe_addstr(stdscr, 9, 4, "[Space] もう1文字表示する    [Enter] 解答する")
                _safe_addstr(stdscr, 10, 4, "[Backspace] 1文字削除    [s] スキップ    [q] メニューに戻る")
                try:
                    stdscr.move(7, 6 + _display_width(buf))
                except curses.error:
                    pass
                stdscr.refresh()

                try:
                    ch = stdscr.get_wch()
                except curses.error:
                    continue

                is_special_key = isinstance(ch, int)

                if is_special_key and ch == curses.KEY_BACKSPACE:
                    buf = buf[:-1]
                    continue
                if not is_special_key and ch in ("\x08", "\x7f"):
                    buf = buf[:-1]
                    continue

                if (is_special_key and ch in (curses.KEY_ENTER, 10, 13)) or (
                    not is_special_key and ch in ("\n", "\r")
                ):
                    if buf:
                        break
                    revealed = min(revealed + 1, len(poem.kami_hiragana))
                    continue

                if (is_special_key and ch == 27) or (not is_special_key and ch == "\x1b"):
                    return

                if not is_special_key and ch == "q" and not buf:
                    return

                if not is_special_key and ch == " ":
                    revealed = min(revealed + 1, len(poem.kami_hiragana))
                    continue

                if not is_special_key and ch == "s" and not buf:
                    skipped = True
                    break

                if not is_special_key and ch.isprintable():
                    buf += ch
        finally:
            curses.curs_set(0)

        if skipped:
            continue

        result = grade(poem, revealed_chars=revealed, answer_text=buf)
        stats.record(poem.no, result.correct)
        stats.save()
        _show_result(stdscr, result)


def _show_result(stdscr, result) -> None:
    poem = result.poem
    stdscr.erase()
    color = curses.color_pair(1) if result.correct else curses.color_pair(2)
    verdict = "正解！" if result.correct else "不正解"
    _safe_addstr(stdscr, 1, 4, verdict, curses.A_BOLD | color)

    answer_display = result.answer_text.strip() if result.answer_text.strip() else "（無回答）"
    _safe_addstr(stdscr, 2, 4, f"あなたの解答: {answer_display}")

    _safe_addstr(stdscr, 4, 4, f"正解: {poem.no}番 {poem.poet}")
    _safe_addstr(stdscr, 5, 4, f"上の句: {poem.kami_kanji}")
    _safe_addstr(stdscr, 6, 4, f"下の句: {poem.shimo_kanji}（{poem.shimo_hiragana}）")
    _safe_addstr(
        stdscr,
        8,
        4,
        f"決まり字: 「{poem.kimariji}」（{poem.kimariji_len}字決まり）",
        curses.A_BOLD,
    )
    _safe_addstr(
        stdscr,
        9,
        4,
        f"あなたが表示した文字数: {result.revealed_chars}字",
    )

    _safe_addstr(stdscr, 11, 4, "何かキーを押すと次の問題へ進みます。", curses.A_DIM)
    stdscr.refresh()
    stdscr.getch()


def browse_screen(stdscr, poems: tuple[Poem, ...]) -> None:
    ordered = sorted(poems, key=lambda p: (p.kimariji_len, p.kimariji, p.no))
    lines: list[tuple[str, int]] = []
    current_len = None
    for p in ordered:
        if p.kimariji_len != current_len:
            current_len = p.kimariji_len
            lines.append((f"── {KIMARIJI_GROUP_LABEL[current_len]} ──", -1))
        lines.append((f"{p.no:>3}番 「{p.kimariji}」 {p.kami_kanji}", p.no))

    top = 0
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        body_height = h - 3
        _safe_addstr(stdscr, 0, 2, "一覧表示（j/k または ↑↓ でスクロール、q で戻る）", curses.A_BOLD)
        for i in range(body_height):
            idx = top + i
            if idx >= len(lines):
                break
            text, no = lines[idx]
            attr = curses.A_BOLD if no == -1 else 0
            _safe_addstr(stdscr, 2 + i, 2, text, attr)
        stdscr.refresh()

        ch = stdscr.getch()
        if ch in (ord("q"), 27):
            return
        if ch in (ord("j"), curses.KEY_DOWN):
            top = min(top + 1, max(0, len(lines) - body_height))
        elif ch in (ord("k"), curses.KEY_UP):
            top = max(top - 1, 0)
        elif ch == curses.KEY_NPAGE:
            top = min(top + body_height, max(0, len(lines) - body_height))
        elif ch == curses.KEY_PPAGE:
            top = max(top - body_height, 0)


def stats_screen(stdscr, poems: tuple[Poem, ...], stats: Stats) -> None:
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    correct, wrong = stats.totals()
    total = correct + wrong
    _safe_addstr(stdscr, 1, 4, "成績", curses.A_BOLD)
    if total == 0:
        _safe_addstr(stdscr, 3, 4, "まだ出題記録がありません。")
    else:
        _safe_addstr(stdscr, 3, 4, f"総合: {correct}/{total} 正解 ({correct / total * 100:.1f}%)")
        _safe_addstr(stdscr, 5, 4, "苦手な歌 (正答率が低い順):", curses.A_BOLD)
        weak = stats.weakest(poems, limit=max(1, min(10, h - 8)))
        if not weak:
            _safe_addstr(stdscr, 6, 4, "（十分な出題回数のある歌がまだありません）")
        for i, (acc, cnt, p) in enumerate(weak):
            _safe_addstr(
                stdscr,
                6 + i,
                6,
                f"{p.no:>3}番「{p.kimariji}」 {p.kami_kanji}  正答率{acc * 100:.0f}%（{cnt}回出題）",
            )
    _safe_addstr(stdscr, h - 2, 4, "何かキーを押すと戻ります。", curses.A_DIM)
    stdscr.refresh()
    stdscr.getch()


def reset_stats_screen(stdscr, stats: Stats) -> None:
    stdscr.erase()
    _safe_addstr(stdscr, 1, 4, "成績をリセットしますか？ (y/N)", curses.A_BOLD)
    stdscr.refresh()
    ch = stdscr.getch()
    if ch in (ord("y"), ord("Y")):
        stats.reset()
        stats.save()
        _safe_addstr(stdscr, 3, 4, "リセットしました。何かキーを押してください。")
        stdscr.refresh()
        stdscr.getch()


def run(stdscr, stats_path=DEFAULT_STATS_PATH) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)
    if curses.has_colors():
        curses.start_color()
        curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)

    poems = load_poems()
    stats = Stats.load(stats_path)
    main_menu(stdscr, poems, stats)


def main(stats_path=DEFAULT_STATS_PATH) -> None:
    locale.setlocale(locale.LC_ALL, "")
    curses.wrapper(run, stats_path=stats_path)
