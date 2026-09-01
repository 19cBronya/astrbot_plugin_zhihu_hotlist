from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


PUSH_TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def parse_push_time(value: str) -> time:
    text = str(value or "").strip()
    if not PUSH_TIME_PATTERN.fullmatch(text):
        raise ValueError("每日推送时间必须使用 HH:MM 24 小时格式，例如 08:30。")
    hour, minute = (int(part) for part in text.split(":"))
    return time(hour=hour, minute=minute)


def next_push_at(
    now: datetime,
    push_time: str,
    timezone_name: str = "Asia/Shanghai",
) -> datetime:
    try:
        timezone = ZoneInfo(str(timezone_name or "Asia/Shanghai").strip())
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"无效时区：{timezone_name}") from exc

    local_now = now.astimezone(timezone)
    scheduled = datetime.combine(
        local_now.date(),
        parse_push_time(push_time),
        tzinfo=timezone,
    )
    if scheduled <= local_now:
        scheduled += timedelta(days=1)
    return scheduled
