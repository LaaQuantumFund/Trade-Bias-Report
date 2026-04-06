# ICT Daily Bias Report — 自動生成パイプライン

## 概要

Playwright（ヘッドレスブラウザ）でリテールセンチメントデータを取得し、
Claude API (Opus 4.6) にマスタープロンプトとデータを渡してレポートを生成する。
出力は Markdown ファイルとして Obsidian Vault に保存される。

## 前提条件

- Python 3.11+
- Anthropic API キー（https://console.anthropic.com/）
- Node.js 18+（Playwright 用）

## セットアップ手順

### 1. リポジトリをクローンまたはコピー

```bash
cd ~/projects  # 任意の場所
cp -r ict-daily-bias ./
cd ict-daily-bias
```

### 2. Python 仮想環境を作成

```bash
python3 -m venv .venv
source .venv/bin/activate   # Mac/Linux
# .venv\Scripts\activate    # Windows
```

### 3. 依存パッケージをインストール

```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. 環境変数を設定

```bash
cp .env.example .env
# .env を編集して ANTHROPIC_API_KEY を設定
```

### 5. 出力先を設定

`.env` の `OBSIDIAN_VAULT_PATH` を自分の Obsidian Vault のパスに変更。

### 6. 実行

```bash
python main.py
```

## Claude Code での使い方

Claude Code がインストール済みなら、プロジェクトディレクトリで：

```bash
claude "main.py を実行してデイリーバイアスレポートを生成して"
```

または初回セットアップごと任せる場合：

```bash
claude "このプロジェクトのセットアップを実行して。.envのANTHROPIC_API_KEYは sk-ant-xxx に設定して"
```

## ファイル構成

```
ict-daily-bias/
├── README.md              # このファイル
├── requirements.txt       # Python 依存パッケージ
├── .env.example           # 環境変数テンプレート
├── main.py                # メインオーケストレーター
├── config.py              # 設定読み込み
├── generate_report.py     # Claude API でレポート生成
├── master_prompt.md       # ICT Daily Bias マスタープロンプト（別途配置）
├── scrapers/
│   ├── __init__.py
│   ├── myfxbook.py        # MyFXBook センチメント取得
│   ├── fxssi.py           # FXSSI Current Ratio 取得
│   ├── ig_sentiment.py    # IG Client Sentiment 取得
│   ├── coinglass.py       # CoinGlass L/S Ratio + Funding Rate
│   └── economic_calendar.py  # 経済指標カレンダー（Investing.com）
└── output/                # ローカル出力（Obsidian にもコピー）
```

## カスタマイズ

- `master_prompt.md` に ICT Daily Bias Report のマスタープロンプトを配置する
- 銘柄の追加・変更は `config.py` の `INSTRUMENTS` を編集
- スクレイピング対象サイトの変更は各 `scrapers/*.py` を編集

## トラブルシューティング

- **Playwright がブロックされる場合:** `scrapers/` 内の各スクリプトで
  User-Agent やヘッドレスモードの設定を調整
- **API キーエラー:** `.env` の `ANTHROPIC_API_KEY` を確認
- **サイト構造変更:** スクレイパーのセレクタを Claude Code に修正させる
  `claude "myfxbook.py のセレクタが壊れている。サイトを確認して修正して"`
