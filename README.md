# AstrBot 小黑盒bot

在 AstrBot 内完成小黑盒扫码登录、人设与世界书回复、私信自动回复、自主巡帖和消息统计，并把社区读取与写入能力注册为 LLM 工具。插件独立运行，不需要额外部署 `xhhRobot`、Go 服务、HTTP 桥接或数据库服务；评论与私信记录使用插件自带的 SQLite。

## 功能概览

- **标准事件回复**：把评论和私信作为 AstrBot 消息处理，沿用人设、会话历史、世界书与其他 LLM 请求钩子。
- **评论与私信**：回复小黑盒 `@` 消息、bot 自己帖子下无需 `@` 的普通评论，以及可选的好友/陌生人私信。
- **自主巡帖评论**：定时浏览推荐流，由模型按人设自主选帖、阅读正文并决定评论或跳过。
- **LLM 工具**：默认提供 22 个动态、搜索、帖子、评论、用户、话题、收藏、点赞、关注、私信、发帖和归档工具；可单独开启 3 个本地草稿箱工具。
- **消息数据库**：自动保存评论与私信，区分原始观察、去重评论、Bot 评论和处理状态，可在 WebUI 或通过工具统计查询。
- **WebUI**：在插件页面扫码登录，查看运行状态、状态分布、分页筛选和消息详情。
- **完整图片链**：收到的评论、帖子与私信图片可交给视觉模型；回复和写工具支持网络图、本地图片与多图私信。
- **家庭网络出口**：可只让小黑盒请求通过 SOCKS5 代理，不改变 AstrBot、模型或云服务器其他流量。
- **写操作保护**：写工具默认关闭，并提供管理员权限、用户/会话允许列表、可选逐次确认、冷却和重复写入拦截。
- **故障隔离**：内置超时、指数退避、熔断、持久化队列和发送结果不确定保护。

## 快速开始

### 1. 安装

在 AstrBot WebUI 的插件市场中安装本插件，或把 `astrbot_plugin_xhhrobot` 文件夹放入 AstrBot 的 `data/plugins/`，然后安装 `requirements.txt` 中的依赖并重载插件。

支持 AstrBot `>=4.24.5,<5`，需要 Python 3.10 或更高版本。较早版本没有完整的插件 Pages 与页面 i18n 能力。

### 2. 完成基础配置

| 配置项 | 建议 |
| --- | --- |
| `ai.provider_id` | 选择用于小黑盒回复的文本模型。 |
| `ai.persona_id` | 选择 bot 已有的人设；留空时可使用 `ai.session_umo` 对应的默认人设。 |
| `event_bridge.enabled` | 建议保持开启，让评论和私信经过标准事件、世界书和消息钩子。 |
| `filters.allowed_user_ids` | 先填写测试账号的小黑盒用户 ID。 |
| `filters.allow_all_users` | 仅在确认效果和频率后再考虑开启。 |
| `filters.reply_to_own_post_comments` | 默认开启；允许回复 bot 自己帖子下无需 `@` 的普通评论。 |
| `auto_browse.enabled` | 默认关闭；先用 `/小黑盒逛帖 预览` 检查选帖和评论效果。 |
| `direct_messages.enabled` | 默认关闭；确认允许范围后再开启私信自动回复。 |
| `analytics.enabled` | 默认开启；使用内置 SQLite 归档评论并提供去重统计。 |
| `webui.show_message_content` | 不希望管理员页面显示正文时关闭，统计和 ID 仍保留。 |
| `tools.enable_draft_tools` | 默认关闭；需要让模型保存、读取或删除本地发帖草稿时开启。 |
| `tools.require_explicit_confirmation` | 默认开启；不想每次确认时可关闭，重载插件后生效。 |
| `connection.proxy_url` | 美国等境外云服务器建议填写家庭 SOCKS5；留空表示云服务器直连。 |

配置页按账号、人设、标准事件、回复范围、私信、巡帖、工具、图片、统计、WebUI、通知、稳定性和连接分组。每个短标签下方都有完整说明，关键安全项会直接显示提示。

### 3. 扫码登录

可以打开 AstrBot 插件详情中的“小黑盒bot”页面，进入“扫码登录”标签生成二维码。也可以在 AstrBot 已连接的平台中，由管理员发送：

```text
/小黑盒登录
```

使用手机小黑盒 App 扫码并确认。随后发送：

```text
/小黑盒状态
```

