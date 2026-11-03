# -*- coding: utf-8 -*-
"""资讯抓取任务：只读爬取新浪体育，不登录、不写入任何站点数据。

流程：
1. 依次打开配置里的列表页（新浪体育首页 + 滚动新闻列表），收集文章链接；
2. 过滤非文章链接、按 URL 去重，剔除历史文件里已出现过的链接；
3. 按时间倒序取前 N 篇，逐篇打开详情页提取 标题 / 时间 / 来源 / 正文；
4. 合并写入 data/news/YYYY-MM-DD.json（同日多次抓取会追加、去重）。
"""

import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeoutError

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = BASE_DIR / "config" / "news_sources.json"
DEFAULT_DATA_DIR = BASE_DIR / "data" / "news"

ARTICLE_URL = re.compile(
    r"^https://sports\.sina\.com\.cn/.+?/(\d{4}-\d{2}-\d{2})/doc-[0-9a-zA-Z]+\.shtml$"
)

COLLECT_JS = """() => {
    const out = [];
    for (const a of document.querySelectorAll('a[href*="doc-"]')) {
        const title = (a.textContent || '').replace(/\\s+/g, ' ').trim();
        if (!title || title.length < 4) continue;
        const li = a.closest('li');
        const raw = li ? (li.textContent || '').replace(/\\s+/g, ' ').trim() : '';
        const m = raw.match(/(\\d{2})-(\\d{2})\\s+(\\d{2}):(\\d{2})/);
        out.push({
            href: a.href,
            title: title,
            time: m ? m[1] + '-' + m[2] + ' ' + m[3] + ':' + m[4] : null
        });
    }
    return out;
}"""

DETAIL_JS = """() => {
    const node = document.querySelector('#artibody')
        || document.querySelector('.article-content')
        || document.querySelector('article');
    const pick = (s) => {
        const n = document.querySelector(s);
        return n ? (n.innerText || '').replace(/\\s+/g, ' ').trim() : '';
    };
    let body = '';
    if (node) {
        const paras = Array.from(node.querySelectorAll('p'))
            .map(p => (p.innerText || '').replace(/\\s+/g, ' ').trim())
            .filter(t => t.length > 0);
        body = paras.length ? paras.join('\\n') : (node.innerText || '').trim();
    }
    return {
        title: pick('h1.main-title') || pick('.main-title') || pick('h1'),
        date: pick('.date') || pick('.article-time') || pick('#pub_date'),
        source: pick('.source') || pick('.article-source'),
        body: body.replace(/\\n{3,}/g, '\\n\\n').trim()
    };
}"""


DEFAULT_FALLBACK_CONFIG = {
    "sources": [
        {"name": "新浪体育首页", "url": "https://sports.sina.com.cn/", "wait_seconds": 2},
        {"name": "新浪体育滚动新闻", "url": "https://sports.sina.com.cn/roll/", "wait_seconds": 4},
    ],
    "max_articles": 20,
    "delay_seconds": 1.5,
    "schedule": {"enabled": False, "time": "08:30"},
}


def load_config(path=None):
    """读取配置；文件不存在时返回内置默认来源。"""
    path = Path(path) if path else DEFAULT_CONFIG
    if not path.is_file():
        return dict(DEFAULT_FALLBACK_CONFIG)
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def save_config(config, path=None):
    """写回配置（UTF-8 无 BOM，保证 json.load 可直接读取）。"""
    path = Path(path) if path else DEFAULT_CONFIG
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)


