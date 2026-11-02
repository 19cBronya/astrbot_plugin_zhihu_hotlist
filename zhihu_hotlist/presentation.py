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
                "rank_display": f"{rank:02d}",
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
    weekdays = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
    return {
        "generated_at": generated_at.strftime("%Y-%m-%d %H:%M"),
        "generated_date": generated_at.strftime("%Y.%m.%d"),
        "generated_time": generated_at.strftime("%H:%M"),
        "weekday": weekdays[generated_at.weekday()],
        "topic_count": len(topics),
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
html { background: #edf3fb; }
body {
  margin: 0;
  width: 920px;
  color: #15253d;
  background:
    radial-gradient(circle at 4% 3%, rgba(23, 114, 246, .11), transparent 24%),
    radial-gradient(circle at 96% 18%, rgba(103, 178, 255, .12), transparent 22%),
    #edf3fb;
  font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
  -webkit-font-smoothing: antialiased;
}
.page { padding: 32px; }
.hero {
  position: relative;
  overflow: hidden;
  min-height: 230px;
  padding: 34px 38px 32px;
  color: white;
  border-radius: 30px;
  background: linear-gradient(135deg, #0d62d7 0%, #1772f6 52%, #3d95ff 100%);
  box-shadow: 0 20px 48px rgba(20, 99, 211, .24);
}
.hero::before, .hero::after {
  content: "";
  position: absolute;
  border-radius: 999px;
  pointer-events: none;
}
.hero::before {
  width: 310px;
  height: 310px;
  top: -184px;
  right: -54px;
  border: 52px solid rgba(255, 255, 255, .10);
}
.hero::after {
  width: 160px;
  height: 160px;
  right: 148px;
  bottom: -112px;
  background: rgba(255, 255, 255, .08);
}
.hero-top, .hero-main {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.identity { display: flex; align-items: center; gap: 12px; }
.logo {
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  border-radius: 13px;
  color: #1772f6;
  background: white;
  font-family: Arial, sans-serif;
  font-size: 25px;
  line-height: 1;
  font-weight: 900;
  box-shadow: 0 8px 20px rgba(7, 54, 126, .22);
}
.identity-text { line-height: 1.15; }
.identity-cn { font-size: 17px; font-weight: 760; letter-spacing: .08em; }
.identity-en { margin-top: 4px; font-size: 10px; opacity: .72; letter-spacing: .18em; }
.date-pill {
  padding: 9px 14px;
  border: 1px solid rgba(255, 255, 255, .24);
  border-radius: 999px;
  background: rgba(255, 255, 255, .12);
  font-size: 13px;
  font-weight: 650;
  letter-spacing: .04em;
}
.hero-main { margin-top: 34px; align-items: flex-end; }
.eyebrow {
  margin-bottom: 7px;
  color: rgba(255, 255, 255, .76);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .22em;
  text-transform: uppercase;
}
.hero-title { font-size: 42px; line-height: 1.15; font-weight: 820; letter-spacing: -.03em; }
.hero-subtitle { margin-top: 9px; font-size: 15px; opacity: .78; }
.hero-stat {
  min-width: 116px;
  padding: 15px 18px 14px;
  text-align: right;
  border: 1px solid rgba(255, 255, 255, .20);
  border-radius: 20px;
  background: rgba(4, 49, 115, .16);
}
.stat-number { font-family: Arial, sans-serif; font-size: 34px; line-height: 1; font-weight: 800; }
.stat-label { margin-top: 6px; font-size: 11px; opacity: .72; letter-spacing: .14em; }
.section-head {
  margin: 28px 5px 13px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.section-title { display: flex; align-items: center; gap: 10px; font-size: 17px; font-weight: 780; }
.section-title::before {
  content: "";
  width: 5px;
  height: 20px;
  border-radius: 9px;
  background: #1772f6;
  box-shadow: 0 3px 10px rgba(23, 114, 246, .35);
}
.section-note { color: #7b8ba3; font-size: 12px; }
.list { display: grid; gap: 13px; }
.topic {
  position: relative;
  overflow: hidden;
  padding: 21px 24px 21px 21px;
  border: 1px solid rgba(202, 215, 233, .82);
  border-radius: 20px;
  background: rgba(255, 255, 255, .96);
  box-shadow: 0 8px 25px rgba(41, 72, 116, .07);
}
.topic::after {
  content: "";
  position: absolute;
  top: 0;
  right: 0;
  width: 72px;
  height: 72px;
  background: linear-gradient(225deg, rgba(23, 114, 246, .065), transparent 65%);
}
.topic-head {
  display: grid;
  grid-template-columns: 58px minmax(0, 1fr);
  gap: 17px;
  align-items: start;
}
.rank {
  width: 54px;
  height: 54px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: 17px;
  color: #1772f6;
  background: #edf5ff;
  border: 1px solid #dceaff;
}
.rank-label {
  margin-bottom: 1px;
  font-size: 8px;
  line-height: 1;
  font-weight: 800;
  letter-spacing: .14em;
  opacity: .68;
}
.rank-number {
  font-family: Arial, sans-serif;
  font-size: 21px;
  line-height: 1;
  font-weight: 850;
  letter-spacing: -.04em;
}
.topic:nth-child(1) .rank {
  color: #9a4b00;
  border-color: #ffe1a9;
  background: linear-gradient(145deg, #fff8e8, #ffebbf);
  box-shadow: 0 7px 16px rgba(238, 159, 28, .16);
}
.topic:nth-child(2) .rank {
  color: #52657c;
  border-color: #dbe4ee;
  background: linear-gradient(145deg, #f8fafc, #e9eff5);
}
.topic:nth-child(3) .rank {
  color: #8a4f2d;
  border-color: #efd5c5;
  background: linear-gradient(145deg, #fff7f2, #f4dfd3);
}
.title {
  padding-top: 2px;
  color: #13233a;
  font-size: 22px;
  line-height: 1.48;
  font-weight: 760;
  letter-spacing: -.012em;
}
.summary {
  margin: 12px 0 0 75px;
  padding-left: 14px;
  color: #64748b;
  border-left: 2px solid #dce8f8;
  font-size: 15px;
  line-height: 1.72;
}
.search {
  margin: 16px 0 0 75px;
  padding: 15px 17px;
  border: 1px solid #e0eaf7;
  border-radius: 14px;
  background: #f6f9fd;
}
.search-label {
  margin-bottom: 9px;
  color: #1772f6;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: .10em;
}
.result + .result { margin-top: 10px; padding-top: 10px; border-top: 1px solid #e0e8f2; }
.result-title { color: #25364d; font-size: 15px; line-height: 1.55; font-weight: 700; }
.author { color: #8290a4; font-size: 13px; font-weight: 500; }
.content { margin-top: 4px; color: #718096; font-size: 13px; line-height: 1.62; }
.note { color: #7b8ba3; font-size: 13px; }
.footer {
  margin-top: 22px;
  padding: 17px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #7b8ba3;
  border: 1px solid rgba(202, 215, 233, .72);
  border-radius: 16px;
  background: rgba(255, 255, 255, .62);
  font-size: 12px;
}
.footer-brand { display: flex; align-items: center; gap: 8px; color: #53647b; font-weight: 680; }
.footer-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #1772f6;
  box-shadow: 0 0 0 4px rgba(23, 114, 246, .10);
}
.footer-meta { text-align: right; }
</style>
</head>
<body>
<main class="page">
  <section class="hero">
    <div class="hero-top">
      <div class="identity">
        <div class="logo">知</div>
        <div class="identity-text">
          <div class="identity-cn">知乎热榜</div>
          <div class="identity-en">ZHIHU DAILY</div>
        </div>
      </div>
      <div class="date-pill">{{ generated_date }} · {{ weekday }}</div>
    </div>
    <div class="hero-main">
      <div>
        <div class="eyebrow">Daily Trending Brief</div>
        <div class="hero-title">今天，大家在关注什么？</div>
        <div class="hero-subtitle">更新于 {{ generated_time }} · 来源于知乎开放平台实时榜单</div>
      </div>
      <div class="hero-stat">
        <div class="stat-number">{{ topic_count }}</div>
        <div class="stat-label">HOT TOPICS</div>
      </div>
    </div>
  </section>
  <div class="section-head">
    <div class="section-title">实时热榜</div>
    <div class="section-note">按当前热度排序</div>
  </div>
  <section class="list">
  {% for topic in topics %}
    <article class="topic">
      <div class="topic-head">
        <div class="rank">
          <div class="rank-label">TOP</div>
          <div class="rank-number">{{ topic.rank_display }}</div>
        </div>
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
    <div class="footer-brand"><span class="footer-dot"></span><span>知乎每日热榜 · 自动生成</span></div>
    <div class="footer-meta">
      <span>数据来源：知乎开放平台</span>
      {% if search_enabled %}<span> · 本轮搜索 {{ search_attempts }}/{{ search_requested }} · 今日 {{ quota_used }}/{{ quota_limit }}</span>{% endif %}
    </div>
  </footer>
</main>
</body>
</html>
"""