命令状态会显示登录来源、后台任务、回复范围、队列和 LLM 工具状态；插件页面还会显示评论/私信统计与消息明细。

> 推荐把 `account.cookie` 留空。Cookie 等同账号凭据，不要发到群聊、日志、问题反馈或公开仓库。

## 家庭网络出口

AstrBot 在美国云服务器运行时，可以让本插件的扫码、读帖、发帖、评论和私信请求统一从家里网络访问小黑盒。插件不会代理 AstrBot 平台消息、LLM 请求或服务器其他程序；代理不可用时请求会失败，不会自动回退到美国直连。

这只能降低登录地区突然变化带来的风险，不能保证账号不被风控。行为频率、设备 ID、登录状态和小黑盒自身规则仍会影响账号状态。不要使用免费或多人共享代理，也不要在家用路由器上把 `1080` 端口直接映射到公网。

### 方案一：Tailscale 私网（推荐）

先在家庭出口设备和云服务器上安装 Tailscale，并登录同一个 Tailnet。家庭宽带没有公网 IP 或处于 CGNAT 下也可以使用。家庭设备可选下面任一种部署。

#### Windows 常开电脑

下载 [GOST](https://github.com/go-gost/gost/releases) 官方 Windows 二进制，在仅当前用户可读的目录创建 `config.yaml`：

```yaml
services:
  - name: xhh-home-socks
    addr: 127.0.0.1:11080
    handler:
      type: socks5
      auth:
        username: xhhbot
        password: 换成独立强密码
      metadata:
        notls: true
    listener:
      type: tcp
```

启动 GOST，并由 Tailscale 在 Tailnet 内转发 TCP 端口：

```powershell
.\gost.exe -C .\config.yaml
tailscale serve --bg --tcp 1080 tcp://127.0.0.1:11080
tailscale ip -4
```

将 GOST 注册为当前用户登录后的计划任务并配置失败重启。GOST 只监听回环地址，`1080` 只由 Tailscale Serve 提供给 Tailnet，不需要创建公网防火墙规则。作为出口的电脑必须保持开机、联网且不进入睡眠。

#### OpenWrt 或 Linux

在家庭设备安装 `microsocks`。OpenWrt 可先尝试 `opkg update && opkg install tailscale microsocks`；具体包名以固件软件源为准。查看设备的 Tailscale IPv4，并让 SOCKS5 只监听这个地址：

```bash
tailscale ip -4
microsocks -i 100.x.x.x -p 1080 -u xhhbot -P '换成独立强密码'
```

请用 OpenWrt `procd`、`systemd` 或容器重启策略保持 `microsocks` 运行，并在 Tailscale ACL/家庭防火墙中只允许云服务器访问该端口。不要设置公网端口转发。

#### 云服务器验证

在云服务器使用家庭设备的 Tailscale IPv4 验证出口；输出应当是家里的公网 IP：

```bash
curl --proxy 'socks5h://xhhbot:密码@100.x.x.x:1080' https://api.ipify.org
```

随后在插件配置中填写并重载插件：

```text
connection.proxy_url = socks5://xhhbot:密码@100.x.x.x:1080
```

插件已固定使用代理端解析 DNS。用户名或密码含 `@`、`:`、`/` 等字符时，需要先做 URL 百分号编码。

### 方案二：SSH 反向隧道

不准备安装 Tailscale 时，可由家庭设备主动连向云服务器，适用于没有公网 IP 的家庭宽带。先让家庭 SOCKS5 仅监听本机：

```bash
microsocks -i 127.0.0.1 -p 1080
```

再从家庭设备建立反向隧道：

```bash
autossh -M 0 -N \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -R 127.0.0.1:11080:127.0.0.1:1080 \
  clouduser@你的云服务器
```

使用独立 SSH 密钥并通过 `systemd` 或 OpenWrt `procd` 保活。云服务器的 SSH 服务需允许 TCP 转发，但远端监听必须保留为 `127.0.0.1`。在云服务器验证：

```bash
curl --proxy socks5h://127.0.0.1:11080 https://api.ipify.org
```

验证是家庭公网 IP 后，将插件配置设为 `socks5://127.0.0.1:11080` 并重载。

### 账号稳定建议

- 保持插件自动生成并持久化的 `account.device_id`，不要频繁清空插件数据或重新扫码。
- 自动巡帖建议保持至少 180 分钟间隔、每天不超过 2 至 3 条评论，并保留随机浮动。
- 家庭出口中断时先恢复代理，再执行 `/小黑盒检查`；不要临时在家庭出口与云服务器直连之间反复切换。
- `/小黑盒状态` 只会显示代理是否配置，不会回显代理地址、用户名或密码。

## 自动回复规则

| 评论场景 | 是否自动回复 |
| --- | --- |
| 在任意帖子中明确 `@` bot | 用户通过允许列表/允许全部检查后回复。 |
| 在 bot 自己发布的帖子下普通评论 | `filters.reply_to_own_post_comments=true` 且用户通过范围检查后回复，无需 `@`。 |
| 在其他人的帖子下普通评论 | 不回复；仍然要求明确 `@` bot。 |
| bot 自己账号发出的评论 | 始终忽略，防止自我回复循环。 |

插件会从帖子详情再次核验作者 ID。无法确认作者，或作者不是当前登录账号时，普通评论不会发送。`@` 与普通评论使用独立游标，并以“帖子 ID + 评论 ID”二次去重，避免同一条评论从两个通知入口触发两次。

`allowed_user_ids`、`allow_all_users` 和 `blocked_user_ids` 同时作用于以上两种自动回复。默认允许列表为空，因此刚安装时不会回复任何用户。

`event_bridge.enabled` 默认开启。评论会进入 `post!帖子ID` 会话，私信会进入 `dm!用户ID` 会话，并经过 AstrBot 正常消息链。因此 `astrbot_plugin_worldbook` 在 `on_llm_request` 中注入的规则可以继续生效，通常不需要复制一份完整人设。若某条世界书规则限定了平台、会话或触发词，需要把新的 `xhhrobot` 平台与会话标识纳入条件。`ai.extra_system_prompt` 只需放小黑盒专用限制。

外部小黑盒用户 ID 会加上 `xhh:` 命名空间，不能冒充 AstrBot 管理员。小黑盒消息默认也不能调用本插件的账号工具；只有明确开启高风险项 `event_bridge.allow_llm_tools` 才会放行。

成功的自动回复和自动巡帖评论都会写入 AstrBot 后台日志，包含相关 ID、对方评论或帖子标题，以及 Bot 实际发送的文本。填写 `notifications.umo` 后，还可把告警主动发送到指定会话；开启 `notifications.notify_on_reply` 时，成功回复通知会同时列出对方评论、Bot 回复及消息/帖子/评论/用户 ID。

## 私信自动回复

私信自动回复默认关闭。开启 `direct_messages.enabled` 后，插件会随机间隔轮询好友私信；`direct_messages.reply_to_strangers` 可额外处理陌生人入口。私信与评论共用 `filters.allowed_user_ids`、`filters.allow_all_users` 和 `filters.blocked_user_ids`。

首次启用默认只建立基线，不回复当前已有的历史私信。可配置静默时段、全局与单用户 24 小时上限、单用户冷却和单轮提交数量。文本与多张图片会按小黑盒消息链分开发送；中途失败会标记为“结果不确定”，不会自动整链重发。

## 消息归档、统计与 WebUI

插件在自己的数据目录使用两个 SQLite 文件，不需要 MySQL、PostgreSQL 或其他数据库服务：

- `comment_archive.sqlite3`：保存收到的评论、平台观察记录和 Bot 发出的评论；由 `analytics.enabled` 控制。
- `direct_messages.sqlite3`：保存私信基线、待处理队列、回复正文与发送状态。

评论归档分为两类：

- `received`：从 `@` 和自己帖子普通评论入口收到的外部用户评论。
- `bot`：自动回复、自动巡帖和 `xhh_create_comment` 发出的 Bot 评论。

同一条外部评论以“帖子 ID + 平台评论 ID”作为唯一记录；不同消息入口或不同消息 ID 的重复通知作为独立原始观察保存。因此统计会同时给出 `raw_observations`、`unique_comments` 和 `duplicate_observations`。处理状态更新不会增加观察数，Bot 评论也不会混入外部用户评论数。

可以直接让模型查询：

```text
统计数据库里包含“转人妻”的评论，说明原始观察、去重、完全匹配、变体、用户、帖子和根楼数量。
查找帖子 186634750 最近 20 条收到的评论，带上评论 ID、用户 ID 和处理状态。
统计 2026-07-01 到 2026-07-26 自动回复、自动巡帖和工具评论各有多少条。
找出用户 27031296 评论过的内容，不要把 Bot 自己的回复算进去。
```

`xhh_comment_stats` 返回聚合结果；Bot 部分会再区分确认发送与发送结果不确定。`xhh_search_comment_archive` 返回具体正文和 ID。两者属于账号私密工具，默认仅 AstrBot 管理员可调用。时间筛选接受 Unix 秒时间戳或带时区的 ISO 8601；无时区值按 UTC 解释。

插件页面的“消息数据库”标签会显示去重评论、原始观察、Bot 评论、私信记录、独立用户、图片消息和各处理状态，并支持按数据集、关键词、方向、来源、状态、用户 ID、帖子 ID 分页筛选。点击一行可查看双方正文和相关 ID。关闭 `webui.show_message_content` 后只返回隐藏占位、字符数、ID、时间和状态。

浏览器只通过 AstrBot 登录态保护的插件 API 查询数据，不会收到 SQLite 路径、Cookie 或代理凭据。页面不能绕过 `analytics.enabled` 读取已关闭的评论归档。

归档只记录插件启用后实际观察到的消息，不会抓取小黑盒全部历史。评论和私信首次轮询默认只建立游标/基线；确需处理当前可见历史时，分别提前开启 `polling.process_existing_on_first_start` 或 `direct_messages.process_existing_on_first_start`。`analytics.retention_days` 默认保留 365 天，设为 `0` 表示永久保留。

## 自主巡帖

自动巡帖默认关闭。启用 `auto_browse.enabled` 后，bot 会定时读取推荐流，先从摘要候选中选帖，再读取完整正文并独立决定评论或跳过。帖子内容被视为不可信输入，不能要求模型改变规则、调用工具或泄露提示词。

建议先执行：

```text
/小黑盒逛帖 预览
```

预览会完成选帖和评论生成，但不会发布，也不占用 24 小时额度。确认效果后再开启自动发布。默认保护包括：

| 保护项 | 默认值 |
| --- | --- |
| 巡帖间隔 | 180 分钟，随机浮动 30 分钟 |
| 启动等待 | 10 分钟 |
| 单轮评论上限 | 1 条 |
| 滚动 24 小时上限 | 3 条 |
| 同作者冷却 | 72 小时 |
| 同帖子去重 | 30 天 |
| 内容保护 | 关键词、长度、网址、`@`、重复评论与提示注入检查 |

自主巡帖是明确授权的后台写入路径，独立于 `tools.enable_write_tools`，不会逐条要求聊天确认词。发送结果不确定时会停止重试并占用额度，避免重复评论。

## 自然语言调用

读取操作无需固定命令，正常和 bot 对话即可：

```text
搜索小黑盒最近讨论 AstrBot 的帖子，列出标题、作者和帖子 ID。
查看帖子 123456 的正文和热门评论。
查一下用户 98765 最近发布了什么。
搜索可以发帖的“数码硬件”话题，告诉我 topic_id。
统计评论归档里包含“AstrBot”的评论，排除 Bot 自己发出的内容。
给用户 98765 发送文字和这两张图片。
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
| `xhh_comment_stats` | 统计评论归档的原始观察、去重、正文匹配、用户、帖子和根楼数量，Bot 评论单列。 |
| `xhh_search_comment_archive` | 按关键词、时间和相关 ID 查询收到或发出的具体评论记录。 |
| `xhh_get_drafts` | 读取插件本地草稿箱的最近摘要或某篇完整草稿。仅在草稿箱开启时注册。 |

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
| `xhh_send_direct_message` | 发送私信文本与多张网络/本地图片。 |
| `xhh_save_draft` | 保存或更新插件本地的发帖草稿，不会发布到小黑盒。仅在草稿箱开启时注册。 |
| `xhh_delete_draft` | 删除插件本地草稿，不会影响已发布帖子。仅在草稿箱开启时注册。 |

除草稿读取外，写工具需要先开启 `tools.enable_write_tools`，修改后重载插件。

### 本地草稿箱

`tools.enable_draft_tools` 默认关闭。开启并重载后，模型才会看到 `xhh_get_drafts`、`xhh_save_draft` 和 `xhh_delete_draft`；关闭时三项工具不会注册，也不能通过直接调用绕过开关。

草稿保存在 AstrBot 服务器插件数据目录的 `post_drafts.sqlite3`，不上传、不同步，也不会读取小黑盒 App 自己的草稿。读取草稿按私密读取权限处理；保存和删除同时要求 `tools.enable_write_tools=true`，并继续受管理员/允许列表、冷却、重复写入和 `tools.require_explicit_confirmation` 保护。保存现有 `draft_id` 时只更新本次提供的字段，传入空字符串或空数组可以清空对应字段。

## 写操作确认

`tools.require_explicit_confirmation` 默认开启，推荐分两轮完成写入：

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

不希望每次确认时，可关闭 `tools.require_explicit_confirmation` 并重载插件。写工具会从模型 schema 中移除 `confirm` 参数和确认提示；之后只要用户明确用自然语言要求执行，模型即可直接发帖、评论或进行其他写操作。管理员/允许列表、冷却和重复写入保护仍然有效。

默认保护条件如下：

| 配置项 | 默认值 | 作用 |
| --- | --- | --- |
| `tools.enable_write_tools` | `false` | 不向模型注册写工具。 |
| `tools.enable_draft_tools` | `false` | 不注册本地草稿读取、保存和删除工具；保存/删除还需要总写入开关。 |
| `tools.write_admin_only` | `true` | 仅 AstrBot 管理员可执行写操作。 |
| `tools.private_tools_admin_only` | `true` | 仅管理员可读取账号私密信息。 |
| `tools.require_explicit_confirmation` | `true` | 开启时同时校验 `confirm=true` 与用户原始消息确认词；可关闭。 |
| `tools.confirmation_keywords` | 两个高强度短语 | 防止普通对话误触写入。 |
| `tools.duplicate_guard_sec` | `120` | 拦截同一消息与参数的短期重复写入。 |
| `tools.write_cooldown_sec` | `3` | 限制连续写操作频率。 |

确认开关开启时，`confirm=true` 不能单独放行写操作。插件还会检查用户当前原始消息，模型无法在用户未确认时自行补一个参数完成发布。

关闭管理员专用后，非管理员仍需命中 `tools.allowed_astrbot_user_ids` 或 `tools.allowed_umos`。列表留空不会放行；显式填写 `*` 才表示允许全部。

发帖、评论和私信支持公开 HTTP(S) 图片、Base64 图片以及允许目录中的本地图片。网络图片会先经小黑盒转存，本地图片会校验格式、大小和真实路径后上传到小黑盒 COS。

本地路径只允许 AstrBot 管理员通过写工具使用；标准事件回复可使用 AstrBot 或图片插件生成的本地图片。允许范围默认为插件数据目录和可选的系统临时目录，也可在 `media.allowed_local_roots` 添加云服务器目录。不要把 `/`、`C:\\` 或整个用户目录加入允许范围。

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
| `/小黑盒逛帖 预览` | 立即选帖并生成评论，不发布。 |
| `/小黑盒逛帖` | 自动巡帖已开启时立即执行一轮。 |

## 配置分组

| 分组 | 内容 |
| --- | --- |
| `account` | 扫码超时、可选手动 Cookie、小黑盒用户 ID 和设备 ID。 |
| `ai` | 回复模型、人设、社区约束、帖子上下文、图片和生成限制。 |
| `event_bridge` | 标准事件、世界书链路、并发和外部消息工具隔离。 |
| `filters` | 普通评论回复开关、自动回复允许范围与屏蔽列表。 |
| `polling` | `@`/普通评论独立游标、分页、回复间隔和首次历史消息策略。 |
| `direct_messages` | 私信开关、陌生人入口、轮询、静默时段、额度和冷却。 |
| `auto_browse` | 自主巡帖开关、频率、额度、内容筛选、作者冷却和评论限制。 |
| `tools` | LLM 工具开关、权限、确认词、限速和内容长度。 |
| `media` | 回复图片数量、本地图大小和允许上传目录。 |
| `analytics` | SQLite 消息保留时间、容量和评论查询上限。 |
| `webui` | 插件页面 API、正文显示和单页读取上限。 |
| `notifications` | AstrBot 主动告警目标与成功通知。 |
| `reliability` | HTTP 超时、重试、熔断和持久化记录上限。 |
| `connection` | 可选家庭 SOCKS5 代理，以及小黑盒接口地址和版本参数。 |

## 数据与更新

- 扫码凭据、设备 ID、评论游标、待处理队列、巡帖记录和失败记录使用 AstrBot 插件 KV 存储。
- 评论、私信和本地草稿分别保存在 `comment_archive.sqlite3`、`direct_messages.sqlite3` 与 `post_drafts.sqlite3`；数据库、WAL/SHM 文件、Cookie 和代理配置不会包含在发布安装包中。
- 停止或卸载插件不会主动删除登录凭据、统计或草稿。`/小黑盒退出` 只清除扫码凭据；彻底清除本地数据时应先停止插件，再删除对应 SQLite 主文件及同名 `-wal`、`-shm` 文件。
- 默认不处理首次启用前已有的历史 `@` 或普通评论。确有需要时，在各自首次拉取前开启 `polling.process_existing_on_first_start`。
- `tools.enabled`、`tools.enable_write_tools`、`tools.enable_draft_tools` 和 `tools.require_explicit_confirmation` 会影响工具注册或 schema，修改后需要重载插件；修改归档或 WebUI 开关也建议重载。
- 版本变化单独记录在 [changelog.md](./changelog.md)，README 不再堆叠更新历史。

## 与参考项目的关系

本插件仍是普通 AstrBot 插件，不注册新的平台适配器；但评论和私信会构造标准 AstrBot 事件。与 [advent259141/astrbot_plugin_xiaoheihe_adapter](https://github.com/advent259141/astrbot_plugin_xiaoheihe_adapter) 当前公开版本对比如下：

| 能力 | 本插件 | `astrbot_plugin_xiaoheihe_adapter` |
| --- | --- | --- |
| AstrBot 集成方式 | 普通插件后台轮询，构造标准事件，并注册 22 个基础 LLM 工具；可选开启本地草稿箱工具。 | 注册为小黑盒平台适配器，把消息提交为标准 AstrBot 事件。 |
| `@` 与帖子评论回复 | 支持，带持久化队列、重试和发送不确定保护。 | 支持，通过标准事件链交给 AstrBot 回复。 |
| 私信 | 可轮询好友/陌生人私信并作为标准私聊事件自动回复，也可由工具主动发送。 | 可轮询好友、陌生人私信并作为标准事件自动处理。 |
| 世界书等消息钩子 | 评论与私信经过标准消息链；自动巡帖仍是受控后台生成。 | 标准事件沿用 AstrBot 对话链和相关插件钩子。 |
| 收到的图片 | 评论、被回复内容、帖子和私信图片组成 AstrBot `Image` 消息链。 | 支持图片消息组件。 |
| 发出图片 | 网络图片转存、本地/Base64 图片上传 COS，支持评论和多图私信链。 | 支持本地图片上传到小黑盒 COS。 |
| 登录与状态 | 管理命令与插件 WebUI 均可扫码；WebUI 还提供运行状态和数据库统计。 | 提供插件 WebUI 扫码登录页和状态页。 |
| LLM 工具 | 22 个基础工具，含发帖、删帖、用户活动/关系、话题、收藏夹、私信和归档统计；草稿箱开启后额外 3 个本地草稿工具。 | 8 个，覆盖推荐、读帖、搜索、评论、收藏、点赞和关注。 |
| 自主巡帖 | 支持定时选帖、决策、评论、额度与风控保护。 | 提供模型逛帖工具，不负责定时自主评论。 |
| 消息数据库 | SQLite 持久归档评论与私信，支持去重、统计、筛选和 WebUI 明细。 | 提供运行状态计数与内存去重。 |
| 国际化 | 插件名称和 Page 标题提供中英文 i18n；配置和文档以中文为主。 | 带 AstrBot 插件 i18n 资源。 |

本项目的协议和接口流程参考 [SomeOvO/xhhRobot](https://github.com/SomeOvO/xhhRobot)；平台事件、私信、图片上传与 WebUI 设计参考 [advent259141/astrbot_plugin_xiaoheihe_adapter](https://github.com/advent259141/astrbot_plugin_xiaoheihe_adapter)。本插件不打包或启动这些项目。具体代码来源边界与许可证见 [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md)。

## 风险说明

小黑盒接口不是面向第三方机器人的稳定公开 API，字段、签名、风控和发布限制可能变化。家庭代理也不能规避平台规则或保证账号安全。建议保持默认限速，从允许列表和测试账号开始，并关注 `/小黑盒状态` 与 AstrBot 日志。

账号受限、Cookie 失效或接口变化时，插件会返回错误或暂停自动回复，不会让 AstrBot 主进程退出。写请求发出后如网络中断，结果会被标记为不确定，默认不会自动重发。

## 开发验证

```powershell
python -m unittest discover -s astrbot_plugin_xhhrobot/tests -t . -v
```

仓库：[Whereis-Alice/astrbot_plugin_xhhrobot](https://github.com/Whereis-Alice/astrbot_plugin_xhhrobot)
