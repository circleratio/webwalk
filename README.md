# EU Notified Bodies Monitor

EU の [Single Market Compliance Space](https://webgate.ec.europa.eu/single-market-compliance-space/notified-bodies/notified-body-list?filter=legislationId:162960,notificationStatusId:1)
(NANDO) の通知機関(Notified Body)リストを定期的に取得し、前回取得時との差分(新規追加・削除・変更されたエントリ)を検出するツールです。

対象URLはデフォルトで `legislationId:162960, notificationStatusId:1`(= 特定の法令・ステータスでフィルタしたリスト)になっています。

## 仕組み

対象ページは Angular の SPA で、HTML 自体にはリストのデータが含まれておらず、
ページ読み込み後に裏側で叩かれる JSON API からデータが取得されます。API のパスは
EC 側の実装変更で変わりうるため、このツールは特定の API パスや CSS セレクタを
ハードコードせず、次の順で自動検出します。

1. まず素の HTTP GET を行い、HTML に埋め込まれた JSON(初期状態用の `<script>` タグ)を探す
2. 見つからなければ Playwright でヘッドレスブラウザを起動してページを実際に読み込み、
   その間にブラウザが受け取った全ての JSON レスポンスを検査し、「通知機関の一覧らしい
   データ(名前っぽいフィールド + 番号/国っぽいフィールドを持つ辞書のリスト)」を自動判定する

取得したエントリは NB番号/id/コードなど識別子らしいフィールドをキーにして、
前回実行時に保存したスナップショット(`state/notified_bodies.json`)と比較します。

> **注意:** この自動判定はヒューリスティックです。初回実行時に正しいデータが
> 取れているか、出力される件数やサンプルを必ず目視確認してください。うまく
> 取れない場合は下記の「うまく動かないとき」を参照してください。

## セットアップ

```bash
pip install -r requirements.txt
playwright install --with-deps chromium
```

## 実行

```bash
python scripts/monitor_notified_bodies.py \
  --url "https://webgate.ec.europa.eu/single-market-compliance-space/notified-bodies/notified-body-list?filter=legislationId:162960,notificationStatusId:1" \
  --state-file state/notified_bodies.json
```

- 初回実行時は比較対象がないため、取得結果をベースラインとして保存するだけです(差分は報告されません)。
- 2回目以降の実行で、前回のスナップショットと比較して新規/削除/変更を報告します。
- 新規エントリが見つかった場合、終了コード `3` を返します(cron などでの通知トリガーに利用可能)。
- 取得自体に失敗した場合は終了コード `1` を返します。

### 主なオプション

| オプション | 説明 |
| --- | --- |
| `--state-file` | 前回スナップショットの保存先(既定: `state/notified_bodies.json`) |
| `--debug-dir` | 取得したページHTMLと全APIレスポンスをここに保存する(トラブルシュート用) |
| `--api-url-contains` | このURL部分文字列を含むJSONレスポンスのみ対象にする |
| `--json-path` | APIレスポンス内でリストが入っているキーへのドット区切りパス(例: `content`) |
| `--json-output` | 差分をJSON形式でも標準出力に出す |

## うまく動かないとき

対象データの自動判定に失敗した場合(終了コード1、または明らかに関係ないデータが
拾われている場合)は、`--debug-dir` を付けて再実行してください。

```bash
python scripts/monitor_notified_bodies.py --debug-dir debug
```

`debug/responses.json` に、ページ読み込み中にブラウザが受け取った全JSONレスポンスの
URLとトップレベルキー一覧が書き出されます。ここから通知機関リストらしいレスポンスを
探し、`debug/response_<N>.json` で中身を確認してください。正しいものが分かったら:

- そのURLの一部を `--api-url-contains` に指定する
- リストがネストしたキーの下にある場合は `--json-path` でそこまでのパスを指定する

ブラウザの開発者ツール(Networkタブ)で実際にページを開いて確認するのが一番確実です。

## GitHub Actions での定期実行

`.github/workflows/monitor-notified-bodies.yml` に、毎日UTC 6時に実行するワークフローを
用意しています。新規エントリが見つかった場合は `notified-bodies-alert` ラベル付きの
Issue を自動作成し、取得結果のスナップショットはリポジトリにコミットして次回実行時の
比較に使います。手動実行(`workflow_dispatch`)にも対応しています。

初回のワークフロー実行はベースライン保存のみなので、Issueは作成されません。

---

# 百人一首 決まり字 暗記トレーナー

`kimariji/` は、競技かるたの決まり字（読み札が上の句の何文字目まで読まれれば
一意に特定できるか）を暗記するための、依存ライブラリ不要（標準ライブラリの
`curses` のみ）の TUI アプリです。上記の EU 監視ツールとは無関係の独立した
ツールです。

## 実行

```bash
python -m kimariji
```

## 主な機能

- **出題モード**: 上の句の読みを1文字ずつ表示し、分かった時点で歌番号（1〜100）を
  入力して解答します。正解／不正解と、実際の決まり字・本来の決まり字の文字数を
  表示します。
- **決まり字の文字数を指定した出題**: 一字決まり（7首）〜六字決まり（6首）まで、
  グループを絞って集中的に練習できます。
- **苦手な歌を優先して出題**: これまでの正答率が低い歌ほど出題されやすくなります。
- **一覧表示**: 全100首を決まり字の文字数順に一覧表示します。
- **成績**: 累計の正答率と、正答率が低い歌のランキングを確認できます。

成績は既定で `~/.kimariji_stats.json` に保存されます（`--state-file` オプションで
変更可能）。

決まり字のデータ（`kimariji/data/hyakunin_isshu.json`）は、各歌の上の句が他の
99首と比べて何文字目で一意に定まるかを実際に算出したもので、一字決まり7首・
二字決まり42首・三字決まり37首・四字決まり6首・五字決まり2首・六字決まり6首と
いう競技かるたで知られる標準的な内訳と一致することを確認済みです。