class NewsTask:
    """资讯抓取任务，命令名 fetch。"""

    def __init__(self, worker, config_path=None, data_dir=None):
        self.worker = worker
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG
        self.data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR

    @property
    def log(self):
        return self.worker.log

    def handlers(self):
        return {"fetch": self.fetch}

    # ---------- 主流程 ----------
    def fetch(self, payload=None):
        payload = payload or {}
        config = self._load_config()
        sources = [s for s in config.get("sources", []) if s.get("enabled", True)]
        if not sources:
            self.log("配置里没有启用的资讯来源，请检查 config/news_sources.json")
            return

        max_articles = int(payload.get("max_articles") or config.get("max_articles", 20))
        delay = float(config.get("delay_seconds", 1.5))
        self.log(
            "开始抓取：%s（单次上限 %d 篇，正文间隔 %.1f 秒）"
            % ("、".join(s["name"] for s in sources), max_articles, delay)
        )

        candidates = self._collect_candidates(sources)
        if not candidates:
            self.log("没有从列表页收集到文章链接，请检查网络或页面结构")
            self._finish_browser()
            return

        known = self._load_known_urls()
        fresh = [c for c in candidates if c["url"] not in known]
        self.log(f"收集 {len(candidates)} 条、历史已存 {len(known)} 条，本次待抓取 {len(fresh)} 条")

        fresh.sort(key=lambda c: (c["time"] or "", c["url"]), reverse=True)
        fresh = fresh[:max_articles]
        if not fresh:
            self.log("没有新的文章，本次不写入")
            self._finish_browser()
            return

        page = self.worker.active_page("sina.com.cn")
        articles = []
        for index, item in enumerate(fresh, 1):
            if not self.worker.context:
                page = self.worker.open_browser(item["url"])
            self.log(f"({index}/{len(fresh)}) 抓取正文：{item['title']}")
            try:
                page.goto(item["url"], wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(800)
                detail = page.evaluate(DETAIL_JS)
            except PWTimeoutError:
                self.log(f"详情页打开超时，跳过：{item['url']}")
                continue
            article = {
                "title": (detail.get("title") or item["title"]).strip(),
                "url": item["url"],
                "time": self._normalize_date(detail.get("date")) or self._url_time(item["url"]),
                "source": (detail.get("source") or "新浪体育").strip(),
                "body": detail.get("body") or "",
                "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            if not article["body"]:
                self.log(f"未提取到正文，仍保留标题与链接：{article['title']}")
            articles.append(article)
            time.sleep(delay)

        self._save(articles)
        self._finish_browser()

    # ---------- 列表页 ----------
    def _collect_candidates(self, sources):
        page = None
        collected = {}
        for source in sources:
            url = source["url"]
            try:
                page = self.worker.open_browser(url) if page is None else page
                if page.url != url:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(int(float(source.get("wait_seconds", 2)) * 1000))
                items = page.evaluate(COLLECT_JS)
            except Exception as exc:
                self.log(f"【{source['name']}】列表页抓取失败：{exc}")
                continue

            added = 0
            for item in items:
                href = (item.get("href") or "").split("?")[0].split("#")[0]
                if not ARTICLE_URL.match(href):
                    continue
                if href in collected:
                    if not collected[href]["time"] and item.get("time"):
                        collected[href]["time"] = item["time"]
                    continue
                collected[href] = {
                    "url": href,
                    "title": item.get("title", ""),
                    "time": item.get("time"),
                    "list": source["name"],
                }
                added += 1
            self.log(f"【{source['name']}】新增 {added} 条链接")
        return list(collected.values())

    # ---------- 落盘 ----------
    def _save(self, articles):
        if not articles:
            return
        self.data_dir.mkdir(parents=True, exist_ok=True)
        day = time.strftime("%Y-%m-%d")
        path = self.data_dir / f"{day}.json"

        merged = []
        if path.exists():
            try:
                with path.open("r", encoding="utf-8-sig") as handle:
                    merged = json.load(handle).get("articles", [])
            except (json.JSONDecodeError, OSError) as exc:
                self.log(f"读取历史文件失败，将覆盖为新文件：{exc}")
                merged = []

        seen = {item.get("url") for item in merged}
        added = [a for a in articles if a["url"] not in seen]
        merged.extend(added)
        merged.sort(key=lambda a: a.get("time") or "", reverse=True)

        payload = {
            "date": day,
            "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source": "sports.sina.com.cn",
            "count": len(merged),
            "added": len(added),
            "articles": merged,
        }
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        self.log(f"已写入 {path}：新增 {len(added)} 条，本日累计 {len(merged)} 条")

    def _load_known_urls(self):
        if not self.data_dir.is_dir():
            return set()
        known = set()
        for path in sorted(self.data_dir.glob("*.json")):
            try:
                with path.open("r", encoding="utf-8-sig") as handle:
                    for item in json.load(handle).get("articles", []):
                        if item.get("url"):
                            known.add(item["url"])
            except (json.JSONDecodeError, OSError):
                continue
        return known

    # ---------- 工具 ----------
    def _load_config(self):
        if not self.config_path.is_file():
            self.log(f"未找到配置文件 {self.config_path}，使用内置默认来源")
            return dict(DEFAULT_FALLBACK_CONFIG)
        try:
            return load_config(self.config_path)
        except json.JSONDecodeError as exc:
            self.log(f"配置文件格式有误，改用内置默认来源：{exc}")
            return dict(DEFAULT_FALLBACK_CONFIG)

    def _finish_browser(self):
        self.worker.close_browser()

    @staticmethod
    def _url_time(url):
        match = ARTICLE_URL.match(url)
        return match.group(1) if match else ""

    @staticmethod
    def _normalize_date(text):
        """把 2026年11月03日 22:07 / 11-03 22:07 统一成 2026-11-03 22:07。"""
        text = (text or "").strip()
        if not text:
            return ""
        match = re.search(
            r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?\s*(\d{1,2}):(\d{2})", text
        )
        if match:
            year, month, day, hour, minute = match.groups()
            return f"{year}-{int(month):02d}-{int(day):02d} {int(hour):02d}:{minute}"
        match = re.search(r"(\d{2})-(\d{2})\s+(\d{2}):(\d{2})", text)
        if match:
            month, day, hour, minute = (int(v) for v in match.groups())
            now = datetime.now()
            year = now.year
            guess = datetime(year, month, day, hour, minute)
            if guess - now > timedelta(days=1):  # 跨年
                year -= 1
            return f"{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"
        return text
