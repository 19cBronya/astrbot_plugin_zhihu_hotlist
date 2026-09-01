from __future__ import annotations

from datetime import datetime, time, timezone

import pytest

from astrbot_plugin_zhihu_hotlist.zhihu_hotlist.schedule import (
    next_push_at,
    parse_push_time,
)


def test_parse_push_time_is_strict() -> None:
    assert parse_push_time("08:30") == time(8, 30)
    for invalid in ("8:30", "24:00", "12:60", "", "tomorrow"):
        with pytest.raises(ValueError):
            parse_push_time(invalid)


def test_next_push_is_today_before_target() -> None:
    now = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    scheduled = next_push_at(now, "09:30", "Asia/Shanghai")
    assert scheduled.isoformat() == "2026-09-01T09:30:00+08:00"


def test_next_push_rolls_to_tomorrow_at_target() -> None:
    now = datetime(2026, 9, 1, 1, 30, tzinfo=timezone.utc)
    scheduled = next_push_at(now, "09:30", "Asia/Shanghai")
    assert scheduled.isoformat() == "2026-09-02T09:30:00+08:00"
