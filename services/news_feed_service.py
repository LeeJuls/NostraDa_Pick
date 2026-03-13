"""
RSS 뉴스 피드 수집 서비스
CNN/BBC/Reuters 등에서 최근 뉴스 헤드라인을 가져와 Gemini 프롬프트에 주입.
sports_schedule_service.py 패턴과 동일한 구조.
"""

import feedparser
from datetime import datetime, timezone, timedelta
from time import mktime


# ── 고신뢰 소스 식별자 (POLITICS/WORLD 전용 필터링에 사용) ────────────────────
HIGH_CREDIBILITY_SOURCES = {
    "bbc", "reuters", "new york times", "nytimes",
    "associated press", "ap news", "the guardian", "guardian",
}

# ── RSS 피드 목록 (무료, API 키 불필요) ──────────────────────────────────────
RSS_FEEDS = {
    # POLITICS/WORLD: 고신뢰 소스만 (BBC, Reuters, NYT, AP, Guardian)
    "world": [
        "http://feeds.bbci.co.uk/news/world/rss.xml",           # BBC World
        "https://feeds.reuters.com/Reuters/worldNews",           # Reuters World
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", # NYT World
        "https://feeds.apnews.com/rss/apf-topnews",             # AP Top News
        "https://www.theguardian.com/world/rss",                 # Guardian World
    ],
    "politics": [
        "https://feeds.reuters.com/Reuters/PoliticsNews",        # Reuters Politics
        "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml", # NYT Politics
        "https://feeds.apnews.com/rss/apf-politics",             # AP Politics
        "https://www.theguardian.com/politics/rss",              # Guardian Politics
        "http://feeds.bbci.co.uk/news/politics/rss.xml",         # BBC Politics
    ],
    "economy": [
        "https://feeds.reuters.com/reuters/businessNews",
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10001147",
    ],
    "crypto": [
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
    ],
    "tech": [
        "https://techcrunch.com/feed/",
        "https://feeds.reuters.com/reuters/technologyNews",
    ],
    "sports": [
        "http://feeds.bbci.co.uk/sport/rss.xml",
        "https://www.espn.com/espn/rss/news",
    ],
}


def _parse_published(entry) -> datetime | None:
    """RSS 엔트리에서 published 시각을 UTC datetime으로 변환"""
    if hasattr(entry, 'published_parsed') and entry.published_parsed:
        try:
            return datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)
        except Exception:
            pass
    if hasattr(entry, 'updated_parsed') and entry.updated_parsed:
        try:
            return datetime.fromtimestamp(mktime(entry.updated_parsed), tz=timezone.utc)
        except Exception:
            pass
    return None


def fetch_news_headlines(max_per_feed: int = 5, max_age_hours: int = 48) -> list[dict]:
    """
    모든 RSS 피드에서 최근 뉴스 헤드라인을 수집.

    Returns:
        [{"title": "...", "link": "https://...", "category": "world", "source": "BBC"}, ...]
    """
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(hours=max_age_hours)
    all_headlines = []

    for category, feed_urls in RSS_FEEDS.items():
        for feed_url in feed_urls:
            try:
                feed = feedparser.parse(feed_url)
                # 피드 소스명 추출 (피드 타이틀에서)
                source_name = ""
                if hasattr(feed, 'feed') and hasattr(feed.feed, 'title'):
                    source_name = feed.feed.title

                count = 0
                for entry in feed.entries:
                    if count >= max_per_feed:
                        break

                    title = getattr(entry, 'title', '').strip()
                    link = getattr(entry, 'link', '').strip()

                    if not title or not link:
                        continue

                    # 최근 뉴스만 (max_age_hours 이내)
                    pub_date = _parse_published(entry)
                    if pub_date and pub_date < cutoff:
                        continue

                    all_headlines.append({
                        "title": title,
                        "link": link,
                        "category": category,
                        "source": source_name,
                    })
                    count += 1

            except Exception as e:
                print(f"⚠️ RSS fetch failed [{category}] {feed_url}: {e}")
                continue

    print(f"📰 News: {len(all_headlines)} headline(s) collected from {sum(len(v) for v in RSS_FEEDS.values())} feeds.")
    return all_headlines


def build_news_context(headlines: list[dict]) -> str:
    """
    Gemini 프롬프트에 주입할 뉴스 헤드라인 컨텍스트 텍스트 생성.
    sports_schedule_service.build_match_context() 패턴과 동일.
    """
    if not headlines:
        return ""

    lines = ["=== RECENT NEWS HEADLINES (real-world, verified sources) ==="]
    lines.append("Use these headlines to create prediction questions about what happens NEXT.")
    lines.append("")

    # 카테고리별로 그룹화하여 출력
    from collections import defaultdict
    by_category = defaultdict(list)
    for h in headlines:
        by_category[h["category"]].append(h)

    for cat, items in by_category.items():
        is_sensitive = cat in ("world", "politics")
        label = f"[{cat.upper()}]" + (" ← HIGH-CREDIBILITY SOURCES ONLY" if is_sensitive else "")
        lines.append(label)
        for item in items:
            source_label = f"[{item['source']}] " if item.get('source') else ""
            lines.append(f"  - {source_label}{item['title']}  (url: {item['link']})")
        lines.append("")

    lines.append("=== END OF NEWS HEADLINES ===")
    return "\n".join(lines)
