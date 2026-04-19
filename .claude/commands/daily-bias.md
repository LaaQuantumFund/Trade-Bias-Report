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

## 環境変数

このコマンドは以下の環境変数で挙動を切り替える。未定義時のデフォルト値は Mac ローカル前提。

| 変数 | デフォルト | 用途 |
|---|---|---|
| `PROJECT_DIR` | `/Users/laa/dev/ict-daily-bias` | ict-daily-bias リポジトリのパス |
| `BRAIN_PATH` | `$HOME/Brain` | Brain リポジトリのパス |
| `PYTHON_BIN` | `$PROJECT_DIR/.venv/bin/python3` | Python 実行コマンド |
| `SLACK_NOTIFY_CHANNEL` | `#ceo` | Slack 通知先チャンネル |
| `CLAUDE_CODE_REMOTE` | (未定義) | `true` なら Routines 環境と判定 |

Routines 環境では、Setup script が `PROJECT_DIR` / `BRAIN_PATH` / `PYTHON_BIN` を
clone 先パスに合わせて `$CLAUDE_ENV_FILE` に書き込んでいる前提とする。

## 実行ルール

- 全ステップを順番に実行する。途中で失敗したら、原因をユーザーに報告して中止する。
- レポート本文は推測で埋めず、データ取得不可の項目は `取得不可` と明記する。
- 推測値には必ず `（推定）` と注記する。
- 出力する Markdown 内に絵文字を使わない。

## Step 1: スクレイピング実行

`Bash` ツールで以下を実行する。`$ARGUMENTS` が `weekly` の場合は末尾に ` --weekly` を付ける。

```bash
PROJECT_DIR="${PROJECT_DIR:-/Users/laa/dev/ict-daily-bias}"
PYTHON_BIN="${PYTHON_BIN:-$PROJECT_DIR/.venv/bin/python3}"
cd "$PROJECT_DIR" && "$PYTHON_BIN" main.py
```

実行後、`$PROJECT_DIR/output/scraped_data_YYYY-MM-DD.json` と
`$PROJECT_DIR/output/scraped_data_YYYY-MM-DD.txt` が生成される。
exit code が 0 でなければ以降を中止し、stderr の内容をユーザーに報告する。

## Step 2: マスタープロンプトとデータの読み込み

引数に応じて読み込むファイルを切り替える。`Read` ツールで両方を読み込む。

- 引数なし: `$PROJECT_DIR/master_prompt.md` + `$PROJECT_DIR/output/scraped_data_YYYY-MM-DD.txt`
- `weekly`: `$PROJECT_DIR/master_prompt_weekly.md` + `$PROJECT_DIR/output/scraped_data_YYYY-MM-DD.txt`

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
- 日次: `$BRAIN_PATH/Calendar/Daily-Bias/Daily_Bias_Report_YYYY-MM-DD.md`
- 週次: `$BRAIN_PATH/Calendar/Weekly-Bias/Weekly_Bias_Report_YYYY-MM-DD.md`

ディレクトリが存在しなければ以下を実行してから、`Write` ツールでレポートを保存する。

```bash
BRAIN_PATH="${BRAIN_PATH:-$HOME/Brain}"
mkdir -p "$BRAIN_PATH/Calendar/Daily-Bias" "$BRAIN_PATH/Calendar/Weekly-Bias"
```

## Step 5: Routines 環境のみ追加処理

環境変数 `CLAUDE_CODE_REMOTE` が `true` の場合のみ、以下を追加で実施する。
ローカル (Mac) 実行ではこの Step を完全にスキップする。

### 5-1. Brain リポジトリへのコミットと push

```bash
BRAIN_PATH="${BRAIN_PATH:-$HOME/Brain}"
SUBDIR="Daily-Bias"  # weekly なら "Weekly-Bias"
PREFIX="Daily_Bias_Report"  # weekly なら "Weekly_Bias_Report"
TITLE="ICT Daily Bias"  # weekly なら "ICT Weekly Bias"
TODAY=$(date +%Y-%m-%d)

cd "$BRAIN_PATH" && \
  git add "Calendar/$SUBDIR/${PREFIX}_${TODAY}.md" && \
  git commit -m "$TITLE $TODAY" && \
  git push
```

git push が認証エラーで失敗した場合、Routine 環境では GitHub proxy 経由で
処理されるため、`Allow unrestricted branch pushes` が Brain リポジトリで
有効化されているか確認する旨をユーザーに報告する。

### 5-2. Slack へ通知

Slack MCP 経由で `${SLACK_NOTIFY_CHANNEL:-#ceo}` チャンネルに以下を投稿する。

- ヘッダー: `ICT {Daily|Weekly} Bias Report - YYYY-MM-DD`
- 本文:
  - レポートのセクション0 (エグゼクティブサマリー) を抜粋 (5行)
  - 保存先ファイル名 (例: `Calendar/Daily-Bias/Daily_Bias_Report_2026-04-19.md`)
  - セッション URL: `https://claude.ai/code/${CLAUDE_CODE_REMOTE_SESSION_ID}`
  - データ取得失敗があった場合は警告として明示

## Step 6: ユーザーへの最終応答

以下の3点を簡潔に提示する。

1. レポートのセクション0 (エグゼクティブサマリー) の5行
2. 保存先のフルパス
3. データ取得失敗があった場合は警告として明示

長い本文の再掲示は不要。詳細は Brain 上のファイルで確認する前提。
