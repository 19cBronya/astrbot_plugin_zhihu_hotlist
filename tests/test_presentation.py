from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from astrbot_plugin_zhihu_hotlist.zhihu_hotlist.client import HotListItem, SearchItem
from astrbot_plugin_zhihu_hotlist.zhihu_hotlist.presentation import (
    HTML_TEMPLATE,
    ReportBundle,
    TopicReport,
    build_render_context,
)


def test_render_context_contains_header_metadata_and_escaped_content() -> None:
    bundle = ReportBundle(
        topics=[
            TopicReport(
                hot=HotListItem("<热点>", "", "包含 <script> 的摘要"),
                search_results=[SearchItem("<回答>", "", "内容", "<作者>")],
            )
        ],
        search_enabled=True,
        search_requested=1,
        search_attempts=1,
        quota_used=2,
    )
    generated_at = datetime(2026, 11, 2, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    context = build_render_context(bundle, generated_at)

    assert context["generated_date"] == "2026.11.02"
    assert context["generated_time"] == "08:00"
    assert context["weekday"] == "星期一"
    assert context["topic_count"] == 1
    assert context["topics"][0]["rank_display"] == "01"
    assert context["topics"][0]["title"] == "&lt;热点&gt;"
    assert "&lt;script&gt;" in context["topics"][0]["summary"]
    assert context["topics"][0]["search_results"][0]["author"] == "&lt;作者&gt;"


def test_image_template_is_self_contained_and_has_new_visual_hierarchy() -> None:
    assert "http://" not in HTML_TEMPLATE
    assert "https://" not in HTML_TEMPLATE
    assert "@import" not in HTML_TEMPLATE
    assert "Daily Trending Brief" in HTML_TEMPLATE
    assert "rank-number" in HTML_TEMPLATE
    assert "footer-brand" in HTML_TEMPLATE
