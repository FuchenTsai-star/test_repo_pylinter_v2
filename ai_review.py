import json
import os
import subprocess
import sys
import urllib.request

from dotenv import load_dotenv
from google import genai
from google.genai import errors

load_dotenv()


def review_code(file_path: str) -> None:
    """使用 Gemini AI 審查單一 Python 檔案，並在 GitHub Commit 頁面留言回報。"""
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


def review_changes() -> None:
    """使用 Gemini AI 審查最近兩筆 Commit 的 Python 檔案變更，並在 GitHub Commit 頁面留言回報。"""
    changed_files, diff_content = get_changed_py_files_and_diff()

    # 若這次 Push 完全沒有改動任何業務邏輯的 .py 檔案，直接結束（零 API 費用）
    if not changed_files:
        print("本次未偵測到任何 Python 業務檔案變更，已略過 AI 審查以節省額度。")
        return

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("錯誤：找不到 GEMINI_API_KEY 環境變數。")
        sys.exit(1)

    # 讀取本次受影響的完整 Python 檔案內容（作為下半部整體架構審查的上下文）
    full_files_section = []
    for file_path in changed_files:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            full_files_section.append(f"#### 檔案：`{file_path}`\n```python\n{content}\n```")
    full_code_context = "\n\n".join(full_files_section)

    prompt = (
        "請擔任資深 Python 工程師，針對本次 Git 提交進行雙視角程式碼審查。"
        "請務必使用繁體中文，並嚴格依照以下【兩部分結構】條列回覆（若無明顯問題請給予簡短肯定）：\n\n"
        "### 第一部分：本次調整範圍建議（針對 Git Diff 變更處）\n"
        "請專注檢查下方「程式碼變更差異」中新增或修改的邏輯，指出是否有潛在 Bug、邊界條件遺漏或寫法問題。\n\n"
        "### 第二部分：受影響主要程式的整體建議（結合完整上下文）\n"
        "請結合下方「受影響檔案完整內容」，評估這次修改對整體程式架構、可讀性或效能的影響與改進建議。\n\n"
        "---\n"
        f"【程式碼變更差異 (Git Diff)】\n```diff\n{diff_content}\n```\n\n"
        f"【受影響檔案完整內容】\n{full_code_context}"
    )

    client = genai.Client(api_key=api_key)
    models_to_try = ["gemini-4-hydrogen", "gemini-3.8-flash", "gemini-3.5-flash-lite"]

    repo = os.environ.get("GITHUB_REPOSITORY")
    sha = os.environ.get("GITHUB_SHA")
    token = os.environ.get("GITHUB_TOKEN")

    review_text = ""
    for model_name in models_to_try:
        try:
            print(f"嘗試使用模型 {model_name} 審查變更檔案：{', '.join(changed_files)}...")
            response = client.models.generate_content(model=model_name, contents=prompt)
            review_text = response.text or "Gemini 未回傳任何內容。"
            print(review_text)
            print("=" * 40)
            break
        except errors.ServerError as e:
            print(f"模型 {model_name} 目前滿載（503）：{e}")
        except errors.ClientError as e:
            print(f"模型 {model_name} 無法使用（{e.code}），嘗試下一個備援模型...")

    if not review_text:
        review_text = "所有備援模型目前皆滿載或無法使用，略過本次 AI 審查。"
        print(review_text)

    # 無論成功取得報告或全部滿載，只要在 GitHub Actions 環境中就自動留言回報
    if repo and sha and token:
        post_commit_comment(repo, sha, token, review_text)


def get_changed_py_files_and_diff() -> tuple[list[str], str]:
    """比對最近兩筆 Commit，取得有變動的 .py 檔案清單與 Git Diff 內容。"""
    try:
        # 1. 取得這次變動的 .py 檔案清單（排除 ai_review.py 本身）
        files_output = subprocess.check_output(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD", "--", "*.py"], text=True).strip()
    except subprocess.CalledProcessError:
        # 若為倉庫的第一筆 Commit（沒有 HEAD~1），則略過 Diff 比對
        return [], ""

    if not files_output:
        return [], ""

    changed_files = [f for f in files_output.splitlines() if f and f != "ai_review.py"]
    if not changed_files:
        return [], ""

    # 2. 只針對這些變動的 .py 檔案取得具體的程式碼差異（Diff）
    diff_content = subprocess.check_output(["git", "diff", "HEAD~1", "HEAD", "--", *changed_files], text=True).strip()
    return changed_files, diff_content


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
    # review_code("main.py")
    review_changes()
