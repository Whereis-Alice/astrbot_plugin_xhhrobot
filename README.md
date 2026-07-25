# AstrBot 小黑盒社区机器人与 LLM 工具

这是一个只依赖 AstrBot 运行的小黑盒插件。不需要额外启动 `xhhRobot`、Go 程序、HTTP 桥接服务或数据库。

插件有两部分能力：

- 后台机器人：扫码登录、轮询小黑盒 `@` 消息、读取帖子上下文，并使用 AstrBot 当前或指定人设自动回复。
- LLM 工具：让 AstrBot 的正常对话模型通过自然语言读取小黑盒，并在严格授权和确认后发帖、评论、收藏、点赞、关注、删除本人帖子或发送私信。

人设负责理解请求、组织内容和与用户确认；插件工具负责调用小黑盒接口执行真实操作。

## 功能

### 人设自动回复

1. 通过 AstrBot 管理员命令生成小黑盒登录二维码并持久化 Cookie。
2. 定时读取 `@` 消息，按消息 ID 持久化游标和去重记录。
3. 读取帖子标题、正文、话题、标签和图片。
4. 调用 AstrBot 配置的模型，注入所选人设或会话默认人设。
5. 限速发布评论回复；明确失败时退避重试，发送结果不确定时停止自动重试。

### 20 个 LLM 工具

公开读取：

- `xhh_get_feed`：社区推荐动态
- `xhh_search`：帖子、用户、游戏、标签和商城搜索
- `xhh_get_post`：帖子正文和评论
- `xhh_get_sub_comments`：子评论分页
- `xhh_get_user_profile`：用户公开资料
- `xhh_get_user_activity`：用户帖子、评论和动态
- `xhh_get_user_relations`：粉丝和关注列表
- `xhh_get_topics`：话题列表和发帖话题搜索
- `xhh_get_emojis`：表情列表

账号私密读取：

- `xhh_status`：登录、队列和工具状态
- `xhh_get_mentions`：当前账号收到的 `@` 消息
- `xhh_get_favorite_folders`：当前账号收藏夹
- `xhh_get_direct_messages`：最近私信会话和指定用户私信历史

写操作：

- `xhh_publish_post`：发布普通图文帖，支持最多两个话题和五个标签
- `xhh_create_comment`：评论帖子或回复评论
- `xhh_set_favorite`：收藏或取消收藏
- `xhh_set_like`：帖子/评论点赞或取消点赞
- `xhh_set_follow`：关注或取消关注
- `xhh_delete_post`：删除当前账号自己的帖子
- `xhh_send_direct_message`：发送私信文本和一张网络图片

小黑盒返回的帖子、评论、用户资料和私信会被标记为不可信外部内容，并按配置限制返回长度。插件不会把小黑盒公开评论直接接入 AstrBot 工具循环。

## 云服务器部署

1. 在 AstrBot WebUI 中从仓库安装插件，或把 `astrbot_plugin_xhhrobot` 文件夹放到 `data/plugins/`。
2. 安装 `requirements.txt` 中的依赖并重载插件。AstrBot 通常已包含 `aiohttp`，二维码功能还需要 `qrcode[pil]`。
3. 在插件配置中选择 `ai.provider_id` 和 `ai.persona_id`。人设留空时使用 `ai.session_umo` 对应的默认人设。
4. 配置自动回复范围：填写 `filters.allowed_user_ids`，或明确开启 `filters.allow_all_users`。
5. 在 AstrBot 已连接的平台中，由管理员发送 `/小黑盒登录`，使用手机小黑盒 App 扫码并确认。
6. 发送 `/小黑盒状态` 检查登录、后台任务和 LLM 工具状态。

仓库地址：<https://github.com/Whereis-Alice/astrbot_plugin_xhhrobot>

## 自然语言使用

读取工具无需固定命令。例如：

```text
搜索小黑盒最近讨论 AstrBot 的帖子，给我列出标题、作者和帖子 ID。
看看帖子 123456 的正文和热门评论。
查一下用户 98765 最近发了什么。
搜索可以发帖的“数码硬件”话题，告诉我 topic_id。
```

