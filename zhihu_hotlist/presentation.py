from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime

from .client import HotListItem, SearchItem


@dataclass(slots=True)
class TopicReport:
    hot: HotListItem
    search_results: list[SearchItem] = field(default_factory=list)
    search_note: str = ""


@dataclass(slots=True)
class ReportBundle:
    topics: list[TopicReport]
    search_enabled: bool = False
    search_requested: int = 0
    search_attempts: int = 0
    quota_used: int = 0
    quota_limit: int = 10


def _truncate(value: str, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def format_text(bundle: ReportBundle, generated_at: datetime) -> str:
    lines = [f"知乎热榜 · {generated_at:%Y-%m-%d %H:%M}"]
    for rank, topic in enumerate(bundle.topics, 1):
        lines.append(f"\n{rank}. {topic.hot.title}")
        if topic.hot.url:
            lines.append(topic.hot.url)
        if topic.hot.summary:
            lines.append(f"热榜摘要：{_truncate(topic.hot.summary, 180)}")
        if topic.search_results:
            lines.append("相关知乎搜索：")
            for result_index, result in enumerate(topic.search_results, 1):
                author = f" · {result.author}" if result.author else ""
                lines.append(f"  {result_index}) {result.title}{author}")
                if result.url:
                    lines.append(f"     {result.url}")
                if result.content:
                    lines.append(f"     {_truncate(result.content, 160)}")
        elif topic.search_note:
            lines.append(f"相关知乎搜索：{topic.search_note}")

    if bundle.search_enabled:
        lines.append(
            "\n本轮搜索："
            f"请求 {bundle.search_attempts}/{bundle.search_requested} 次；"
            f"今日用量 {bundle.quota_used}/{bundle.quota_limit}"
        )
    lines.append("数据来源：知乎开放平台")
    return "\n".join(lines)


def build_render_context(bundle: ReportBundle, generated_at: datetime) -> dict:
    topics = []
    for rank, topic in enumerate(bundle.topics, 1):
        topics.append(
            {
                "rank": rank,
                "title": html.escape(topic.hot.title),
                "summary": html.escape(_truncate(topic.hot.summary, 220)),
                "search_note": html.escape(topic.search_note),
                "search_results": [
                    {
                        "title": html.escape(result.title),
                        "author": html.escape(result.author),
                        "content": html.escape(_truncate(result.content, 180)),
                    }
                    for result in topic.search_results
                ],
            }
        )
    return {
        "generated_at": generated_at.strftime("%Y-%m-%d %H:%M"),
        "topics": topics,
        "search_enabled": bundle.search_enabled,
        "search_requested": bundle.search_requested,
        "search_attempts": bundle.search_attempts,
        "quota_used": bundle.quota_used,
        "quota_limit": bundle.quota_limit,
    }


HTML_TEMPLATE = r"""
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
* { box-sizing: border-box; }
body {
  margin: 0;
  width: 860px;
  color: #182230;
  background: #f3f5f8;
  font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
}
.page { padding: 38px; }
.header {
  padding: 30px 32px;
  color: white;
  border-radius: 24px;
  background: linear-gradient(135deg, #056de8 0%, #3b8cff 58%, #74b2ff 100%);
  box-shadow: 0 12px 34px rgba(5, 109, 232, .22);
}
.brand { font-size: 38px; font-weight: 800; letter-spacing: 1px; }
.time { margin-top: 7px; font-size: 17px; opacity: .88; }
.list { margin-top: 22px; display: grid; gap: 16px; }
.topic {
  padding: 23px 25px;
  border: 1px solid #e4e8ef;
  border-radius: 20px;
  background: white;
  box-shadow: 0 5px 18px rgba(24, 34, 48, .055);
}
.topic-head { display: flex; gap: 17px; align-items: flex-start; }
.rank {
  flex: 0 0 44px;
  width: 44px;
  height: 44px;
  border-radius: 14px;
  color: #056de8;
  background: #eaf3ff;
  text-align: center;
  line-height: 44px;
  font-size: 21px;
  font-weight: 800;
}
.topic:nth-child(-n+3) .rank { color: white; background: #056de8; }
.title { padding-top: 3px; font-size: 23px; line-height: 1.5; font-weight: 720; }
.summary { margin: 12px 0 0 61px; color: #667085; font-size: 16px; line-height: 1.7; }
.search {
  margin: 17px 0 0 61px;
  padding: 15px 17px;
  border-radius: 14px;
  background: #f7f9fc;
  border-left: 4px solid #84b9f6;
}
.search-label { margin-bottom: 9px; color: #056de8; font-size: 15px; font-weight: 750; }
.result + .result { margin-top: 11px; padding-top: 11px; border-top: 1px solid #e6eaf0; }
.result-title { font-size: 16px; line-height: 1.55; font-weight: 680; }
.author { color: #7b8492; font-size: 14px; font-weight: 500; }
.content { margin-top: 4px; color: #667085; font-size: 14px; line-height: 1.6; }
.note { color: #7b8492; font-size: 15px; }
.footer {
  margin-top: 22px;
  padding: 0 6px;
  display: flex;
  justify-content: space-between;
  color: #7b8492;
  font-size: 14px;
}
</style>
</head>
<body>
<main class="page">
  <section class="header">
    <div class="brand">知乎热榜</div>
    <div class="time">{{ generated_at }} · 每轮热榜仅拉取一次</div>
  </section>
  <section class="list">
  {% for topic in topics %}
    <article class="topic">
      <div class="topic-head">
        <div class="rank">{{ topic.rank }}</div>
        <div class="title">{{ topic.title | safe }}</div>
      </div>
      {% if topic.summary %}<div class="summary">{{ topic.summary | safe }}</div>{% endif %}
      {% if topic.search_results or topic.search_note %}
      <div class="search">
        <div class="search-label">相关知乎搜索</div>
        {% for result in topic.search_results %}
        <div class="result">
          <div class="result-title">{{ result.title | safe }}{% if result.author %}<span class="author"> · {{ result.author | safe }}</span>{% endif %}</div>
          {% if result.content %}<div class="content">{{ result.content | safe }}</div>{% endif %}
        </div>
        {% endfor %}
        {% if topic.search_note %}<div class="note">{{ topic.search_note | safe }}</div>{% endif %}
      </div>
      {% endif %}
    </article>
  {% endfor %}
  </section>
  <footer class="footer">
    <span>数据来源：知乎开放平台</span>
    {% if search_enabled %}<span>本轮搜索 {{ search_attempts }}/{{ search_requested }} · 今日 {{ quota_used }}/{{ quota_limit }}</span>{% endif %}
  </footer>
</main>
</body>
</html>
"""
