from __future__ import annotations

import asyncio
import importlib
import sys
import types

from astrbot_plugin_zhihu_hotlist.zhihu_hotlist.client import HotListItem, SearchItem


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
        self.kv = {}

    async def get_kv_data(self, key, default=None):
        return self.kv.get(key, default)

    async def put_kv_data(self, key, value) -> None:
        self.kv[key] = value

    async def html_render(self, _template, _data, options=None):
        return "https://example.com/render.png"


class _Config(dict):
    pass


class _Plain:
    def __init__(self, text: str):
        self.text = text


class _Image:
    def __init__(self, source: str, remote: bool):
        self.source = source
        self.remote = remote

    @classmethod
    def fromURL(cls, source: str):
        return cls(source, True)

    @classmethod
    def fromFileSystem(cls, source: str):
        return cls(source, False)


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
        "astrbot.api.message_components": types.ModuleType(
            "astrbot.api.message_components"
        ),
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
    modules["astrbot.api.message_components"].Image = _Image
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
            enable_search=True,
            search_top_n=1,
        ),
    )
    calls = 0
    search_calls = 0

    async def fake_fetch(count: int):
        nonlocal calls
        calls += 1
        assert count == 10
        return [HotListItem("测试热榜", "https://www.zhihu.com/question/1")]

    async def fake_search(query: str, count: int):
        nonlocal search_calls
        search_calls += 1
        assert query == "测试热榜"
        assert count == 3
        return [SearchItem("相关回答", "https://www.zhihu.com/answer/1")]

    plugin._fetch_hot_list = fake_fetch
    plugin._search_zhihu = fake_search
    asyncio.run(plugin._push_daily())

    assert calls == 1
    assert search_calls == 1
    assert [umo for umo, _chain in context.sent] == ["umo:a:1", "umo:b:2"]
    assert context.sent[0][1].chain[0].text.startswith("知乎热榜")
    assert context.sent[0][1].chain[0].text == context.sent[1][1].chain[0].text


def test_daily_push_with_no_target_does_not_fetch(monkeypatch) -> None:
    module = _load_main(monkeypatch)
    plugin = module.ZhihuHotListPlugin(
        _Context(),
        _Config(target_umos=[], token="secret", timezone="Asia/Shanghai"),
    )

    async def forbidden_fetch(_count: int):
        raise AssertionError("empty target list must not consume API quota")

    plugin._fetch_hot_list = forbidden_fetch
    asyncio.run(plugin._push_daily())


def test_search_count_uses_smallest_bound(monkeypatch) -> None:
    module = _load_main(monkeypatch)

    async def run_case(actual_hot: int, configured_top: int, expected: int) -> None:
        plugin = module.ZhihuHotListPlugin(
            _Context(),
            _Config(
                enable_search=True,
                search_top_n=configured_top,
                search_results_per_topic=2,
                token="secret",
                timezone="Asia/Shanghai",
            ),
        )
        search_queries = []

        async def fake_hot(_count: int):
            return [
                HotListItem(f"热点 {index}", f"https://www.zhihu.com/question/{index}")
                for index in range(actual_hot)
            ]

        async def fake_search(query: str, count: int):
            search_queries.append((query, count))
            return [SearchItem(f"{query}结果", "https://www.zhihu.com/answer/1")]

        plugin._fetch_hot_list = fake_hot
        plugin._search_zhihu = fake_search
        bundle = await plugin._build_report(actual_hot or 1)

        assert bundle.search_requested == expected
        assert bundle.search_attempts == expected
        assert len(search_queries) == expected
        assert all(count == 2 for _query, count in search_queries)

    asyncio.run(run_case(actual_hot=4, configured_top=8, expected=4))
    asyncio.run(run_case(actual_hot=8, configured_top=3, expected=3))
    asyncio.run(run_case(actual_hot=15, configured_top=99, expected=10))


def test_daily_quota_limits_search_and_marks_unsearched_topics(monkeypatch) -> None:
    module = _load_main(monkeypatch)
    plugin = module.ZhihuHotListPlugin(
        _Context(),
        _Config(
            enable_search=True,
            search_top_n=3,
            token="secret",
            timezone="Asia/Shanghai",
        ),
    )
    plugin._reset_quota_if_new_day()
    plugin._search_quota_used = 9
    calls = 0

    async def fake_hot(_count: int):
        return [HotListItem(f"热点 {index}", "") for index in range(3)]

    async def fake_search(_query: str, _count: int):
        nonlocal calls
        calls += 1
        return []

    plugin._fetch_hot_list = fake_hot
    plugin._search_zhihu = fake_search
    bundle = asyncio.run(plugin._build_report(3))

    assert calls == 1
    assert bundle.search_attempts == 1
    assert bundle.quota_used == 10
    assert bundle.topics[0].search_note == "未找到相关结果"
    assert bundle.topics[1].search_note == "今日搜索额度不足，本条未搜索"
    assert bundle.topics[2].search_note == "今日搜索额度不足，本条未搜索"


def test_image_render_runs_once_and_builds_image_delivery(monkeypatch) -> None:
    module = _load_main(monkeypatch)
    plugin = module.ZhihuHotListPlugin(
        _Context(),
        _Config(output_mode="image", timezone="Asia/Shanghai"),
    )
    render_calls = []

    async def fake_render(template, data, options=None):
        render_calls.append((template, data, options))
        return "https://example.com/hot-list.png"

    plugin.html_render = fake_render
    bundle = module.ReportBundle(
        topics=[module.TopicReport(HotListItem("测试热榜", ""))]
    )
    delivery = asyncio.run(plugin._prepare_delivery(bundle))
    components = plugin._delivery_components(delivery)

    assert len(render_calls) == 1
    assert render_calls[0][2]["type"] == "png"
    assert delivery.image_ref == "https://example.com/hot-list.png"
    assert isinstance(components[0], _Image)
    assert components[0].remote is True


def test_image_render_failure_falls_back_to_complete_text(monkeypatch) -> None:
    module = _load_main(monkeypatch)
    plugin = module.ZhihuHotListPlugin(
        _Context(),
        _Config(output_mode="image", timezone="Asia/Shanghai"),
    )

    async def failed_render(_template, _data, options=None):
        raise RuntimeError("render unavailable")

    plugin.html_render = failed_render
    bundle = module.ReportBundle(
        topics=[module.TopicReport(HotListItem("回退测试", "https://zhihu.com/1"))]
    )
    delivery = asyncio.run(plugin._prepare_delivery(bundle))
    components = plugin._delivery_components(delivery)

    assert delivery.image_ref == ""
    assert "回退测试" in delivery.text
    assert isinstance(components[0], _Plain)


def test_legacy_image_switch_is_migrated_to_output_mode(monkeypatch) -> None:
    module = _load_main(monkeypatch)
    config = _Config(
        output_mode="text",
        render_as_image=True,
        timezone="Asia/Shanghai",
    )
    plugin = module.ZhihuHotListPlugin(_Context(), config)

    assert config["output_mode"] == "image"
    assert config["render_as_image"] is False
    assert plugin._image_output_enabled() is True
