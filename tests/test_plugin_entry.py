from __future__ import annotations

import asyncio
import importlib
import sys
import types

from astrbot_plugin_zhihu_hotlist.zhihu_hotlist.client import HotListItem


class _Logger:
    def __getattr__(self, _name):
        return lambda *_args, **_kwargs: None


class _Filter:
    @staticmethod
    def command(*_args, **_kwargs):
        return lambda function: function


class _Star:
    def __init__(self, context):
        self.context = context


class _Config(dict):
    pass


class _Plain:
    def __init__(self, text: str):
        self.text = text


class _MessageChain:
    def __init__(self, chain):
        self.chain = chain


class _Context:
    def __init__(self) -> None:
        self.sent = []

    async def send_message(self, umo, chain) -> None:
        self.sent.append((umo, chain))


def _load_main(monkeypatch):
    modules = {
        "astrbot": types.ModuleType("astrbot"),
        "astrbot.api": types.ModuleType("astrbot.api"),
        "astrbot.api.event": types.ModuleType("astrbot.api.event"),
        "astrbot.api.star": types.ModuleType("astrbot.api.star"),
        "astrbot.core": types.ModuleType("astrbot.core"),
        "astrbot.core.message": types.ModuleType("astrbot.core.message"),
        "astrbot.core.message.components": types.ModuleType(
            "astrbot.core.message.components"
        ),
        "astrbot.core.message.message_event_result": types.ModuleType(
            "astrbot.core.message.message_event_result"
        ),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    modules["astrbot.api"].AstrBotConfig = _Config
    modules["astrbot.api"].logger = _Logger()
    modules["astrbot.api.event"].AstrMessageEvent = object
    modules["astrbot.api.event"].filter = _Filter
    modules["astrbot.api.star"].Context = _Context
    modules["astrbot.api.star"].Star = _Star
    modules["astrbot.api.star"].register = lambda *_args, **_kwargs: (
        lambda plugin_class: plugin_class
    )
    modules["astrbot.core.message.components"].Plain = _Plain
    modules["astrbot.core.message.message_event_result"].MessageChain = _MessageChain

    module_name = "astrbot_plugin_zhihu_hotlist.main"
    monkeypatch.delitem(sys.modules, module_name, raising=False)
    return importlib.import_module(module_name)


def test_exact_umo_gate_and_scheduler_lifecycle(monkeypatch) -> None:
    module = _load_main(monkeypatch)
    plugin = module.ZhihuHotListPlugin(
        _Context(),
        _Config(
            enabled=True,
            target_umos=["default:FriendMessage:10001"],
            token="secret",
            daily_push_time="08:00",
            timezone="Asia/Shanghai",
        ),
    )

    assert plugin._is_effective_umo("default:FriendMessage:10001") is True
    assert plugin._is_effective_umo("default:FriendMessage:100010") is False

    async def lifecycle() -> None:
        await plugin.initialize()
        assert plugin._scheduler_task is not None
        await plugin.terminate()
        assert plugin._scheduler_task is None

    asyncio.run(lifecycle())


def test_daily_push_fetches_once_and_sends_each_target(monkeypatch) -> None:
    module = _load_main(monkeypatch)
    context = _Context()
    plugin = module.ZhihuHotListPlugin(
        context,
        _Config(
            target_umos=["umo:a:1", "umo:b:2", "umo:a:1"],
            token="secret",
            timezone="Asia/Shanghai",
            hot_count=10,
        ),
    )
    calls = 0

    async def fake_fetch(count: int):
        nonlocal calls
        calls += 1
        assert count == 10
        return [HotListItem("测试热榜", "https://www.zhihu.com/question/1")]

    plugin._fetch_hot_list = fake_fetch
    asyncio.run(plugin._push_daily())

    assert calls == 1
    assert [umo for umo, _chain in context.sent] == ["umo:a:1", "umo:b:2"]
    assert context.sent[0][1].chain[0].text.startswith("知乎热榜")
