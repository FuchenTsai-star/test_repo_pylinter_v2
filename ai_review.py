import json
import os
import sys
import urllib.request

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
    review_text = response.text or "Gemini 未回傳任何內容。"
    print(response.text)
    print("=" * 40)
    # 如果在 GitHub Actions 環境中執行，就自動去該筆 Commit 底下留言
    repo = os.environ.get("GITHUB_REPOSITORY")
    sha = os.environ.get("GITHUB_SHA")
    token = os.environ.get("GITHUB_TOKEN")
    print(repo, sha, token)
    if repo and sha and token:
        post_commit_comment(repo, sha, token, review_text)


def post_commit_comment(repo: str, sha: str, token: str, comment_body: str) -> None:
    url = f"https://github.com/{repo}/commits/{sha}/comments"
    payload = {"body": f"### 🤖 Gemini AI 程式碼審查報告\n\n{comment_body}"}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as response:
        if response.status == 201:
            print("已成功將 AI 審查意見張貼至 Commit 頁面！")


if __name__ == "__main__":
    review_code("main.py")
