import os
import yaml
import httpx
import asyncio
import json
from bs4 import BeautifulSoup
from openai import AsyncOpenAI
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

class Config(BaseModel):
    api_key: str
    base_url: str
    model: str
    github_trending_url: str
    hacker_news_url: str
    output_file: str
    threshold: int

class TrendItem(BaseModel):
    title: str
    link: str
    description: str
    source: str
    score: Optional[float] = None
    bauhaus_intro: Optional[str] = None

def load_config(path: str = "config.yaml") -> Config:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Config(**data)

class Crawler:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    async def fetch_github_trending(self, url: str) -> List[TrendItem]:
        async with httpx.AsyncClient(headers=self.headers, follow_redirects=True) as client:
            resp = await client.get(url)
            soup = BeautifulSoup(resp.text, 'html.parser')
            items = []
            for article in soup.select('article.Box-row'):
                title_tag = article.select_one('h2 a')
                # Clean title to "owner / repo" format
                raw_title = title_tag.get_text(separator=" ", strip=True)
                title = " ".join(raw_title.split())
                link = "https://github.com" + title_tag['href']
                desc_tag = article.select_one('p')
                desc = desc_tag.get_text(strip=True) if desc_tag else ""
                
                # Simple AI keyword filtering
                ai_keywords = ["ai", "llm", "agent", "gpt", "model", "transformer", "neural", "intelligence", "deepseek"]
                if any(kw in (title + desc).lower() for kw in ai_keywords):
                    items.append(TrendItem(title=title, link=link, description=desc, source="GitHub"))
            return items

    async def fetch_hacker_news(self, url: str) -> List[TrendItem]:
        async with httpx.AsyncClient(headers=self.headers) as client:
            resp = await client.get(url)
            soup = BeautifulSoup(resp.text, 'html.parser')
            items = []
            rows = soup.select('tr.athing')
                for row in rows[:30]: # Check top 30
                    title_tag = row.select_one('td.title span.titleline a')
                    if not title_tag: continue
                    title = title_tag.get_text()
                    link = title_tag['href']
                    if link.startswith('item?id='):
                        link = "https://news.ycombinator.com/" + link
                
                # HN doesn't have descriptions on the front page, just title
                ai_keywords = ["ai", "llm", "agent", "gpt", "model", "transformer", "deepseek", "claude", "openai"]
                if any(kw in title.lower() for kw in ai_keywords):
                    items.append(TrendItem(title=title, link=link, description="", source="Hacker News"))
            return items

class DeepSeekAnalyzer:
    def __init__(self, config: Config):
        self.client = AsyncOpenAI(api_key=config.api_key, base_url=config.base_url)
        self.model = config.model

    async def analyze(self, item: TrendItem) -> (float, str):
        prompt = f"""
        你是一个资深的商业分析师和技术专家。请对以下 AI 项目进行评估：
        项目名称: {item.title}
        简介: {item.description}
        来源: {item.source}

        评估标准：
        1. 商业化潜力 (0-10)
        2. 工作流创新度 (0-10)

        请给出一个综合评分 (0-10)，并生成一段符合 Bauhaus (包豪斯) 极简风格且具备商业深度的中文介绍。
        介绍要求：
        - 工具名称：[简洁名称]
        - 核心卖点：[一行字，直击痛点，去掉修饰词]
        - 价值拆解：[用简练词汇描述加分/扣分项。格式：[+] 加分项; [-] 扣分项]
        - 推荐指数：[评分]/10

        请严格按照以下 JSON 格式输出，不要包含任何其他文字：
        {{"score": 8.5, "intro": "工具名称：xxx\\n核心卖点：xxx\\n价值拆解：[+] xxx; [-] xxx\\n推荐指数：8.5/10"}}
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            res = json.loads(response.choices[0].message.content)
            return float(res.get("score", 0)), res.get("intro", "")
        except Exception as e:
            print(f"Error analyzing {item.title}: {e}")
            return 0.0, ""

async def main():
    print("🚀 Starting AI Trend Sniffer...")
    config = load_config()
    crawler = Crawler()
    analyzer = DeepSeekAnalyzer(config)

    # 1. Crawl
    print("🔍 Fetching trends...")
    github_items = await crawler.fetch_github_trending(config.github_trending_url)
    hn_items = await crawler.fetch_hacker_news(config.hacker_news_url)
    all_items = github_items + hn_items

    # 2. Analyze & Filter
    print(f"🧠 Analyzing {len(all_items)} items...")
    valid_items = []
    for item in all_items:
        score, intro = await analyzer.analyze(item)
        if score >= config.threshold:
            item.score = score
            item.bauhaus_intro = intro
            valid_items.append(item)
            print(f"✅ Found High-Potential Project: {item.title} ({score})")

    # 3. Output to README
    if valid_items:
        print(f"📝 Updating {config.output_file}...")
        with open(config.output_file, "a", encoding="utf-8") as f:
            f.write(f"\n\n## 🤖 AI 热点嗅探 ({datetime.now().strftime('%Y-%m-%d')})\n\n")
            for item in valid_items:
                f.write(f"### [{item.title}]({item.link})\n")
                f.write(f"{item.bauhaus_intro}\n\n---\n")
        print("✨ Update complete!")
    else:
        print("No items met the score threshold today.")

# End of file v2
if __name__ == "__main__":
    asyncio.run(main())
