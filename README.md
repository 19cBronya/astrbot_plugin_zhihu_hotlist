# astrbot_plugin_zhihu_hotlist

AstrBot 知乎热搜每日推送插件。插件基于 AstrBot 官方 `helloworld` 插件模板结构开发，通过知乎数据开放平台官方接口获取热榜，并在每天指定时间主动推送到配置的 UMO。

## 功能

- 使用知乎开放平台 `GET /api/v1/content/hot_list` 官方接口。
- 每日按指定时区和 `HH:MM` 时间推送；每轮定时任务只拉取一次热榜，并将同一份结果广播到全部 UMO。
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

只有接口拉取本身失败时才会间隔 60 秒重试，最多 3 次。单个 UMO 发送失败不会重新请求热榜，不影响其他目标，也不会重发已成功目标。手动执行 `/知乎热搜` 属于独立查询，会额外消耗一次请求。

## v0.1.1

- 明确定时任务采用“一次拉取、多 UMO 广播”。
- 推送开始前冻结目标列表，保证整轮推送复用同一份榜单。
- 日志记录单轮接口拉取次数。

## 接口与鉴权

请求地址：

```text
https://developer.zhihu.com/api/v1/content/hot_list?Limit=10
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
