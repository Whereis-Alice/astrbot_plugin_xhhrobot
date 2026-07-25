# AstrBot 小黑盒bot

在 AstrBot 内完成小黑盒扫码登录、人设自动回复，并把社区读取与写入能力注册为 LLM 工具。插件独立运行，不需要额外部署 `xhhRobot`、Go 服务、HTTP 桥接或数据库。

## 功能概览

- **人设自动回复**：轮询小黑盒 `@` 消息，读取帖子正文和图片，调用指定的 AstrBot 模型与人设生成回复。
- **20 个 LLM 工具**：支持动态、搜索、帖子、评论、用户、话题、收藏、点赞、关注、私信和发帖等能力。
- **扫码登录**：由 AstrBot 管理员发起二维码登录，Cookie、设备 ID、游标和任务队列保存在插件数据中。
- **写操作保护**：写工具默认关闭，并提供管理员权限、用户/会话允许列表、原始消息确认词、冷却和重复写入拦截。
- **故障隔离**：内置超时、指数退避、熔断、持久化队列和发送结果不确定保护。

## 快速开始

### 1. 安装

在 AstrBot WebUI 的插件市场中安装本插件，或把 `astrbot_plugin_xhhrobot` 文件夹放入 AstrBot 的 `data/plugins/`，然后安装 `requirements.txt` 中的依赖并重载插件。

支持 AstrBot `>=4.16,<5`，需要 Python 3.10 或更高版本。

### 2. 完成基础配置

| 配置项 | 建议 |
| --- | --- |
| `ai.provider_id` | 选择用于小黑盒回复的文本模型。 |
| `ai.persona_id` | 选择 bot 已有的人设；留空时可使用 `ai.session_umo` 对应的默认人设。 |
| `filters.allowed_user_ids` | 先填写测试账号的小黑盒用户 ID。 |
| `filters.allow_all_users` | 仅在确认效果和频率后再考虑开启。 |

配置页已经按“账号与登录、模型与人设、回复范围、轮询、工具权限、通知、稳定性、高级连接”分组。每个短标签下方都有完整说明，关键安全项会直接显示提示。

### 3. 扫码登录

在 AstrBot 已连接的平台中，由管理员发送：

```text
/小黑盒登录
```

使用手机小黑盒 App 扫码并确认。随后发送：

```text
/小黑盒状态
```

状态页会显示登录来源、后台任务、回复范围、队列和 LLM 工具状态。

> 推荐把 `account.cookie` 留空。Cookie 等同账号凭据，不要发到群聊、日志、问题反馈或公开仓库。

## 自然语言调用

读取操作无需固定命令，正常和 bot 对话即可：

```text
搜索小黑盒最近讨论 AstrBot 的帖子，列出标题、作者和帖子 ID。
查看帖子 123456 的正文和热门评论。
查一下用户 98765 最近发布了什么。
搜索可以发帖的“数码硬件”话题，告诉我 topic_id。
```

模型会根据问题选择工具。小黑盒返回的帖子、评论、用户资料和私信会被标记为不可信外部内容，并按配置限制返回长度。

## LLM 工具

### 公开读取

| 工具 | 能力 |
| --- | --- |
| `xhh_get_feed` | 获取社区推荐动态。 |
| `xhh_search` | 搜索帖子、用户、游戏、标签和商城内容。 |
| `xhh_get_post` | 获取帖子正文和评论。 |
| `xhh_get_sub_comments` | 分页获取子评论。 |
| `xhh_get_user_profile` | 获取用户公开资料。 |
| `xhh_get_user_activity` | 获取用户帖子、评论和动态。 |
| `xhh_get_user_relations` | 获取粉丝和关注列表。 |
| `xhh_get_topics` | 获取话题列表或搜索发帖话题。 |
| `xhh_get_emojis` | 获取小黑盒表情列表。 |

### 账号私密读取

| 工具 | 能力 |
| --- | --- |
| `xhh_status` | 查看登录、后台队列和工具状态。 |
| `xhh_get_mentions` | 获取当前账号收到的 `@` 消息。 |
| `xhh_get_favorite_folders` | 获取当前账号的收藏夹。 |
| `xhh_get_direct_messages` | 获取最近私信会话或指定用户的私信历史。 |

私密读取工具默认仅允许 AstrBot 管理员调用。

### 写操作

| 工具 | 能力 |
| --- | --- |
| `xhh_publish_post` | 发布普通图文帖，最多两个话题、五个标签。 |
| `xhh_create_comment` | 评论帖子或回复评论。 |
| `xhh_set_favorite` | 收藏或取消收藏。 |
| `xhh_set_like` | 点赞或取消帖子/评论点赞。 |
| `xhh_set_follow` | 关注或取消关注用户。 |
| `xhh_delete_post` | 删除当前账号自己发布的帖子。 |
| `xhh_send_direct_message` | 发送私信文本和一张网络图片。 |

写工具需要先开启 `tools.enable_write_tools`，修改后重载插件。

