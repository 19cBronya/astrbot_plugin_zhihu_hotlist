"""Core helpers for the Zhihu hot-list plugin."""

from .client import (
    HotListItem,
    SearchItem,
    ZhihuApiError,
    ZhihuHotListClient,
    parse_hot_list,
    parse_search_results,
)
from .schedule import next_push_at, parse_push_time
from .presentation import (
    HTML_TEMPLATE,
    ReportBundle,
    TopicReport,
    build_render_context,
    format_text,
)

__all__ = [
    "HotListItem",
    "HTML_TEMPLATE",
    "ReportBundle",
    "SearchItem",
    "TopicReport",
    "ZhihuApiError",
    "ZhihuHotListClient",
    "next_push_at",
    "build_render_context",
    "format_text",
    "parse_hot_list",
    "parse_search_results",
    "parse_push_time",
]
