#!/usr/bin/env python3
"""Monitor the EU "Single Market Compliance Space" notified-body list for new entries.

The target page (NANDO / notified-bodies/notified-body-list) is an Angular
single-page app: the HTML it serves does not directly contain the list, the
data comes from a JSON API call the app makes after loading. Rather than
hard-coding a specific API path or CSS selector (which the EC can and does
change), this script:

  1. First tries a plain HTTP GET and looks for JSON embedded directly in the
     HTML (some SPAs ship an initial-state blob in a <script> tag).
  2. If that fails, it drives a real headless browser (Playwright), lets the
     page load normally, and inspects every JSON network response the page
     receives. Whichever response looks like a list of notified-body records
     (heuristically: dict entries with a name-like field and a number/id-like
     field) is treated as "the data".

Extracted entries are keyed by whatever field looks like a stable identifier
(NB number / id / code) and compared against the previous run's snapshot
(--state-file). New keys are reported as new entries.

Usage:
    python monitor_notified_bodies.py \
        --url "https://webgate.ec.europa.eu/single-market-compliance-space/notified-bodies/notified-body-list?filter=legislationId:162960,notificationStatusId:1" \
        --state-file state/notified_bodies.json

Exit codes:
    0  no new entries (including the very first "baseline" run)
    1  fetch/parse error (could not extract any usable data)
    3  new entries were found

If extraction fails, re-run with --debug-dir to dump every captured API
response so you can find the right one and pin it down with
--api-url-contains / --json-path.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

DEFAULT_URL = (
    "https://webgate.ec.europa.eu/single-market-compliance-space/notified-bodies/"
    "notified-body-list?filter=legislationId:162960,notificationStatusId:1"
)

USER_AGENT = "Mozilla/5.0 (compatible; NotifiedBodyMonitor/1.0; +monitoring script)"

NAME_HINTS = ("name", "organisation", "organization", "denomination", "bodyname")
COUNTRY_HINTS = ("country",)
NUMBER_HINTS = ("nbnumber", "notifiedbodynumber", "number", "nbid", "code")
ID_KEY_CANDIDATES = (
    "nbNumber",
    "notifiedBodyNumber",
    "number",
    "nbId",
    "id",
    "organisationId",
    "code",
)


def looks_like_nb_entry(entry: dict, min_fields: int = 3) -> bool:
    if not isinstance(entry, dict) or len(entry) < min_fields:
        return False
    keys_lower = [k.lower() for k in entry.keys()]
    has_name = any(any(h in k for h in NAME_HINTS) for k in keys_lower)
    has_number_or_country = any(
        any(h in k for h in NUMBER_HINTS + COUNTRY_HINTS) for k in keys_lower
    ) or "id" in keys_lower
    return has_name and has_number_or_country


def find_entry_list(
    data: Any, min_fields: int = 3, json_path: Optional[str] = None
) -> Optional[list]:
    if json_path:
        node = data
        for part in json_path.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return None
        return node if isinstance(node, list) else None

    candidates: list[list] = []

    def visit(node: Any) -> None:
        if isinstance(node, list):
            if node and all(isinstance(x, dict) for x in node) and looks_like_nb_entry(
                node[0], min_fields
            ):
                candidates.append(node)
            for v in node:
                visit(v)
        elif isinstance(node, dict):
            for v in node.values():
                visit(v)

    visit(data)
    if not candidates:
        return None
    candidates.sort(key=len, reverse=True)
    return candidates[0]


def fetch_via_html(url: str, timeout: int, min_fields: int) -> tuple[Optional[list], Optional[str]]:
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    html = resp.text

    blocks = re.findall(r"<script[^>]*type=\"application/json\"[^>]*>(.*?)</script>", html, re.S)
    blocks += re.findall(r"<script[^>]*id=\"[^\"]*state[^\"]*\"[^>]*>(.*?)</script>", html, re.S | re.I)

    for raw in blocks:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        entries = find_entry_list(data, min_fields)
        if entries:
            return entries, "html-embedded-json"
    return None, None


def fetch_via_browser(
    url: str,
    timeout: int,
    min_fields: int,
    api_url_contains: Optional[str],
    json_path: Optional[str],
    debug_dir: Optional[Path],
) -> tuple[Optional[list], Optional[str]]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "playwright is not installed. Run: pip install playwright && "
            "playwright install --with-deps chromium"
        ) from exc

    captured: list[tuple[str, Any]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)

        def on_response(response) -> None:
            try:
                ctype = response.headers.get("content-type", "")
                if "application/json" not in ctype:
                    return
                if api_url_contains and api_url_contains not in response.url:
                    return
                data = response.json()
            except Exception:
                return
            captured.append((response.url, data))

        page.on("response", on_response)
        try:
            page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
        except Exception:
            # Some SPAs never go fully idle (polling, websockets); proceed with
            # whatever we already captured instead of failing outright.
            pass
        page.wait_for_timeout(2000)

        if debug_dir:
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / "page.html").write_text(page.content(), encoding="utf-8")
            (debug_dir / "responses.json").write_text(
                json.dumps(
                    [{"url": u, "sample_keys": list(d.keys()) if isinstance(d, dict) else "list"}
                     for u, d in captured],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            for i, (u, d) in enumerate(captured):
                (debug_dir / f"response_{i}.json").write_text(
                    json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8"
                )

        browser.close()

    best: Optional[list] = None
    best_url: Optional[str] = None
    for resp_url, data in captured:
        entries = find_entry_list(data, min_fields, json_path)
        if entries and (best is None or len(entries) > len(best)):
            best = entries
            best_url = resp_url

    if best is not None:
        return best, f"api-capture:{best_url}"
    return None, None


def normalize_entries(raw_entries: list) -> dict[str, dict]:
    normalized: dict[str, dict] = {}
    for entry in raw_entries:
        key = None
        if isinstance(entry, dict):
            for cand in ID_KEY_CANDIDATES:
                if entry.get(cand) not in (None, ""):
                    key = str(entry[cand])
                    break
            if key is None:
                key = json.dumps(entry, sort_keys=True, ensure_ascii=False)
        else:
            key = str(entry)
        normalized[key] = entry
    return normalized


def summarize(entry: Any) -> str:
    if not isinstance(entry, dict):
        return str(entry)

    def pick(hints: tuple[str, ...]) -> Optional[str]:
        for k, v in entry.items():
            if v and any(h in k.lower() for h in hints):
                return str(v)
        return None

    number = pick(NUMBER_HINTS)
    name = pick(NAME_HINTS)
    country = pick(COUNTRY_HINTS)
    parts = []
    if number:
        parts.append(f"[{number}]")
    if name:
        parts.append(name)
    if country:
        parts.append(f"({country})")
    return " ".join(parts) if parts else json.dumps(entry, ensure_ascii=False)


def diff_states(previous: dict, current: dict) -> tuple[dict, dict, dict]:
    prev_keys, curr_keys = set(previous.keys()), set(current.keys())
    added = {k: current[k] for k in curr_keys - prev_keys}
    removed = {k: previous[k] for k in prev_keys - curr_keys}
    changed = {}
    for k in curr_keys & prev_keys:
        if json.dumps(previous[k], sort_keys=True, ensure_ascii=False) != json.dumps(
            current[k], sort_keys=True, ensure_ascii=False
        ):
            changed[k] = {"before": previous[k], "after": current[k]}
    return added, removed, changed


def print_report(
    report: dict, current: dict, previous: Optional[dict], source: str, now: str, url: str
) -> None:
    print("=== EU Notified Bodies 監視ツール ===")
    print(f"対象URL: {url}")
    print(f"取得日時: {now}")
    print(f"取得方法: {source}")
    print(f"今回の件数: {len(current)}")

    if report["baseline"]:
        print("\n初回実行のため、今回取得した内容をベースラインとして保存しました。")
        print("次回以降の実行から新規/削除/変更の差分を報告します。")
        return

    prev_count = len(previous.get("entries", {})) if previous else 0
    print(f"前回の件数: {prev_count}")

    added, removed, changed = report["added"], report["removed"], report["changed"]

    if added:
        print(f"\n🆕 新規エントリ ({len(added)}件):")
        for k, v in added.items():
            print(f"  - {summarize(v)}  (key={k})")
    else:
        print("\n新規エントリ: なし")

    if removed:
        print(f"\n🗑 削除されたエントリ ({len(removed)}件):")
        for k, v in removed.items():
            print(f"  - {summarize(v)}  (key={k})")

    if changed:
        print(f"\n♻️ 内容が変更されたエントリ ({len(changed)}件):")
        for k, diff in changed.items():
            print(f"  - key={k}: {summarize(diff['after'])}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--state-file", default="state/notified_bodies.json")
    parser.add_argument("--timeout", type=int, default=45, help="seconds")
    parser.add_argument("--min-fields", type=int, default=3, help="min dict fields to count as a notified-body record")
    parser.add_argument("--api-url-contains", default=None, help="only trust JSON responses whose URL contains this substring")
    parser.add_argument("--json-path", default=None, help="dotted path into the API response envelope, e.g. 'content' or 'data.items'")
    parser.add_argument("--json-output", action="store_true", help="also print the diff as JSON on stdout")
    parser.add_argument("--debug-dir", default=None, help="dump raw page HTML and captured API responses here")
    args = parser.parse_args()

    state_path = Path(args.state_file)
    previous = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else None

    debug_dir = Path(args.debug_dir) if args.debug_dir else None

    entries: Optional[list] = None
    source: Optional[str] = None
    try:
        entries, source = fetch_via_html(args.url, args.timeout, args.min_fields)
    except requests.RequestException as exc:
        print(f"[warn] plain HTTP fetch failed: {exc}", file=sys.stderr)

    if entries is None:
        try:
            entries, source = fetch_via_browser(
                args.url, args.timeout, args.min_fields, args.api_url_contains, args.json_path, debug_dir
            )
        except RuntimeError as exc:
            print(f"[error] {exc}", file=sys.stderr)
            sys.exit(1)

    if not entries:
        print("エラー: 対象ページから通知機関リストのデータを抽出できませんでした。", file=sys.stderr)
        print("サイトの構造が変わった可能性があります。--debug-dir を指定して再実行し、", file=sys.stderr)
        print("responses.json の中から正しいAPIレスポンスを探して --api-url-contains / --json-path で指定してください。", file=sys.stderr)
        sys.exit(1)

    current = normalize_entries(entries)
    now = datetime.now(timezone.utc).isoformat()

    if previous is None:
        report = {"added": {}, "removed": {}, "changed": {}, "baseline": True}
    else:
        added, removed, changed = diff_states(previous.get("entries", {}), current)
        report = {"added": added, "removed": removed, "changed": changed, "baseline": False}

    new_state = {"url": args.url, "fetched_at": now, "source": source, "entries": current}
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(new_state, ensure_ascii=False, indent=2), encoding="utf-8")

    print_report(report, current, previous, source, now, args.url)

    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))

    if not report["baseline"] and report["added"]:
        sys.exit(3)
    sys.exit(0)


if __name__ == "__main__":
    main()
