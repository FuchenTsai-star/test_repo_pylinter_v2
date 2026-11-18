import json
import os
import sys
import urllib.request

from dotenv import load_dotenv
from google import genai
from google.genai import errors

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
    # 設定模型優先順序：主力模型塞車（503）時，自動切換到下一個備援模型
    models_to_try = ["gemini-4-hydrogen", "gemini-3.8-flash", "gemini-3.5-flash-lite"]
    review_text = ""
    for model_name in models_to_try:
        try:
            print(f"嘗試使用模型 {model_name} 進行審查...")
            response = client.models.generate_content(model=model_name, contents=prompt)
            review_text = response.text or "Gemini 未回傳任何內容。"
            print(response.text)
            print("=" * 40)
            # 如果在 GitHub Actions 環境中執行，就自動去該筆 Commit 底下留言
            repo = os.environ.get("GITHUB_REPOSITORY")
            sha = os.environ.get("GITHUB_SHA")
            token = os.environ.get("GITHUB_TOKEN")
            if repo and sha and token:
                post_commit_comment(repo, sha, token, review_text)
            break
        except errors.ServerError as e:
            print(f"模型 {model_name} 目前滿載（503）：{e}")
        except errors.ClientError as e:
            # 若帳號不支援某個備援模型（404），自動跳過試下一個
            print(f"模型 {model_name} 無法使用（{e.code}），嘗試下一個備援模型...")
    if not review_text:
        review_text = "所有備援模型目前皆滿載或無法使用，略過本次 AI 審查。"
        print(review_text)
        if repo and sha and token:
            post_commit_comment(repo, sha, token, review_text)
        return


def post_commit_comment(repo: str, sha: str, token: str, comment_body: str) -> None:
    url = f"https://api.github.com/repos/{repo}/commits/{sha}/comments"
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
