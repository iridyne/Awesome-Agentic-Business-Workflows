import os
import re
import httpx
import asyncio
from typing import List
from datetime import datetime
from bs4 import BeautifulSoup
from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import SystemMessage, UserMessage
from azure.core.credentials import AzureKeyCredential

# 配置区
# 使用 GitHub Models 需要 GITHUB_TOKEN，Actions 环境会自动注入，本地需手动 export
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
MODEL_NAME = "gpt-4o" # 核心逻辑推理，推荐使用 gpt-4o 或 gemini-1.5-flash
TRENDING_URL = "https://github.com/trending/python?since=daily" # 默认关注 Python/AI 领域
# 注意：路径相对于 git 根目录，Actions 运行是在根目录
README_PATH = "../README.md" 
START_MARKER = "<!-- START_HOTSPOT -->"
END_MARKER = "<!-- END_HOTSPOT -->"

class RepoItem:
    def __init__(self, name, link, desc):
        self.name = name
        self.link = link
        self.desc = desc

async def fetch_github_trending() -> List[RepoItem]:
    """抓取 GitHub Trending 数据"""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = await client.get(TRENDING_URL, headers=headers)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        repos = []
        for article in soup.select('article.Box-row'):
            title_tag = article.select_one('h2 a')
            if not title_tag: continue
            name = title_tag.get_text(strip=True).replace(" ", "")
            link = "https://github.com" + title_tag['href']
            desc_tag = article.select_one('p')
            desc = desc_tag.get_text(strip=True) if desc_tag else "No description provided."
            repos.append(RepoItem(name, link, desc))
        return repos[:15]

async def get_ai_reasoning(repos: List[RepoItem]) -> str:
    """使用 GitHub Models API 进行免费逻辑推理"""
    if not GITHUB_TOKEN:
        return "❌ Error: GITHUB_TOKEN is not set."

    client = ChatCompletionsClient(
        endpoint="https://models.inference.ai.azure.com",
        credential=AzureKeyCredential(GITHUB_TOKEN),
    )

    repo_context = "\n".join([f"- {r.name}: {r.desc} ({r.link})" for r in repos])
    
    prompt = f"""
    你是一个包豪斯(Bauhaus)风格的极简主义设计师，同时具备深厚的投资人视角。
    任务：从以下 GitHub 热点项目中精选 3-5 个最具『商业化潜力』和『工作流创新度』的项目。
    
    输出要求：
    1. 每一项严格保持以下格式：
       [Emoji] | **项目名** | 商业化潜力: [1-10]/10
       - **核心卖点**：[一行字，精准描述商业价值，禁止废话]
       - **价值拆解**：[用简练词汇描述加分/扣分项。格式：[+] 加分项; [-] 扣分项]
       - **传送门**：[URL]
    2. 视觉风格：极简、对齐、干净，强调数据的权威感。
    3. 分类标签 Emoji 规范：⚙️ 工具, 🛍️ 商业应用, 🧠 模型/AI内核, 🚀 框架/基础设施。
    4. 仅输出精选列表条目，不要任何开场白或结束语。
    5. 语言：中文。

    待分析项目：
    {repo_context}
    """

    try:
        response = client.complete(
            messages=[
                SystemMessage(content="You are a senior tech analyst specializing in identifying high-value AI open source projects."),
                UserMessage(content=prompt),
            ],
            model=MODEL_NAME,
            temperature=0.1, # 降低随机性，保证稳定性
            max_tokens=1500,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ AI Reasoning Failed: {str(e)}"

def update_readme(new_content: str):
    """精准更新 README.md 的特定区块"""
    full_readme_path = os.path.abspath(os.path.join(os.path.dirname(__file__), README_PATH))
    
    if not os.path.exists(full_readme_path):
        print(f"⚠️ README not found at {full_readme_path}, creating a placeholder.")
        with open(full_readme_path, 'w', encoding='utf-8') as f:
            f.write(f"# Awesome Agentic Workflows\n\n{START_MARKER}\n{END_MARKER}\n")

    with open(full_readme_path, 'r', encoding='utf-8') as f:
        content = f.read()

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    formatted_block = f"{START_MARKER}\n\n### 🕒 Trend Sniffed at {timestamp}\n\n{new_content.strip()}\n\n{END_MARKER}"

    # 正则替换 Marker 之间的内容
    pattern = re.compile(f"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}", re.DOTALL)
    
    if pattern.search(content):
        updated_content = pattern.sub(formatted_block, content)
    else:
        # 如果没有 Marker，则追加到末尾
        updated_content = f"{content.strip()}\n\n{formatted_block}\n"

    with open(full_readme_path, 'w', encoding='utf-8') as f:
        f.write(updated_content)

async def main():
    print("🛰️  Checking for high-potential AI items...")
    repos = await fetch_github_trending()
    
    print(f"🧠 Reasoning with GitHub Models ({MODEL_NAME})...")
    analysis = await get_ai_reasoning(repos)
    
    print("📝 Refining README.md...")
    update_readme(analysis)
    print("✨ Hotspot Sniffer completed successfully.")

if __name__ == "__main__":
    asyncio.run(main())
