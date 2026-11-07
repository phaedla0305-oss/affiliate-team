# アフィリエイト広告制作チーム（AI 4人体制）

ChatGPT・Claude・GitHub・Copilot に役割を分け、**企画 → 制作 → 法令チェック → 実装・公開 → 販売（集客） → 効果測定 → 次の企画** を GitHub Actions で回す仕組みです。

## 役割分担

| メンバー | 役割 | 担当工程 | なぜこの担当か |
|---|---|---|---|
| **ChatGPT** | ブレスト・コピーライター | 企画アイデア出し、SNS投稿5案、広告見出し5案 | 量と言い回しの幅を出す「発散」が得意 |
| **Claude** | 編集長 | 企画の評価・企画書化、記事執筆、法令・規約レビュー、週次分析 | 長文の構成と、ルールに沿った判断の「収束」が得意 |
| **Copilot** | 実装担当 | `implement` Issue を受けてサイトを改善する PR、PR レビュー | GitHub の Issue に割り当てると PR まで作る |
| **GitHub** | 進行管理 | Issue（企画・タスク）、ラベル（承認）、PR（公開判断）、Actions（自動実行）、Pages（公開） | 全工程の記録と承認を一か所に残せる |
| **あなた** | プロデューサー | 案件選定、企画の承認、事実確認、マージ | 法的責任と最終判断は人に残す |

## 権限委譲（自動化モード）

`config.yaml` の `automation` で設定します。初期値はすべて「AI に任せる」です。

| 工程 | 自動化モード | あなたの確認が入る条件 |
|---|---|---|
| AI 間のプロンプト送信 | 各 AI が自分の判断で送る | 口座情報・カード番号・APIキー・メールアドレス・電話番号・マイナンバーらしき文字列を検出したとき（送信を止めてワークフローが失敗し、GitHub から通知が届く） |
| 企画の承認 | AI が自動で `approved` を付ける | なし |
| 記事の公開 | チェックの指摘が0件なら自動マージ → 自動公開 | critical・warn・「要確認」コメント・体験談表現が1つでもあると、`needs-review` ラベルを付けてあなたに割り当て |
| SNS 投稿 | 自動投稿（X の API キーが登録されていれば） | キーが無ければ投稿キューを作るだけ |
| サイト改善 | Copilot が PR を作成 | Copilot が作った PR のマージはあなたが行う |
| 収益の受け取り | ASP が口座へ自動振込 | 口座の登録は最初の1回だけあなたが行う（[docs/payout.md](docs/payout.md)） |

自動公開モードでは、捏造リスクのある体験談を記事に書かせません（`no_experience_claims`）。
実際に使った感想を載せたい記事は、公開後にあなたが追記してください。

## 全体の流れ

```
 [月 7:00] ⑥効果測定 ─ 学び ──────────────────────────┐
     │  Claude が分析 → kaizen Issue / implement Issue（→Copilot）│
     ▼                                                    │
 [月 9:00] ①企画  ChatGPT 10案 → Claude が2本に絞り企画書 → Issue 起票
     │
     ▼  あなたが内容を確認して `approved` ラベル   ← 人の承認①
 ②制作   Claude が記事 / ChatGPT が SNS・広告コピー
 ③チェック NG表現・PR表記・リンク形式の機械チェック ＋ Claude のレビュー
     │  → PR 自動作成
     ▼  あなたが事実確認してマージ                ← 人の承認②
 ④公開   サイト生成（PR表記・rel=sponsored・クリック計測を自動付与）→ GitHub Pages
     ▼
 ⑤販売   SNS 告知（1日1件、案を順番に使って A/B テスト）
     ▼
 GA4・ASP の CSV を data/metrics/ に置く → ⑥へ戻る
```

| ワークフロー | タイミング | 中身 |
|---|---|---|
| `1. 企画` | 毎週月曜 9:00 / 手動 | `python -m affteam plan` |
| `2. 制作` | 企画 Issue に `approved` | 記事作成 → チェック → PR |
| `3. 法令チェック` | 記事を変える PR | 機械チェック＋ビルド確認 |
| `4. 公開` | main へのマージ | GitHub Pages へデプロイ |
| `5. SNS告知` | 公開後 / 毎日12:00 | 投稿（既定はキュー作成のみ） |
| `6. 効果測定` | 毎週月曜 7:00 / 手動 | 集計 → 分析 → 改善 Issue |
| `Claude Code` | コメントに `@claude` | 記事の手直し・相談 |

## まず手元で試す（API キー不要）

```bash
pip install -r requirements.txt
```

```bash
python -m affteam --dry-run all
```

`_site/index.html` をブラウザで開くと、生成されたサイトを確認できます。

## 本番セットアップ

1. **GitHub にリポジトリを作成**して、このフォルダを push する
2. **Secrets**（Settings → Secrets and variables → Actions）に登録
   - `ANTHROPIC_API_KEY` … Claude（console.anthropic.com で発行）
   - `OPENAI_API_KEY` … ChatGPT（platform.openai.com で発行。ChatGPT の月額プランとは別契約）
   - `AUTOMATION_TOKEN` … あなたの fine-grained PAT（対象はこのリポジトリだけ。権限は Contents・Issues・Pull requests の Read and write）。AI が付けたラベル・マージで次の工程を起動するのと、Copilot への割り当てに使う
   - X に自動投稿する場合のみ: `X_API_KEY` `X_API_SECRET` `X_ACCESS_TOKEN` `X_ACCESS_SECRET`
3. **Pages** を有効化（Settings → Pages → Source: GitHub Actions）
4. **Copilot coding agent** を有効化（Copilot Pro / Pro+ / Business / Enterprise が必要）
5. **Claude Code の GitHub App** を入れる（ローカルの Claude Code で `/install-github-app`）
6. `config.yaml` の `site`・`niche`・`target`・`programs`（ASP で提携した案件と広告リンク）を自分のものに書き換える
7. 各 ASP の管理画面で振込先口座を登録する（[docs/payout.md](docs/payout.md)）
8. Actions タブから `1. 企画` を手動実行 → 以降は自動で回る

## 効果測定データの入れ方

管理画面から CSV をエクスポートし、列名を合わせて置きます（サンプルあり）。

- `data/metrics/ga/*.csv` … GA4: `date,slug,pageviews,affiliate_clicks`（`affiliate_click` イベントは自動送信済み）
- `data/metrics/asp/*.csv` … ASP: `date,program_id,slug,clicks,conversions,revenue`（記事別が取れなければ slug は空欄）

## フォルダ構成

```
affteam/        パイプライン本体（plan / produce / compliance / build / sns / measure）
prompts/        各AIへの指示文（ここを直すと品質が変わる）
config.yaml     サイト・ジャンル・案件・NG表現の設定
content/        記事（articles/*.md）と SNS 案（sns/*.json）
data/           企画データ、効果測定 CSV、SNS 投稿状況
reports/        法令チェック結果、週次レポート、SNS 投稿キュー
.github/        Actions、Copilot への指示、Issue/PR テンプレート
.claude/agents/ Claude Code のサブエージェント（editor / analyst）
docs/           調査メモ（参考にした公開ノウハウ・規制情報）
```

## 注意
- 自動公開しても、広告表示の法的責任はサイト運営者（あなた）にあります。公開済み記事は週1回程度ざっと目を通してください
- 自動投稿は X の自動化ルールと、各 ASP の規約（SNS 掲載可否）を確認してから有効にしてください
- 景品表示法・ステマ規制の判断は消費者庁の運用基準で確認してください（docs/research.md）
