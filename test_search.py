import json
import os

import httpx


def main() -> None:
    api_key = os.getenv("SERPER_API_KEY") or os.getenv("CLUDE_SEARCH__SERPER_API_KEY") or ""
    if not api_key:
        raise SystemExit(
            "缺少 SERPER_API_KEY（或 CLUDE_SEARCH__SERPER_API_KEY）。"
            "请先设置环境变量，再运行该脚本。"
        )

    payload = {
        "q": "学习 Transformer 模型，有哪些重要的论文？",
        "gl": "cn",
        "hl": "zh-cn",
        "num": 5,
    }
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}

    with httpx.Client(timeout=30) as client:
        r = client.post("https://google.serper.dev/search", headers=headers, content=json.dumps(payload))
        r.raise_for_status()
        data = r.json()

    # 安全：仅打印摘要，避免输出潜在敏感信息/超长内容
    organic = data.get("organic") or []
    print(f"ok=True, results={len(organic)}")
    for i, it in enumerate(organic[:5], start=1):
        print(f"{i}. {it.get('title')} - {it.get('link')}")


if __name__ == '__main__':
    main()