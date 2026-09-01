from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image
from astrbot.api.star import Context, Star, register
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain

from .zhihu_hotlist import (
    HTML_TEMPLATE,
    HotListItem,
    ReportBundle,
    SearchItem,
    TopicReport,
    ZhihuApiError,
    ZhihuHotListClient,
    build_render_context,
    format_text,
    next_push_at,
    parse_push_time,
)


PLUGIN_NAME = "astrbot_plugin_zhihu_hotlist"
PLUGIN_VERSION = "0.2.1"
SEARCH_DAILY_LIMIT = 10
SEARCH_QUOTA_KEY = "zhihu_search_daily_quota_v1"


@dataclass(frozen=True, slots=True)
class Delivery:
    text: str
    image_ref: str = ""


@register(
    PLUGIN_NAME,
    "19cBronya",
    "获取知乎热榜和相关搜索，每天定时以文字或图片推送到指定 UMO",
    PLUGIN_VERSION,
)
class ZhihuHotListPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._scheduler_task: asyncio.Task[Any] | None = None
        self._quota_lock = asyncio.Lock()
        self._search_quota_date = ""
        self._search_quota_used = 0
        self._migrate_output_mode()

    async def initialize(self) -> None:
        await self._load_search_quota()
        self._log_config_warnings()
        self._scheduler_task = asyncio.create_task(
            self._scheduler_loop(),
            name=f"{PLUGIN_NAME}:daily-push",
        )
        logger.info(
            "%s 已加载；目标 UMO=%d，推送时间=%s（%s），输出=%s，搜索=%s",
            PLUGIN_NAME,
            len(self._target_umos()),
            self._cfg_str("daily_push_time", "08:00"),
            self._cfg_str("timezone", "Asia/Shanghai"),
            "图片" if self._image_output_enabled() else "文字",
            "开启" if self._cfg_bool("enable_search", False) else "关闭",
        )

    async def terminate(self) -> None:
        if self._scheduler_task is None:
            return
        self._scheduler_task.cancel()
        await asyncio.gather(self._scheduler_task, return_exceptions=True)
        self._scheduler_task = None

    @filter.command("知乎热搜")
    async def zhihu_hot_list(self, event: AstrMessageEvent, count: int = 0):
        """立即获取知乎热榜；仅在配置的生效 UMO 中可用。"""
        if not self._is_effective_umo(event.unified_msg_origin):
            return

        try:
            bundle = await self._build_report(count or self._hot_count())
            delivery = await self._prepare_delivery(bundle)
            if delivery.image_ref:
                yield event.chain_result(self._delivery_components(delivery))
            else:
                yield event.plain_result(delivery.text)
        except (ZhihuApiError, ValueError) as exc:
            yield event.plain_result(f"获取知乎热榜失败：{exc}")
        except Exception:
            logger.exception("%s 手动获取热榜失败", PLUGIN_NAME)
            yield event.plain_result("获取知乎热榜失败，请查看 AstrBot 日志。")

    async def _scheduler_loop(self) -> None:
        while True:
            try:
                if not self._scheduler_ready():
                    await asyncio.sleep(300)
                    continue

                timezone_name = self._cfg_str("timezone", "Asia/Shanghai")
                now = datetime.now(ZoneInfo(timezone_name))
                scheduled = next_push_at(
                    now,
                    self._cfg_str("daily_push_time", "08:00"),
                    timezone_name,
                )
                delay = max(0.0, (scheduled - now).total_seconds())
                logger.info(
                    "%s 下次推送时间：%s",
                    PLUGIN_NAME,
                    scheduled.isoformat(timespec="minutes"),
                )
                await asyncio.sleep(delay)
                await self._push_with_retries()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("%s 定时任务异常，5 分钟后重试调度", PLUGIN_NAME)
                await asyncio.sleep(300)

    async def _push_with_retries(self) -> None:
        """Retry only hot-list failures, avoiding duplicate partial deliveries."""
        for attempt in range(1, 4):
            try:
                await self._push_daily()
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                if attempt == 3:
                    logger.exception("%s 每日热榜连续 3 次获取失败", PLUGIN_NAME)
                    return
                logger.exception(
                    "%s 每日热榜第 %d 次获取失败，60 秒后重试",
                    PLUGIN_NAME,
                    attempt,
                )
                await asyncio.sleep(60)

    async def _push_daily(self) -> None:
        # One scheduled run owns one hot-list/search snapshot. Rendering and
        # UMO delivery reuse it and never trigger additional Zhihu requests.
        targets = self._target_umos()
        if not targets:
            logger.warning("%s 本次推送没有目标 UMO，已跳过接口请求", PLUGIN_NAME)
            return

        bundle = await self._build_report(self._hot_count())
        delivery = await self._prepare_delivery(bundle)
        succeeded = 0
        for umo in targets:
            try:
                await self.context.send_message(
                    umo,
                    MessageChain(self._delivery_components(delivery)),
                )
                succeeded += 1
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("%s 推送到 UMO 失败：%s", PLUGIN_NAME, umo)
        logger.info(
            "%s 推送完成：热榜 1 次，搜索 %d 次，渲染至多 1 次，成功 %d/%d",
            PLUGIN_NAME,
            bundle.search_attempts,
            succeeded,
            len(targets),
        )

    async def _build_report(self, count: int) -> ReportBundle:
        hot_items = await self._fetch_hot_list(count)
        topics = [TopicReport(hot=item) for item in hot_items]
        search_enabled = self._cfg_bool("enable_search", False)
        requested = min(self._search_top_n(), len(topics)) if search_enabled else 0
        attempts = await self._reserve_search_slots(requested) if requested else 0

        for index in range(attempts):
            try:
                topics[index].search_results = await self._search_zhihu(
                    topics[index].hot.title,
                    self._search_results_per_topic(),
                )
                if not topics[index].search_results:
                    topics[index].search_note = "未找到相关结果"
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                topics[index].search_note = "搜索失败，本条已跳过"
                logger.warning(
                    "%s 搜索热榜第 %d 条失败：%s",
                    PLUGIN_NAME,
                    index + 1,
                    exc,
                )

        for index in range(attempts, requested):
            topics[index].search_note = "今日搜索额度不足，本条未搜索"

        return ReportBundle(
            topics=topics,
            search_enabled=search_enabled,
            search_requested=requested,
            search_attempts=attempts,
            quota_used=self._search_quota_used,
            quota_limit=SEARCH_DAILY_LIMIT,
        )

    async def _prepare_delivery(self, bundle: ReportBundle) -> Delivery:
        generated_at = datetime.now(self._timezone())
        text = format_text(bundle, generated_at)
        if not self._image_output_enabled():
            return Delivery(text=text)

        try:
            image_ref = await self.html_render(
                HTML_TEMPLATE,
                build_render_context(bundle, generated_at),
                options={"type": "png", "timeout": 30_000},
            )
            image_ref = str(image_ref or "").strip()
            if not image_ref:
                raise RuntimeError("渲染服务返回了空地址")
            return Delivery(text=text, image_ref=image_ref)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("%s 图片渲染失败，自动回退文字消息", PLUGIN_NAME)
            return Delivery(text=text)

    @staticmethod
    def _delivery_components(delivery: Delivery) -> list[Any]:
        if not delivery.image_ref:
            return [Plain(delivery.text)]
        if delivery.image_ref.startswith(("http://", "https://")):
            return [Image.fromURL(delivery.image_ref)]
        return [Image.fromFileSystem(delivery.image_ref)]

    async def _fetch_hot_list(self, count: int) -> list[HotListItem]:
        client = self._client()
        return await client.fetch(max(1, min(int(count), 30)))

    async def _search_zhihu(self, query: str, count: int) -> list[SearchItem]:
        return await self._client().search(query, count)

    def _client(self) -> ZhihuHotListClient:
        return ZhihuHotListClient(
            token=self._cfg_str("token", ""),
            timeout_seconds=20,
        )

    async def _load_search_quota(self) -> None:
        try:
            value = await self.get_kv_data(SEARCH_QUOTA_KEY, {})
        except Exception:
            logger.exception("%s 读取搜索用量失败，将从 0 开始记录", PLUGIN_NAME)
            value = {}
        if isinstance(value, dict):
            self._search_quota_date = str(value.get("date", ""))
            try:
                self._search_quota_used = max(
                    0,
                    min(int(value.get("used", 0)), SEARCH_DAILY_LIMIT),
                )
            except (TypeError, ValueError):
                self._search_quota_used = 0
        self._reset_quota_if_new_day()

    async def _reserve_search_slots(self, requested: int) -> int:
        requested = max(0, min(int(requested), SEARCH_DAILY_LIMIT))
        async with self._quota_lock:
            self._reset_quota_if_new_day()
            remaining = max(0, SEARCH_DAILY_LIMIT - self._search_quota_used)
            granted = min(requested, remaining)
            self._search_quota_used += granted
            try:
                await self.put_kv_data(
                    SEARCH_QUOTA_KEY,
                    {
                        "date": self._search_quota_date,
                        "used": self._search_quota_used,
                    },
                )
            except Exception:
                logger.exception("%s 保存搜索用量失败", PLUGIN_NAME)
            return granted

    def _reset_quota_if_new_day(self) -> None:
        try:
            timezone = self._timezone()
        except (ValueError, KeyError):
            timezone = ZoneInfo("Asia/Shanghai")
        today = datetime.now(timezone).date().isoformat()
        if self._search_quota_date != today:
            self._search_quota_date = today
            self._search_quota_used = 0

    def _scheduler_ready(self) -> bool:
        if not self._cfg_bool("enabled", True):
            return False
        if not self._cfg_str("token", "") or not self._target_umos():
            return False
        try:
            parse_push_time(self._cfg_str("daily_push_time", "08:00"))
            self._timezone()
        except (ValueError, KeyError):
            return False
        return True

    def _log_config_warnings(self) -> None:
        if not self._target_umos():
            logger.warning("%s 尚未配置生效 UMO，不会主动推送", PLUGIN_NAME)
        if not self._cfg_str("token", ""):
            logger.warning("%s 尚未配置知乎开放平台 token，不会请求接口", PLUGIN_NAME)
        try:
            parse_push_time(self._cfg_str("daily_push_time", "08:00"))
            self._timezone()
        except (ValueError, KeyError) as exc:
            logger.error("%s 定时配置无效：%s", PLUGIN_NAME, exc)

    def _is_effective_umo(self, umo: str) -> bool:
        return self._cfg_bool("enabled", True) and umo in self._target_umos()

    def _target_umos(self) -> list[str]:
        value = self.config.get("target_umos", [])
        if not isinstance(value, list):
            return []
        return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))

    def _hot_count(self) -> int:
        return self._cfg_int("hot_count", 10, 1, 30)

    def _search_top_n(self) -> int:
        return self._cfg_int("search_top_n", 3, 1, SEARCH_DAILY_LIMIT)

    def _search_results_per_topic(self) -> int:
        return self._cfg_int("search_results_per_topic", 3, 1, 10)

    def _image_output_enabled(self) -> bool:
        return self._cfg_str("output_mode", "text").lower() == "image"

    def _migrate_output_mode(self) -> None:
        """Migrate the v0.2.0 boolean switch to the visible mode selector."""
        if not self._cfg_bool("render_as_image", False):
            return
        self.config["output_mode"] = "image"
        self.config["render_as_image"] = False
        save_config = getattr(self.config, "save_config", None)
        if callable(save_config):
            try:
                save_config()
            except Exception:
                logger.exception("%s 迁移图片输出配置失败", PLUGIN_NAME)

    def _timezone(self) -> ZoneInfo:
        return ZoneInfo(self._cfg_str("timezone", "Asia/Shanghai"))

    def _cfg_str(self, key: str, default: str) -> str:
        return str(self.config.get(key, default) or default).strip()

    def _cfg_bool(self, key: str, default: bool) -> bool:
        value = self.config.get(key, default)
        return value if isinstance(value, bool) else default

    def _cfg_int(self, key: str, default: int, low: int, high: int) -> int:
        try:
            return max(low, min(int(self.config.get(key, default)), high))
        except (TypeError, ValueError):
            return default
