from __future__ import annotations

import html
import json
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import aiohttp


HOT_LIST_URL = "https://developer.zhihu.com/api/v1/content/hot_list"
SEARCH_URL = "https://developer.zhihu.com/api/v1/content/zhihu_search"


class ZhihuApiError(RuntimeError):
    """A safe-to-display error returned by the Zhihu Open Platform."""


@dataclass(frozen=True, slots=True)
class HotListItem:
    title: str
    url: str
    summary: str = ""


@dataclass(frozen=True, slots=True)
class SearchItem:
    title: str
    url: str
    content: str = ""
    author: str = ""


def _text(value: Any) -> str:
    value = html.unescape(str(value or ""))
    value = re.sub(r"<[^>]+>", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _safe_http_url(value: Any) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return url
    return ""


def _api_message(payload: dict[str, Any], default: str) -> str:
    error = payload.get("error")
    if isinstance(error, dict):
        return _text(error.get("message") or error.get("code") or default)
    return _text(
        payload.get("Message")
        or payload.get("message")
        or payload.get("msg")
        or default
    )


def parse_hot_list(payload: dict[str, Any], limit: int = 30) -> list[HotListItem]:
    """Parse the documented Zhihu response while tolerating key casing changes."""
    if not isinstance(payload, dict):
        raise ZhihuApiError("知乎开放平台返回了无效数据。")

    code = payload.get("Code", payload.get("code", 0))
    if code not in (0, "0", None):
        message = _api_message(payload, "请求失败")
        raise ZhihuApiError(f"知乎开放平台请求失败：{message}（code={code}）")

    data: Any = payload.get("Data", payload.get("data", payload))
    if isinstance(data, list):
        raw_items = data
    elif isinstance(data, dict):
        raw_items = data.get("Items", data.get("items", []))
    else:
        raw_items = []

    if not isinstance(raw_items, list):
        raise ZhihuApiError("知乎开放平台热榜数据格式不正确。")

    parsed: list[HotListItem] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        title = _text(raw.get("Title", raw.get("title", "")))
        if not title:
            continue
        parsed.append(
            HotListItem(
                title=title,
                url=_safe_http_url(raw.get("Url", raw.get("url", ""))),
                summary=_text(raw.get("Summary", raw.get("summary", ""))),
            )
        )
        if len(parsed) >= max(1, min(int(limit), 30)):
            break

    if not parsed:
        raise ZhihuApiError("知乎开放平台暂未返回热榜内容。")
    return parsed


def parse_search_results(
    payload: dict[str, Any],
    limit: int = 10,
) -> list[SearchItem]:
    """Parse Zhihu search results and return an empty list for no matches."""
    if not isinstance(payload, dict):
        raise ZhihuApiError("知乎开放平台返回了无效搜索数据。")

    code = payload.get("Code", payload.get("code", 0))
    if code not in (0, "0", None):
        message = _api_message(payload, "搜索失败")
        raise ZhihuApiError(f"知乎搜索失败：{message}（code={code}）")

    data: Any = payload.get("Data", payload.get("data", payload))
    if isinstance(data, list):
        raw_items = data
    elif isinstance(data, dict):
        raw_items = data.get("Items", data.get("items", []))
    else:
        raw_items = []
    if not isinstance(raw_items, list):
        raise ZhihuApiError("知乎开放平台搜索数据格式不正确。")

    parsed: list[SearchItem] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        title = _text(raw.get("Title", raw.get("title", "")))
        if not title:
            continue
        parsed.append(
            SearchItem(
                title=title,
                url=_safe_http_url(raw.get("Url", raw.get("url", ""))),
                content=_text(
                    raw.get(
                        "ContentText",
                        raw.get("content_text", raw.get("Summary", raw.get("summary", ""))),
                    )
                ),
                author=_text(raw.get("AuthorName", raw.get("author_name", ""))),
            )
        )
        if len(parsed) >= max(1, min(int(limit), 10)):
            break
    return parsed


class ZhihuHotListClient:
    def __init__(self, token: str, timeout_seconds: int = 20) -> None:
        self.token = str(token or "").strip()
        self.timeout_seconds = max(5, min(int(timeout_seconds), 60))

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "X-Request-Timestamp": str(int(time.time())),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "astrbot-plugin-zhihu-hotlist/0.2.2",
        }

    async def _get_json(
        self,
        url: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.token:
            raise ZhihuApiError("尚未配置知乎开放平台 token。")

        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    url,
                    params=params,
                    headers=self._headers(),
                    allow_redirects=False,
                ) as response:
                    body = await response.text()
                    if response.status >= 400 or 300 <= response.status < 400:
                        detail = f"HTTP {response.status}"
                        try:
                            error_payload = json.loads(body)
                            if isinstance(error_payload, dict):
                                detail = _api_message(error_payload, detail)
                        except (TypeError, ValueError, json.JSONDecodeError):
                            pass
                        raise ZhihuApiError(f"知乎开放平台请求失败：{detail}")
                    try:
                        payload = json.loads(body)
                    except json.JSONDecodeError as exc:
                        raise ZhihuApiError("知乎开放平台返回的不是 JSON 数据。") from exc
        except ZhihuApiError:
            raise
        except TimeoutError as exc:
            raise ZhihuApiError("请求知乎开放平台超时。") from exc
        except aiohttp.ClientError as exc:
            raise ZhihuApiError(f"无法连接知乎开放平台：{exc}") from exc

        if not isinstance(payload, dict):
            raise ZhihuApiError("知乎开放平台返回了无效 JSON 数据。")
        return payload

    async def fetch(self, limit: int = 10) -> list[HotListItem]:
        limit = max(1, min(int(limit), 30))
        payload = await self._get_json(HOT_LIST_URL, {"Limit": limit})
        return parse_hot_list(payload, limit)

    async def search(self, query: str, count: int = 3) -> list[SearchItem]:
        query = str(query or "").strip()
        if not query:
            raise ValueError("知乎搜索关键词不能为空。")
        count = max(1, min(int(count), 10))
        payload = await self._get_json(
            SEARCH_URL,
            {"Query": query, "Count": count},
        )
        return parse_search_results(payload, count)
