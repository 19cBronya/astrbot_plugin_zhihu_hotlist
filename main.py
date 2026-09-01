from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain

from .zhihu_hotlist import (
    HotListItem,
    ZhihuApiError,
    ZhihuHotListClient,
    next_push_at,
    parse_push_time,
)


PLUGIN_NAME = "astrbot_plugin_zhihu_hotlist"
PLUGIN_VERSION = "0.1.1"


@register(
    PLUGIN_NAME,
    "19cBronya",
    "从知乎开放平台获取热榜，并每天定时推送到指定 UMO",
    PLUGIN_VERSION,
)
class ZhihuHotListPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._scheduler_task: asyncio.Task[Any] | None = None

    async def initialize(self) -> None:
        self._log_config_warnings()
        self._scheduler_task = asyncio.create_task(
            self._scheduler_loop(),
            name=f"{PLUGIN_NAME}:daily-push",
        )
        logger.info(
            "%s 已加载；目标 UMO 数量=%d，推送时间=%s（%s）",
            PLUGIN_NAME,
            len(self._target_umos()),
            self._cfg_str("daily_push_time", "08:00"),
            self._cfg_str("timezone", "Asia/Shanghai"),
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
            items = await self._fetch_hot_list(count or self._hot_count())
            yield event.plain_result(self._format_message(items))
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
        """Retry only pre-send failures, avoiding duplicate partial deliveries."""
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
        # Freeze the recipients first. One scheduled run owns exactly one API
        # snapshot, which is then reused for every target UMO.
        targets = self._target_umos()
        if not targets:
            logger.warning("%s 本次推送没有目标 UMO，已跳过接口请求", PLUGIN_NAME)
            return

        items = await self._fetch_hot_list(self._hot_count())
        message = self._format_message(items)
        succeeded = 0
        for umo in targets:
            try:
                await self.context.send_message(
                    umo,
                    MessageChain([Plain(message)]),
                )
                succeeded += 1
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("%s 推送到 UMO 失败：%s", PLUGIN_NAME, umo)
        logger.info(
            "%s 每日热榜推送完成：接口拉取 1 次，成功推送 %d/%d",
            PLUGIN_NAME,
            succeeded,
            len(targets),
        )

    async def _fetch_hot_list(self, count: int) -> list[HotListItem]:
        client = ZhihuHotListClient(
            token=self._cfg_str("token", ""),
            timeout_seconds=20,
        )
        return await client.fetch(max(1, min(int(count), 30)))

    def _scheduler_ready(self) -> bool:
        if not self._cfg_bool("enabled", True):
            return False
        if not self._cfg_str("token", "") or not self._target_umos():
            return False
        try:
            parse_push_time(self._cfg_str("daily_push_time", "08:00"))
            ZoneInfo(self._cfg_str("timezone", "Asia/Shanghai"))
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
            ZoneInfo(self._cfg_str("timezone", "Asia/Shanghai"))
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
        try:
            return max(1, min(int(self.config.get("hot_count", 10)), 30))
        except (TypeError, ValueError):
            return 10

    def _cfg_str(self, key: str, default: str) -> str:
        return str(self.config.get(key, default) or default).strip()

    def _cfg_bool(self, key: str, default: bool) -> bool:
        value = self.config.get(key, default)
        return value if isinstance(value, bool) else default

    def _format_message(self, items: list[HotListItem]) -> str:
        timezone_name = self._cfg_str("timezone", "Asia/Shanghai")
        now = datetime.now(ZoneInfo(timezone_name))
        lines = [f"知乎热榜 · {now:%Y-%m-%d %H:%M}"]
        for rank, item in enumerate(items, 1):
            lines.append(f"{rank}. {item.title}")
            if item.url:
                lines.append(item.url)
        lines.append("数据来源：知乎开放平台")
        return "\n".join(lines)