## 写操作确认

推荐分两轮完成写入：

```text
用户：按你现在的人设写一篇介绍 AstrBot 的小黑盒帖子，先给我预览，不要发布。
Bot：返回标题、正文、话题和标签草稿，等待用户确认。
用户：确认执行小黑盒操作，发布刚才那一版。
Bot：调用 xhh_publish_post，并返回 link_id 或错误。
```

也可以在一条消息中提供完整内容和确认词：

```text
确认执行小黑盒操作：在帖子 123456 下评论“写得很清楚，谢谢分享”。
```

默认保护条件如下：

| 配置项 | 默认值 | 作用 |
| --- | --- | --- |
| `tools.enable_write_tools` | `false` | 不向模型注册写工具。 |
| `tools.write_admin_only` | `true` | 仅 AstrBot 管理员可执行写操作。 |
| `tools.private_tools_admin_only` | `true` | 仅管理员可读取账号私密信息。 |
| `tools.require_explicit_confirmation` | `true` | 同时校验工具参数 `confirm=true` 与用户原始消息确认词。 |
| `tools.confirmation_keywords` | 两个高强度短语 | 防止普通对话误触写入。 |
| `tools.duplicate_guard_sec` | `120` | 拦截同一消息与参数的短期重复写入。 |
| `tools.write_cooldown_sec` | `3` | 限制连续写操作频率。 |

`confirm=true` 不能单独放行写操作。插件还会检查用户当前原始消息，模型无法在用户未确认时自行补一个参数完成发布。

关闭管理员专用后，非管理员仍需命中 `tools.allowed_astrbot_user_ids` 或 `tools.allowed_umos`。列表留空不会放行；显式填写 `*` 才表示允许全部。

发帖、评论和私信只接受 HTTP(S) 图片 URL，不接受云服务器本地文件路径。插件会拒绝回环、私有和保留 IP，并先通过小黑盒图片转存接口取得可发布 URL。

## 管理命令

以下命令都要求 AstrBot 管理员权限：

| 命令 | 作用 |
| --- | --- |
| `/小黑盒帮助` | 显示命令帮助。 |
| `/小黑盒状态` | 查看登录、轮询、队列和工具状态。 |
| `/小黑盒登录` | 发起二维码扫码登录。 |
| `/小黑盒退出` | 清除扫码登录凭据并停止任务。 |
| `/小黑盒启动` | 启动后台轮询。 |
| `/小黑盒停止` | 停止后台轮询。 |
| `/小黑盒检查` | 立即执行一轮检查。 |
| `/小黑盒重试` | 重试明确失败且可安全重试的记录。 |
| `/小黑盒重试 确认` | 包含发送结果不确定的记录，存在重复回复风险。 |
| `/小黑盒测试 帖子ID 测试消息` | 用指定帖子和文本测试生成人设回复。 |

## 配置分组

| 分组 | 内容 |
| --- | --- |
| `account` | 扫码超时、可选手动 Cookie、小黑盒用户 ID 和设备 ID。 |
| `ai` | 回复模型、人设、社区约束、帖子上下文、图片和生成限制。 |
| `filters` | 自动回复允许范围与屏蔽列表。 |
| `polling` | 轮询、分页、回复间隔和首次历史消息策略。 |
| `tools` | LLM 工具开关、权限、确认词、限速和内容长度。 |
| `notifications` | AstrBot 主动告警目标与成功通知。 |
| `reliability` | HTTP 超时、重试、熔断和持久化记录上限。 |
| `connection` | 小黑盒接口地址与版本参数，通常保持默认。 |

## 数据与更新

- 扫码凭据、设备 ID、消息游标、待处理队列和失败记录使用 AstrBot 插件 KV 存储。
- 停止或卸载插件不会主动删除登录凭据；使用 `/小黑盒退出` 清除扫码登录信息。
- 默认不处理安装前已有的历史 `@`。确有需要时，在首次拉取前开启 `polling.process_existing_on_first_start`。
- `tools.enabled` 和 `tools.enable_write_tools` 控制工具注册，修改后需要重载插件。

## 风险说明

小黑盒接口不是面向第三方机器人的稳定公开 API，字段、签名、风控和发布限制可能变化。建议保持默认限速，从允许列表和测试账号开始，并关注 `/小黑盒状态` 与 AstrBot 日志。

账号受限、Cookie 失效或接口变化时，插件会返回错误或暂停自动回复，不会让 AstrBot 主进程退出。写请求发出后如网络中断，结果会被标记为不确定，默认不会自动重发。

协议请求流程参考 [SomeOvO/xhhRobot](https://github.com/SomeOvO/xhhRobot)。本插件没有运行或打包上游 Go 程序。

## 开发验证

```powershell
python -m unittest discover -s astrbot_plugin_xhhrobot/tests -t . -v
```

仓库：[Whereis-Alice/astrbot_plugin_xhhrobot](https://github.com/Whereis-Alice/astrbot_plugin_xhhrobot)
