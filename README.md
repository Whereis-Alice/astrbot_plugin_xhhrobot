# AstrBot 小黑盒bot

在 AstrBot 内完成小黑盒扫码登录、人设自动回复、自主巡帖，并把社区读取与写入能力注册为 LLM 工具。插件独立运行，不需要额外部署 `xhhRobot`、Go 服务、HTTP 桥接或数据库。

## 功能概览

- **人设自动回复**：回复小黑盒 `@` 消息，也可自动回复 bot 自己帖子下无需 `@` 的普通评论。
- **自主巡帖评论**：定时浏览推荐流，由模型按人设自主选帖、阅读正文并决定评论或跳过。
- **20 个 LLM 工具**：支持动态、搜索、帖子、评论、用户、话题、收藏、点赞、关注、私信和发帖等能力。
- **扫码登录**：由 AstrBot 管理员发起二维码登录，Cookie、设备 ID、游标和任务队列保存在插件数据中。
- **家庭网络出口**：可只让小黑盒请求通过 SOCKS5 代理，不改变 AstrBot、模型或云服务器其他流量。
- **写操作保护**：写工具默认关闭，并提供管理员权限、用户/会话允许列表、可选逐次确认、冷却和重复写入拦截。
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
| `filters.reply_to_own_post_comments` | 默认开启；允许回复 bot 自己帖子下无需 `@` 的普通评论。 |
| `auto_browse.enabled` | 默认关闭；先用 `/小黑盒逛帖 预览` 检查选帖和评论效果。 |
| `tools.require_explicit_confirmation` | 默认开启；不想每次确认时可关闭，重载插件后生效。 |
| `connection.proxy_url` | 美国等境外云服务器建议填写家庭 SOCKS5；留空表示云服务器直连。 |

配置页已经按“账号与登录、模型与人设、回复范围、轮询、自动巡帖、工具权限、通知、稳定性、高级连接”分组。每个短标签下方都有完整说明，关键安全项会直接显示提示。

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

> 后台回复直接调用 AstrBot 的 `context.llm_generate()`。`astrbot_plugin_worldbook` 的对话请求钩子不会自动注入这类后台调用；请在 `ai.persona_id` 选择包含核心设定的完整人设，并把必须遵守的规则放进 `ai.extra_system_prompt`。巡帖专用偏好可另写在 `auto_browse.extra_prompt`。

成功的自动回复和自动巡帖评论都会写入 AstrBot 后台日志，包含相关 ID、对方评论或帖子标题，以及 Bot 实际发送的文本。填写 `notifications.umo` 后，还可把告警主动发送到指定会话；开启 `notifications.notify_on_reply` 时，成功回复通知会同时列出对方评论、Bot 回复及消息/帖子/评论/用户 ID。

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
| `tools.write_admin_only` | `true` | 仅 AstrBot 管理员可执行写操作。 |
| `tools.private_tools_admin_only` | `true` | 仅管理员可读取账号私密信息。 |
| `tools.require_explicit_confirmation` | `true` | 开启时同时校验 `confirm=true` 与用户原始消息确认词；可关闭。 |
| `tools.confirmation_keywords` | 两个高强度短语 | 防止普通对话误触写入。 |
| `tools.duplicate_guard_sec` | `120` | 拦截同一消息与参数的短期重复写入。 |
| `tools.write_cooldown_sec` | `3` | 限制连续写操作频率。 |

确认开关开启时，`confirm=true` 不能单独放行写操作。插件还会检查用户当前原始消息，模型无法在用户未确认时自行补一个参数完成发布。

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
| `/小黑盒逛帖 预览` | 立即选帖并生成评论，不发布。 |
| `/小黑盒逛帖` | 自动巡帖已开启时立即执行一轮。 |

## 配置分组

| 分组 | 内容 |
| --- | --- |
| `account` | 扫码超时、可选手动 Cookie、小黑盒用户 ID 和设备 ID。 |
| `ai` | 回复模型、人设、社区约束、帖子上下文、图片和生成限制。 |
| `filters` | 普通评论回复开关、自动回复允许范围与屏蔽列表。 |
| `polling` | `@`/普通评论独立游标、分页、回复间隔和首次历史消息策略。 |
| `auto_browse` | 自主巡帖开关、频率、额度、内容筛选、作者冷却和评论限制。 |
| `tools` | LLM 工具开关、权限、确认词、限速和内容长度。 |
| `notifications` | AstrBot 主动告警目标与成功通知。 |
| `reliability` | HTTP 超时、重试、熔断和持久化记录上限。 |
| `connection` | 可选家庭 SOCKS5 代理，以及小黑盒接口地址和版本参数。 |

## 数据与更新

- 扫码凭据、设备 ID、两类消息游标、待处理队列、巡帖记录和失败记录使用 AstrBot 插件 KV 存储。
- 停止或卸载插件不会主动删除登录凭据；使用 `/小黑盒退出` 清除扫码登录信息。
- 默认不处理首次启用前已有的历史 `@` 或普通评论。确有需要时，在各自首次拉取前开启 `polling.process_existing_on_first_start`。
- `tools.enabled`、`tools.enable_write_tools` 和 `tools.require_explicit_confirmation` 会影响工具注册或 schema，修改后需要重载插件。
- 版本变化单独记录在 [changelog.md](./changelog.md)，README 不再堆叠更新历史。

## 风险说明

小黑盒接口不是面向第三方机器人的稳定公开 API，字段、签名、风控和发布限制可能变化。家庭代理也不能规避平台规则或保证账号安全。建议保持默认限速，从允许列表和测试账号开始，并关注 `/小黑盒状态` 与 AstrBot 日志。

账号受限、Cookie 失效或接口变化时，插件会返回错误或暂停自动回复，不会让 AstrBot 主进程退出。写请求发出后如网络中断，结果会被标记为不确定，默认不会自动重发。

协议请求流程参考 [SomeOvO/xhhRobot](https://github.com/SomeOvO/xhhRobot)。本插件没有运行或打包上游 Go 程序。

## 开发验证

```powershell
python -m unittest discover -s astrbot_plugin_xhhrobot/tests -t . -v
```

仓库：[Whereis-Alice/astrbot_plugin_xhhrobot](https://github.com/Whereis-Alice/astrbot_plugin_xhhrobot)