写操作建议分两轮：

```text
用户：按你现在的人设写一篇介绍 AstrBot 的小黑盒帖子，先给我预览，不要发布。
Bot：给出标题、正文、话题和标签草稿，并说明等待确认。
用户：确认执行小黑盒操作，发布刚才那一版。
Bot：调用 xhh_publish_post，返回小黑盒 link_id 或错误。
```

也可以在一条消息中提供完整内容和确认词：

```text
确认执行小黑盒操作：在帖子 123456 下评论“写得很清楚，谢谢分享”。
```

工具参数中的 `confirm=true` 不能单独放行写操作。默认还会检查用户当前原始消息是否包含 `确认执行小黑盒操作`，因此模型无法在用户没有确认时自行补一个参数完成发布。

## 工具权限

相关配置位于 `tools`：

- `enabled=true`：注册读取工具。
- `enable_write_tools=false`：写工具默认不向模型开放；需要真实写入时由管理员开启并重载插件。
- `write_admin_only=true`：写工具默认只允许 AstrBot 管理员。
- `private_tools_admin_only=true`：状态、`@`、收藏夹和私信默认只允许管理员读取。
- `allowed_astrbot_user_ids` / `allowed_umos`：关闭管理员专用后，允许指定非管理员用户或会话。留空不会放行非管理员；可显式填写 `*`。
- `require_explicit_confirmation=true`：同时校验 `confirm=true` 和原始消息确认词。
- `confirmation_keywords`：自定义高强度确认短语。不要使用单独的“确认”“好”“是”。
- `duplicate_guard_sec=120`：阻止同一消息和相同参数在短时间内重复写入。
- `write_cooldown_sec=3`：串行化并限制 LLM 写操作频率。

发帖、评论和私信工具不接受云服务器本地文件路径，只接受 HTTP(S) 图片 URL。插件会拒绝回环、私有和保留 IP，并通过小黑盒图片转存接口取得可发布 URL。

## 管理命令

所有命令要求 AstrBot 管理员权限：

- `/小黑盒帮助`
- `/小黑盒状态`
- `/小黑盒登录`
- `/小黑盒退出`
- `/小黑盒启动`
- `/小黑盒停止`
- `/小黑盒检查`
- `/小黑盒重试`
- `/小黑盒重试 确认`
- `/小黑盒测试 帖子ID 测试消息`

`/小黑盒重试 确认` 会重试无法确认是否已经发布的自动回复记录，存在重复回复风险，因此必须显式带上“确认”。

## 登录和持久化

- 二维码登录凭据、设备 ID、消息游标、待处理队列和失败记录使用 AstrBot 插件 KV 存储。
- 配置中的 `account.cookie` 只用于手动导入，推荐留空后扫码登录。
- Cookie 与账号密码等价，不要发到群聊、日志、问题反馈或公开仓库。
- 停止或卸载插件不会主动清除登录凭据和待处理队列；使用 `/小黑盒退出` 清除扫码凭据。
- 默认不会回复安装前已有的历史 `@`，只建立最新游标。确需处理历史消息时，在第一次拉取前开启 `polling.process_existing_on_first_start`。

## 风险说明

小黑盒接口不是面向第三方机器人的稳定公开 API，字段、签名、风控和发布限制可能变化。建议保持默认限速，从用户白名单和测试账号开始，关注 `/小黑盒状态` 与 AstrBot 日志。

账号受限、Cookie 失效或接口变化时，插件会把错误返回给模型或暂停自动回复，不会让 AstrBot 主进程退出。写请求发出后如网络中断，结果会标记为不确定；短期重复保护会阻止模型立即重发。

协议请求流程参考了 [SomeOvO/xhhRobot](https://github.com/SomeOvO/xhhRobot)。本插件没有运行或打包上游 Go 程序。

## 开发验证

```powershell
python -m unittest discover -s astrbot_plugin_xhhrobot/tests -t . -v
```

支持 AstrBot `>=4.16,<5`，要求 Python 3.10 或更高版本。
