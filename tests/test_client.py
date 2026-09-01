from __future__ import annotations

import pytest

from astrbot_plugin_zhihu_hotlist.zhihu_hotlist.client import (
    ZhihuApiError,
    ZhihuHotListClient,
    parse_hot_list,
)


def test_parse_official_casing_and_sanitize_fields() -> None:
    items = parse_hot_list(
        {
            "Code": 0,
            "Data": {
                "Total": 2,
                "Items": [
                    {
                        "Title": "<b>第一条</b>  热榜",
                        "Summary": "摘要&nbsp;内容",
                        "Url": "https://www.zhihu.com/question/1",
                    },
                    {
                        "Title": "第二条",
                        "Url": "javascript:alert(1)",
                    },
                ],
            },
        },
        limit=2,
    )

    assert [item.title for item in items] == ["第一条 热榜", "第二条"]
    assert items[0].summary == "摘要 内容"
    assert items[1].url == ""


def test_parse_lowercase_root_items_and_limit() -> None:
    items = parse_hot_list(
        {
            "code": 0,
            "items": [
                {"title": "一", "url": "https://www.zhihu.com/question/1"},
                {"title": "二", "url": "https://www.zhihu.com/question/2"},
            ],
        },
        limit=1,
    )
    assert [item.title for item in items] == ["一"]


def test_parse_api_error() -> None:
    with pytest.raises(ZhihuApiError, match="token 无效"):
        parse_hot_list({"Code": 401, "Message": "token 无效"})


def test_headers_use_bearer_and_unix_timestamp() -> None:
    headers = ZhihuHotListClient("secret-value")._headers()
    assert headers["Authorization"] == "Bearer secret-value"
    assert headers["X-Request-Timestamp"].isdigit()
