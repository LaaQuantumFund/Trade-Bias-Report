"""Claude API を使用してレポートを生成する。

マスタープロンプト + スクレイピングデータ → Markdown レポート
"""

import anthropic
from pathlib import Path
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL


def generate_report(scraped_data: str, master_prompt: str) -> str:
    """Claude API にデータとプロンプトを送信してレポートを生成する。

    Args:
        scraped_data: スクレイピングで取得したデータ（テキスト形式）
        master_prompt: ICT Daily Bias Report のマスタープロンプト

    Returns:
        生成されたレポート（Markdown 形式）
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_message = f"""以下のデータを使用して、今日のICT Daily Bias Reportを生成してください。

## 取得済みデータ（最優先で使用すること）

{scraped_data}

## 指示

上記のデータを「ユーザーがチャット内に貼り付けたデータ」として最優先で使用してください。
Web検索でデータが取得できなかった項目については「取得不可」と明記し、取得できたデータのみで分析を進めてください。
推測値には必ず「（推定）」と注記してください。
"""

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        system=master_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    return response.content[0].text


def load_master_prompt(path: str = "master_prompt.md") -> str:
    """マスタープロンプトをファイルから読み込む。"""
    prompt_path = Path(path)
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    else:
        raise FileNotFoundError(
            f"マスタープロンプトが見つかりません: {path}\n"
            "master_prompt.md にICT Daily Bias Reportのプロンプトを配置してください。"
        )
