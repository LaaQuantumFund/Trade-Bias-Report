---
description: ICT Daily/Weekly Bias Report を生成 (Mac/Routines 両対応)
argument-hint: [weekly]
allowed-tools: Bash, Read, Write
---

# ICT Daily Bias Report 生成

トレード分析の直前に、チャート外情報 (リテールセンチメント、経済指標、FedWatch、ETFフロー、COT 等)
を体系的にまとめたレポートを生成し、Brain (Obsidian Vault) に保存する。

引数:
- 引数なし: 日次レポート (`master_prompt.md` を使用)
- `weekly`: 週次レポート (`master_prompt_weekly.md` を使用、COT データも含む)

引数: $ARGUMENTS

## 実行ルール

- 全ステップを順番に実行する。途中で失敗したら、原因をユーザーに報告して中止する。
- レポート本文は推測で埋めず、データ取得不可の項目は `取得不可` と明記する。
- 推測値には必ず `（推定）` と注記する。
- 出力する Markdown 内に絵文字を使わない。

## Step 1: スクレイピング実行

`Bash` ツールで以下を実行する。引数 `$ARGUMENTS` が `weekly` なら `--weekly` を付ける。

ローカル (Mac) 実行:

```bash
cd /Users/laa/dev/ict-daily-bias && ./.venv/bin/python3 main.py
```

`weekly` の場合:

```bash
cd /Users/laa/dev/ict-daily-bias && ./.venv/bin/python3 main.py --weekly
```

クラウド (Routines) 環境では `.venv` が無く、ワークスペースのパスも異なるので以下の形にする:

```bash
cd "$CLAUDE_PROJECT_DIR" && python3 main.py
```

(weekly なら `python3 main.py --weekly`)

判定方法: 環境変数 `CLAUDE_CODE_REMOTE` が `true` ならクラウド形式、そうでなければローカル形式。

実行後、`output/scraped_data_YYYY-MM-DD.json` と `output/scraped_data_YYYY-MM-DD.txt` が生成される。
exit code が 0 でなければ以降を中止し、stderr の内容をユーザーに報告する。

## Step 2: マスタープロンプトとデータの読み込み

引数に応じて読み込むファイルを切り替える。

- 引数なし: `master_prompt.md` + `output/scraped_data_YYYY-MM-DD.txt`
- `weekly`: `master_prompt_weekly.md` + `output/scraped_data_YYYY-MM-DD.txt`

`Read` ツールで両方を読み込む。

## Step 3: 分析・レポート生成

マスタープロンプトの指示 (セクション0〜7、出力ルール) に厳密に従って Markdown レポートを生成する。
具体的には、以下のメンタルモデルで分析を進める。

「以下のデータを使用して、本日の ICT {Daily|Weekly} Bias Report を生成してください。

## 取得済みデータ (最優先で使用すること)

{scraped_data_YYYY-MM-DD.txt の全文}

## 指示

- 取得済みデータを最優先で使用すること
- データ取得不可の項目は『取得不可』と明記すること
- 推測値には必ず『（推定）』と注記すること
- マスタープロンプトのセクション順序、テーブル形式、出力ルール、ICT用語規則に厳密に従うこと」

レポートは Markdown 形式、テーブル積極使用、絵文字禁止、時刻はすべて JST、
全体 2000-3500 字を目安に、master_prompt の出力ルールに従って生成する。

## Step 4: レポートを Brain に保存

ファイル名は `Daily_Bias_Report_YYYY-MM-DD.md` (または `Weekly_Bias_Report_YYYY-MM-DD.md`)。
日付は実行時の JST 日付を使う。

出力先:
- 日次: `~/Brain/Calendar/Daily-Bias/Daily_Bias_Report_YYYY-MM-DD.md`
- 週次: `~/Brain/Calendar/Weekly-Bias/Weekly_Bias_Report_YYYY-MM-DD.md`

ディレクトリが存在しなければ `Bash` で `mkdir -p` を実行してから、`Write` ツールでレポートを保存する。

## Step 5: Routines 環境のみ追加処理

環境変数 `CLAUDE_CODE_REMOTE` が `true` の場合のみ、以下を追加で実施する。
ローカル (Mac) 実行ではこの Step をスキップする。

### 5-1. Brain リポジトリへのコミットと push

```bash
cd ~/Brain && \
  git add Calendar/Daily-Bias/Daily_Bias_Report_YYYY-MM-DD.md && \
  git commit -m "ICT Daily Bias YYYY-MM-DD" && \
  git push
```

(週次なら `Calendar/Weekly-Bias/...` および `ICT Weekly Bias YYYY-MM-DD`)

### 5-2. Slack へ通知

Slack MCP 経由で `#trading` チャンネル (未指定なら DM) に以下を投稿する。

- 件名: `ICT {Daily|Weekly} Bias Report - YYYY-MM-DD`
- 本文:
  - レポートのセクション0 (エグゼクティブサマリー) を抜粋
  - 保存先ファイル名
  - セッション URL: `https://claude.ai/code/${CLAUDE_CODE_REMOTE_SESSION_ID}`

## Step 6: ユーザーへの最終応答

以下の3点を簡潔に提示する。

1. レポートのセクション0 (エグゼクティブサマリー) の5行
2. 保存先のフルパス
3. データ取得失敗があった場合は警告として明示

長い本文の再掲示は不要。詳細は Brain 上のファイルで確認する前提。
