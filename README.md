# astrbot_plugin_zhihu_hotlist

AstrBot 知乎热搜每日推送插件。插件基于 AstrBot 官方 `helloworld` 插件模板结构开发，通过知乎数据开放平台官方接口获取热榜，并在每天指定时间主动推送到配置的 UMO。

## 功能

- 使用知乎开放平台 `GET /api/v1/content/hot_list` 官方接口。
- 每日按指定时区和 `HH:MM` 时间推送；每轮定时任务只拉取一次热榜，并将同一份结果广播到全部 UMO。
- 可选使用 AstrBot 内置 `html_render` 服务，把热榜和相关搜索渲染成一张信息卡片；失败自动回退文字。
- 可选对热榜前 X 条逐条执行知乎搜索，定时推送和手动查询共享每日 10 次本地额度控制。
- 支持一个或多个精确 UMO；未配置的会话不会生效。
- `/知乎热搜 [条数]` 可在生效 UMO 中手动查询，方便验证配置。
- token 在 AstrBot 配置界面中以敏感字段显示，日志不会输出 token。
- 单次请求只访问固定的知乎 HTTPS 地址，并禁止携带 token 跟随重定向。

## 安装

将本目录放到 AstrBot 插件目录：

```text
AstrBot/data/plugins/astrbot_plugin_zhihu_hotlist/
```

重载插件。AstrBot 会根据 `requirements.txt` 安装 `aiohttp`。

## 配置

先前往 [知乎数据开放平台个人中心](https://developer.zhihu.com/profile) 获取 Access Secret，再在 AstrBot 插件配置中填写：

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `enabled` | `true` | 插件总开关 |
| `target_umos` | `[]` | 生效且接收推送的完整 UMO，可通过 `/sid` 查看 |
| `token` | 空 | 知乎 Access Secret，不含 `Bearer ` 前缀 |
| `daily_push_time` | `08:00` | 每日推送时间，24 小时制 `HH:MM` |
| `timezone` | `Asia/Shanghai` | IANA 时区名称 |
| `hot_count` | `10` | 榜单条数，允许 1–30 |
| `render_as_image` | `false` | 使用 AstrBot 渲染服务生成热榜与搜索结果图片 |
| `enable_search` | `false` | 为热榜话题附加知乎搜索结果 |
| `search_top_n` | `3` | 搜索实际热榜的前 X 条，最大 10 |
| `search_results_per_topic` | `3` | 每次搜索展示的结果数，允许 1–10；不增加请求次数 |

示例 UMO：

```text
default:FriendMessage:123456789
default:GroupMessage:987654321
```

配置列表为空或 token 为空时，插件保持加载，但不会请求接口或主动推送。

## 使用

在任一配置的生效 UMO 中发送：

```text
/知乎热搜
/知乎热搜 20
```

## 请求次数控制

每轮定时推送会先固定本轮目标 UMO 列表，只调用一次知乎热榜接口，再复用同一份消息逐个推送。因此配置 10 个 UMO 时，成功的一轮仍只消耗 1 次热榜请求，而不是 10 次。

开启搜索时，本轮实际搜索次数按以下规则计算：

```text
min(search_top_n, 实际热榜条数, 10, 今日剩余搜索额度)
```

- `search_top_n=10`、实际只返回 6 条热榜：搜索前 6 条。
- `search_top_n=3`、实际返回 20 条热榜：只搜索前 3 条。
- 希望搜索 5 条、今日只剩 2 次额度：只搜索前 2 条，其余显示“今日搜索额度不足”。
- 同一轮的搜索结果、文字排版和图片只生成一次，再广播到全部 UMO，不会按 UMO 重复搜索或渲染。

搜索用量按配置时区的自然日持久化记录，定时推送与手动 `/知乎热搜` 共享每日 10 次额度。搜索请求即使返回空结果或失败，也按已经发出的请求计入用量。`search_results_per_topic` 只控制一次请求展示几条结果，不改变请求次数。

只有热榜接口拉取失败时才会间隔 60 秒重试，最多 3 次。搜索、图片渲染或单个 UMO 发送失败都不会重新拉取热榜；渲染失败会发送完整文字结果。

## 图片渲染

开启 `render_as_image` 后，插件调用 AstrBot 官方插件 API：

```python
await self.html_render(HTML模板, 渲染数据, options={"type": "png"})
```

需要 AstrBot 的文本转图片服务可用。插件不直接依赖 Playwright，也不自行启动浏览器；远程或本地渲染策略由 AstrBot 全局配置决定。

## v0.2.0

- 新增 AstrBot `html_render` 图片模式及文字降级。
- 新增知乎搜索增强、搜索前 X 条及每话题结果数量配置。
- 新增每日 10 次搜索用量持久化控制。
- 对热榜数量、前 X 条配置和剩余额度取最小值，避免超额调用。
- 每轮只生成一份数据和图片，再广播到全部 UMO。

## v0.1.1

- 明确定时任务采用“一次拉取、多 UMO 广播”。
- 推送开始前冻结目标列表，保证整轮推送复用同一份榜单。
- 日志记录单轮接口拉取次数。

## 接口与鉴权

请求地址：

```text
https://developer.zhihu.com/api/v1/content/hot_list?Limit=10
https://developer.zhihu.com/api/v1/content/zhihu_search?Query=关键词&Count=3
```

请求包含 `Authorization: Bearer <Access Secret>` 与秒级 `X-Request-Timestamp`。请不要把 Access Secret 写入 README、日志或提交记录。

## 开发测试

```bash
python3 -m pytest -q
python3 -m compileall -q main.py zhihu_hotlist
```

测试均使用模拟响应，不需要真实 token，也不会访问网络。

## 许可证

AGPL-3.0-or-later，与 AstrBot 官方插件模板一致。
