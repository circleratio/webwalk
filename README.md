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
