import os
import sys

from dotenv import load_dotenv
from google import genai

load_dotenv()


def review_code(file_path: str) -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("錯誤：找不到 GEMINI_API_KEY 環境變數。")
        sys.exit(1)
    with open(file_path, "r", encoding="utf-8") as f:
        code_content = f.read()
    client = genai.Client(api_key=api_key)
    prompt = (
        "請擔任資深 Python 工程師，幫我審查以下程式碼。"
        "請用繁體中文條列指出潛在的 Bug、邏輯問題或可改進之處（若無明顯問題請給予簡短肯定）：\n\n"
        f"```python\n{code_content}\n```"
    )
    print(f"正在請 Gemini 審查 {file_path}...\n" + "=" * 40)
    response = client.models.generate_content(model="gemini-3.8-flash", contents=prompt)
    print(response.text)
    print("=" * 40)


if __name__ == "__main__":
    review_code("main.py")
