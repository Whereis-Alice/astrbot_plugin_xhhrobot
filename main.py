from __future__ import annotations

import asyncio
import contextlib
import inspect
import re
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import qrcode
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, StarTools

from .models import AuthInfo, Mention, PostContext, QrChallenge
from .state_store import StateStore
from .tools import XhhToolRuntime
from .xhh_client import XhhClient, XhhError

PLUGIN_ID = "astrbot_plugin_xhhrobot"
AUTH_STORAGE_KEY = "xhh_auth_v1"
DEVICE_STORAGE_KEY = "xhh_device_id_v1"
DEFAULT_SESSION_UMO = "xhhrobot:FriendMessage:community"
DEFAULT_REPLY_SYSTEM_PROMPT = (
    "你正在小黑盒社区回复一条明确 @ 你的评论。严格保持前面给定的人设和说话习惯。"
    "只输出准备发布的回复正文，使用自然的纯文本，不使用 Markdown，不添加分析过程。"
    "除非对方明确询问，否则不要提到 AstrBot、模型、API、系统提示词或自动回复。"
    "不要声称看到了输入中没有提供的内容，也不要编造帖子事实。"
)


@dataclass(slots=True)
class CycleResult:
    fetched: int = 0
    queued: int = 0
    ignored: int = 0
    replied: int = 0
    retried: int = 0
    skipped: int = 0
    uncertain: int = 0


class XhhRobotPlugin(Star):
    def __init__(self, context: Context, config: Any | None = None) -> None:
        super().__init__(context)
        self.config = config or {}
        self.data_dir: Path = StarTools.get_data_dir(PLUGIN_ID)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.store = StateStore(
            load_value=self.get_kv_data,
            save_value=self.put_kv_data,
            max_queue=self._int_cfg("reliability.max_queue_size", 500, 20, 5000),
            max_recent=self._int_cfg("reliability.max_recent_records", 200, 20, 2000),
            max_dead=self._int_cfg("reliability.max_dead_records", 200, 20, 2000),
        )
        self.client: XhhClient | None = None
        self.auth: AuthInfo | None = None
        self._auth_source = "none"
        self._auth_invalid = False
        self._tool_runtime = XhhToolRuntime(self)
        self._registered_tool_names: list[str] = []

        self._worker_task: asyncio.Task[None] | None = None
        self._login_task: asyncio.Task[str] | None = None
        self._cycle_lock = asyncio.Lock()
        self._login_lock = asyncio.Lock()
        self._stop_event = asyncio.Event()

        self._started_at = time.time()
        self._last_poll_at = 0.0
        self._last_success_at = 0.0
        self._last_error = ""
        self._consecutive_errors = 0
        self._suspended_until = 0.0
        self._auth_error_notified = False

    async def initialize(self) -> None:
        await self.store.initialize()
        device_id = await self._resolve_device_id()
        self.auth, self._auth_source = await self._load_auth()
        self.client = XhhClient(
            api_base_url=self._str_cfg("connection.api_base_url", "https://api.xiaoheihe.cn"),
            reply_base_url=self._str_cfg(
                "connection.reply_base_url", "https://workshopapi.xiaoheihe.cn"
            ),
            version=self._str_cfg("connection.version", "999.0.4"),
            web_version=self._str_cfg("connection.web_version", "2.5"),
            device_id=device_id,
            timeout_seconds=self._int_cfg("reliability.request_timeout_sec", 20, 5, 120),
            auth=self.auth,
        )
        await self.client.start()
        self._register_llm_tools()

        snapshot = await self.store.snapshot()
        if self._bool_cfg("auto_start", True) and not snapshot["paused"]:
            self._ensure_worker()
        logger.info(
            "%s initialized: auth=%s, worker=%s",
            PLUGIN_ID,
            self._auth_source,
            self._worker_running,
        )

    async def terminate(self) -> None:
        self._unregister_llm_tools()
        self._stop_event.set()
        tasks = [task for task in (self._worker_task, self._login_task) if task is not None and not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._worker_task = None
        self._login_task = None
        if self.client is not None:
            await self.client.close()
            self.client = None

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("小黑盒帮助", alias={"xhh帮助", "xhh_help"})
    async def xhh_help(self, event: AstrMessageEvent):
        """查看小黑盒机器人管理命令。"""
        yield event.plain_result(
            "小黑盒机器人命令：\n"
            "/小黑盒状态 - 查看登录、队列和运行状态\n"
            "/小黑盒登录 - 获取二维码并登录\n"
            "/小黑盒退出 - 清除二维码登录凭据\n"
            "/小黑盒启动 / /小黑盒停止 - 控制后台轮询\n"
            "/小黑盒检查 - 立即拉取并处理一次\n"
            "/小黑盒重试 - 重试普通失败项\n"
            "/小黑盒重试 确认 - 连同“发送结果不确定”的项目一起重试，可能重复回帖\n"
            "/小黑盒测试 帖子ID 测试消息 - 只生成回复，不发布\n\n"
            "自然语言工具：动态、搜索、帖子/评论、用户资料、话题、收藏、点赞、关注、私信和发帖。\n"
            "写工具默认关闭；开启后，用户原消息还需包含“确认执行小黑盒操作”。"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("小黑盒状态", alias={"xhh状态", "xhh_status"})
    async def xhh_status(self, event: AstrMessageEvent):
        """查看小黑盒登录、轮询与回复队列状态。"""
        yield event.plain_result(await self._status_text())

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("小黑盒登录", alias={"xhh登录", "xhh_login"})
    async def xhh_login(self, event: AstrMessageEvent):
        """生成小黑盒二维码并等待扫码登录。"""
        if self.client is None:
            yield event.plain_result("插件客户端尚未初始化。")
            return

        qr_path = self.data_dir / "xhh_login_qr.png"
        async with self._login_lock:
            task = self._login_task
            created = task is None or task.done()
            if created:
                try:
                    challenge = await self.client.begin_qr_login()
                    await asyncio.to_thread(self._write_qr_image, challenge.qr_url, qr_path)
                except Exception as exc:
                    self._last_error = str(exc)
                    yield event.plain_result(f"创建登录二维码失败：{exc}")
                    return
                task = asyncio.create_task(self._complete_qr_login(challenge), name="xhhrobot-qr-login")
                self._login_task = task

        if created:
            yield event.plain_result("请使用小黑盒 App 扫描二维码，并在手机上确认登录。")
        else:
            yield event.plain_result("已有登录二维码正在等待确认。")
        if qr_path.exists():
            yield event.image_result(str(qr_path))

        assert task is not None
        try:
            result = await asyncio.shield(task)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            result = f"登录任务异常：{exc}"
        yield event.plain_result(result)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("小黑盒退出", alias={"xhh退出", "xhh_logout"})
    async def xhh_logout(self, event: AstrMessageEvent):
        """清除插件保存的小黑盒登录凭据。"""
        task = self._login_task
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._login_task = None
        await self.delete_kv_data(AUTH_STORAGE_KEY)
        self.auth = None
        self._auth_source = "none"
        self._auth_invalid = False
        self._auth_error_notified = False
        if self.client is not None:
            self.client.set_auth(None)
        suffix = ""
        if self._str_cfg("account.cookie", ""):
            suffix = "\n配置页仍填写了 Cookie；重新加载插件后会再次使用它，请同时清空该配置。"
        yield event.plain_result("已清除二维码登录凭据。" + suffix)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("小黑盒启动", alias={"xhh启动", "xhh_start"})
    async def xhh_start(self, event: AstrMessageEvent):
        """启动小黑盒后台轮询与自动回复。"""
        await self.store.set_paused(False)
        self._suspended_until = 0.0
        self._ensure_worker()
        message = "小黑盒后台任务已启动。"
        if self.auth is None:
            message += " 当前尚未登录，任务会等待凭据。"
        elif not self._filter_can_reply_to_anyone():
            message += " 当前白名单为空且未允许全部用户，不会实际回复。"
        yield event.plain_result(message)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("小黑盒停止", alias={"xhh停止", "xhh_stop"})
    async def xhh_stop(self, event: AstrMessageEvent):
        """停止小黑盒后台轮询，保留登录和队列。"""
        await self.store.set_paused(True)
        await self._stop_worker()
        yield event.plain_result("小黑盒后台任务已停止；登录凭据和待处理队列均已保留。")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("小黑盒检查", alias={"xhh检查", "xhh_check"})
    async def xhh_check(self, event: AstrMessageEvent):
        """立即执行一次小黑盒消息拉取和回复处理。"""
        try:
            result = await self._run_cycle()
        except Exception as exc:
            await self._handle_cycle_error(exc)
            yield event.plain_result(f"本次检查失败：{exc}")
            return
        yield event.plain_result(
            "本次检查完成："
            f"拉取 {result.fetched}，入队 {result.queued}，忽略 {result.ignored}，"
            f"回复 {result.replied}，待重试 {result.retried}，跳过 {result.skipped}，"
            f"发送结果不确定 {result.uncertain}。"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("小黑盒重试", alias={"xhh重试", "xhh_retry"})
    async def xhh_retry(self, event: AstrMessageEvent, confirmation: str = ""):
        """将失败队列重新放回待处理队列。"""
        include_uncertain = str(confirmation or "").strip().lower() in {"确认", "confirm", "yes"}
        moved = await self.store.retry_dead(include_uncertain=include_uncertain)
        snapshot = await self.store.snapshot()
        uncertain_left = sum(
            1 for item in snapshot["dead"].values() if item.get("reason") == "uncertain_delivery"
        )
        message = f"已将 {moved} 条失败记录放回待处理队列。"
        if uncertain_left and not include_uncertain:
            message += (
                f" 另有 {uncertain_left} 条记录无法确认是否已经发出；"
                "确认没有重复风险后，使用“小黑盒重试 确认”。"
            )
        yield event.plain_result(message)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("小黑盒测试", alias={"xhh测试", "xhh_test"})
    async def xhh_test(self, event: AstrMessageEvent, link_id: int = 0, message: str = ""):
        """读取指定帖子并生成一条测试回复，但不发布。"""
        if link_id <= 0:
            yield event.plain_result("用法：/小黑盒测试 帖子ID 测试消息")
            return
        if self.client is None or self.auth is None:
            yield event.plain_result("请先登录小黑盒。")
            return
        message = self._extract_test_message(event, link_id, message) or "你好，简单说说你对这个帖子的看法。"
        try:
            post = await self.client.fetch_post_context(link_id)
            mention = Mention(
                message_id=0,
                comment_id=0,
                root_comment_id=0,
                link_id=link_id,
                user_id=0,
                comment_text=message,
            )
            reply = await self._generate_reply(mention, post, [])
        except Exception as exc:
            yield event.plain_result(f"测试生成失败：{exc}")
            return
        yield event.plain_result(f"测试回复（未发布）：\n{reply}")

    async def _worker_loop(self) -> None:
        logger.info("%s worker started", PLUGIN_ID)
        try:
            while not self._stop_event.is_set():
                snapshot = await self.store.snapshot()
                if snapshot["paused"]:
                    return
                if self.auth is None or self._auth_invalid:
                    await self._wait_or_stop(30)
                    continue
                now = time.time()
                if self._suspended_until > now:
                    await self._wait_or_stop(min(30, self._suspended_until - now))
                    continue
                try:
                    await self._run_cycle()
                    self._consecutive_errors = 0
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    await self._handle_cycle_error(exc)
                await self._wait_or_stop(self._int_cfg("polling.poll_interval_sec", 30, 5, 3600))
        finally:
            logger.info("%s worker stopped", PLUGIN_ID)

    async def _run_cycle(self) -> CycleResult:
        if self.client is None:
            raise RuntimeError("小黑盒客户端未初始化。")
        if self.auth is None:
            raise XhhError("尚未登录小黑盒。", auth_required=True, retryable=False)
        if self._auth_invalid:
            raise XhhError("小黑盒登录已失效，请重新扫码登录。", auth_required=True, retryable=False)

        async with self._cycle_lock:
            result = await self._poll_mentions()
            await self._process_pending(result)
            self._last_poll_at = time.time()
            self._last_success_at = self._last_poll_at
            return result

    async def _poll_mentions(self) -> CycleResult:
        assert self.client is not None
        snapshot = await self.store.snapshot()
        cursor = int(snapshot["last_message_id"] or 0)
        initialized = bool(snapshot["initialized"])
        page_size = self._int_cfg("polling.page_size", 20, 1, 50)
        max_pages = self._int_cfg("polling.max_pages_per_poll", 10, 1, 100)

        first_page = await self.client.fetch_mentions(offset=0, limit=page_size)
        if not initialized and not self._bool_cfg("polling.process_existing_on_first_start", False):
            newest_id = max((item.message_id for item in first_page), default=0)
            await self.store.set_initial_cursor(newest_id)
            return CycleResult(fetched=len(first_page), ignored=len(first_page))

        collected = list(first_page)
        last_page = first_page
        reached_cursor = any(item.message_id <= cursor for item in first_page) if cursor else False
        for page_index in range(1, max_pages):
            if reached_cursor or len(last_page) < page_size:
                break
            page = await self.client.fetch_mentions(offset=page_index * page_size, limit=page_size)
            if not page:
                last_page = page
                break
            collected.extend(page)
            last_page = page
            if cursor and any(item.message_id <= cursor for item in page):
                reached_cursor = True

        if not reached_cursor and len(last_page) >= page_size:
            raise XhhError(
                "新 @ 消息积压超过 polling.max_pages_per_poll，尚未推进游标以避免漏消息；"
                "请调大该配置后重试。",
                retryable=False,
            )

        unique = {
            item.message_id: item
            for item in collected
            if item.message_id > cursor or (not initialized and cursor == 0)
        }
        mentions = sorted(unique.values(), key=lambda item: item.message_id)
        queued: list[Mention] = []
        ignored: list[tuple[Mention, str]] = []
        for mention in mentions:
            reason = self._ineligible_reason(mention)
            if reason:
                ignored.append((mention, reason))
            else:
                queued.append(mention)

        newest_id = max((item.message_id for item in collected), default=cursor)
        queued_count, ignored_count = await self.store.ingest(
            newest_message_id=newest_id,
            queued=queued,
            ignored=ignored,
        )
        return CycleResult(fetched=len(collected), queued=queued_count, ignored=ignored_count)

    async def _process_pending(self, result: CycleResult) -> None:
        limit = self._int_cfg("polling.max_replies_per_cycle", 3, 1, 20)
        mentions = await self.store.due_items(limit=limit)
        for index, mention in enumerate(mentions):
            outcome = await self._process_mention(mention)
            if outcome == "replied":
                result.replied += 1
            elif outcome == "retry":
                result.retried += 1
            elif outcome == "skipped":
                result.skipped += 1
            elif outcome == "uncertain":
                result.uncertain += 1
            elif outcome == "auth":
                result.retried += 1
                break

            if outcome == "replied" and index < len(mentions) - 1:
                await self._wait_or_stop(self._int_cfg("polling.reply_interval_sec", 30, 5, 3600))

    async def _process_mention(self, mention: Mention) -> str:
        assert self.client is not None
        try:
            post = (
                await self.client.fetch_post_context(mention.link_id)
                if self._bool_cfg("ai.include_post_context", True)
                else PostContext()
            )
            history = await self.store.conversation_history(
                link_id=mention.link_id,
                user_id=mention.user_id,
                turns=self._int_cfg("ai.history_turns", 3, 0, 20),
            )
            reply_text = await self._generate_reply(mention, post, history)
        except asyncio.CancelledError:
            raise
        except XhhError as exc:
            return await self._handle_pre_send_error(mention, exc)
        except Exception as exc:
            await self._schedule_retry(mention, f"生成回复失败：{exc}")
            logger.warning("%s generation failed for message %s: %r", PLUGIN_ID, mention.message_id, exc)
            return "retry"

        try:
            await self.store.mark_sending(mention.message_id)
        except asyncio.CancelledError:
            await asyncio.shield(
                self.store.defer(
                    mention.message_id,
                    "任务在发出回帖请求前被停止。",
                    delay_seconds=0,
                )
            )
            raise
        try:
            await self.client.send_reply(
                text=reply_text,
                link_id=mention.link_id,
                reply_id=mention.comment_id,
                root_id=mention.root_comment_id,
            )
        except asyncio.CancelledError:
            await asyncio.shield(
                self.store.mark_uncertain(
                    mention.message_id,
                    "回帖请求执行期间任务被停止，无法确认服务端是否已经发布。",
                )
            )
            raise
        except XhhError as exc:
            if exc.delivery_uncertain:
                await self.store.mark_uncertain(mention.message_id, str(exc))
                await self._notify(
                    f"小黑盒消息 {mention.message_id} 的发送结果无法确认，已停止自动重试，避免重复回复。"
                )
                return "uncertain"
            if exc.auth_required:
                await self.store.defer(mention.message_id, str(exc), delay_seconds=300)
                await self._set_auth_invalid(str(exc))
                return "auth"
            if exc.terminal:
                await self.store.mark_skipped(mention.message_id, str(exc))
                return "skipped"
            await self._schedule_retry(mention, str(exc), retry_after=exc.retry_after)
            return "retry"
        except Exception as exc:
            await self.store.mark_uncertain(mention.message_id, f"回帖请求异常：{exc}")
            await self._notify(
                f"小黑盒消息 {mention.message_id} 的发送结果无法确认，已停止自动重试，避免重复回复。"
            )
            return "uncertain"

        await self.store.mark_done(mention.message_id, reply_text)
        logger.info(
            "%s replied: message_id=%s link_id=%s comment_id=%s user_id=%s",
            PLUGIN_ID,
            mention.message_id,
            mention.link_id,
            mention.comment_id,
            mention.user_id,
        )
        if self._bool_cfg("notifications.notify_on_reply", False):
            await self._notify(
                f"小黑盒已回复消息 {mention.message_id}（帖子 {mention.link_id}，用户 {mention.user_id}）。"
            )
        return "replied"

    async def _handle_pre_send_error(self, mention: Mention, exc: XhhError) -> str:
        if exc.auth_required:
            await self.store.defer(mention.message_id, str(exc), delay_seconds=300)
            await self._set_auth_invalid(str(exc))
            return "auth"
        if exc.terminal:
            await self.store.mark_skipped(mention.message_id, str(exc))
            return "skipped"
        await self._schedule_retry(mention, str(exc), retry_after=exc.retry_after)
        return "retry"

    async def _schedule_retry(
        self,
        mention: Mention,
        error: str,
        *,
        retry_after: float | None = None,
    ) -> None:
        snapshot = await self.store.snapshot()
        item = snapshot["queue"].get(str(mention.message_id), {})
        attempts = int(item.get("attempts") or 0)
        base = self._int_cfg("reliability.retry_base_delay_sec", 60, 5, 3600)
        delay = retry_after if retry_after is not None else min(base * (2**attempts), 6 * 3600)
        await self.store.mark_retry(
            mention.message_id,
            error,
            max_attempts=self._int_cfg("reliability.max_retry_attempts", 3, 1, 20),
            delay_seconds=delay,
        )
        self._last_error = error

    async def _generate_reply(
        self,
        mention: Mention,
        post: PostContext,
        history: list[dict[str, str]],
    ) -> str:
        provider_id = await self._resolve_provider_id()
        system_prompt = await self._build_system_prompt()
        prompt = self._build_generation_prompt(mention, post, history)
        image_urls = (
            list(post.image_urls)[: self._int_cfg("ai.max_post_images", 4, 0, 20)]
            if self._bool_cfg("ai.include_post_images", True)
            else []
        )
        timeout = self._int_cfg("ai.generation_timeout_sec", 120, 10, 600)
        response = await asyncio.wait_for(
            self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
                contexts=[],
                image_urls=image_urls or None,
                system_prompt=system_prompt or None,
            ),
            timeout=timeout,
        )
        text = str(getattr(response, "completion_text", None) or "").strip()
        text = self._clean_reply(text)
        if not text:
            raise RuntimeError("AstrBot 模型返回了空文本。")
        return text

    async def _resolve_provider_id(self) -> str:
        configured = self._str_cfg("ai.provider_id", "")
        if configured:
            return configured
        umo = self._str_cfg("ai.session_umo", DEFAULT_SESSION_UMO)
        getter = getattr(self.context, "get_current_chat_provider_id", None)
        if callable(getter):
            value = getter(umo)
            value = await value if inspect.isawaitable(value) else value
            if value:
                return str(value)
        provider = self.context.get_using_provider(umo)
        provider_id = getattr(getattr(provider, "meta", lambda: None)(), "id", "") if provider else ""
        if not provider_id:
            provider_id = str(getattr(provider, "id", "") or getattr(provider, "provider_id", ""))
        if not provider_id:
            raise RuntimeError("没有可用的 AstrBot 文本模型，请在插件配置中选择 provider。")
        return provider_id

    async def _build_system_prompt(self) -> str:
        parts: list[str] = []
        persona_prompt = await self._selected_persona_prompt()
        if persona_prompt:
            parts.append(persona_prompt)
        routing_prompt = self._str_cfg("ai.reply_system_prompt", DEFAULT_REPLY_SYSTEM_PROMPT)
        if routing_prompt:
            parts.append(routing_prompt)
        extra = self._str_cfg("ai.extra_system_prompt", "")
        if extra:
            parts.append(extra)
        return "\n\n".join(part.strip() for part in parts if part.strip())

    async def _selected_persona_prompt(self) -> str:
        manager = getattr(self.context, "persona_manager", None)
        if manager is None:
            return ""
        persona_id = self._str_cfg("ai.persona_id", "")
        if persona_id == "[%None]":
            return ""
        try:
            if persona_id and persona_id != "default":
                persona = manager.get_persona(persona_id)
                persona = await persona if inspect.isawaitable(persona) else persona
                return self._persona_prompt(persona)
            if not self._bool_cfg("ai.use_default_persona", True):
                return ""
            getter = getattr(manager, "get_default_persona_v3", None)
            if callable(getter):
                persona = getter(self._str_cfg("ai.session_umo", DEFAULT_SESSION_UMO))
                persona = await persona if inspect.isawaitable(persona) else persona
                return self._persona_prompt(persona)
        except Exception as exc:
            logger.warning("%s failed to resolve persona: %r", PLUGIN_ID, exc)
        return ""

    @staticmethod
    def _persona_prompt(persona: Any) -> str:
        if persona is None:
            return ""
        if isinstance(persona, Mapping):
            return str(persona.get("prompt") or persona.get("system_prompt") or "").strip()
        return str(getattr(persona, "prompt", None) or getattr(persona, "system_prompt", None) or "").strip()

    def _build_generation_prompt(
        self,
        mention: Mention,
        post: PostContext,
        history: list[dict[str, str]],
    ) -> str:
        max_context = self._int_cfg("ai.max_post_context_chars", 12000, 0, 100000)
        body = post.body_text
        if max_context > 0 and len(body) > max_context:
            body = body[:max_context].rstrip() + "\n[帖子正文已截断]"

        sections: list[str] = []
        if post.title:
            sections.append(f"帖子标题：{post.title}")
        if post.topics:
            sections.append("话题：" + "、".join(post.topics))
        if post.tags:
            sections.append("标签：" + "、".join(post.tags))
        if body:
            sections.append("帖子正文：\n" + body)
        if post.image_urls and self._bool_cfg("ai.include_post_images", True):
            sections.append(f"帖子图片：{len(post.image_urls)} 张（已随模型请求提供可用图片）")
        if history:
            lines = []
            for turn in history:
                lines.append(f"对方：{turn['user']}\n你：{turn['assistant']}")
            sections.append("同一帖子中你与该用户最近的对话：\n" + "\n\n".join(lines))

        sections.append(f"当前评论者小黑盒用户 ID：{mention.user_id or '测试用户'}")
        sections.append("当前对方 @ 你的评论：\n" + (mention.comment_text or "[空评论]"))
        sections.append("请直接给出要发布的回复正文。")
        return "\n\n".join(sections)

    def _clean_reply(self, value: str) -> str:
        text = value.strip()
        if self._bool_cfg("ai.strip_markdown", True):
            text = re.sub(r"^```[^\n]*\n?|\n?```$", "", text, flags=re.MULTILINE).strip()
            text = re.sub(r"^\s{0,3}#{1,6}\s+", "", text, flags=re.MULTILINE)
            text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
            text = re.sub(r"\[([^\]]+)]\(([^)]+)\)", r"\1（\2）", text)
            text = text.replace("**", "").replace("__", "").replace("`", "")
        max_chars = self._int_cfg("ai.max_reply_chars", 1200, 1, 10000)
        if len(text) > max_chars:
            text = text[:max_chars].rstrip()
        return text.strip()

    def _ineligible_reason(self, mention: Mention) -> str:
        if not mention.is_actionable:
            return "消息缺少帖子或评论 ID"
        if self.auth is not None and self.auth.heybox_id and str(mention.user_id) == self.auth.heybox_id:
            return "忽略机器人账号自己的消息"
        blocked = self._id_set_cfg("filters.blocked_user_ids")
        if str(mention.user_id) in blocked:
            return "用户在黑名单中"
        if self._bool_cfg("filters.allow_all_users", False):
            return ""
        allowed = self._id_set_cfg("filters.allowed_user_ids")
        if str(mention.user_id) not in allowed:
            return "用户不在允许列表中"
        return ""

    async def _handle_cycle_error(self, exc: Exception) -> None:
        self._last_error = str(exc)
        self._last_poll_at = time.time()
        if isinstance(exc, XhhError) and exc.auth_required:
            await self._set_auth_invalid(str(exc))
            return
        self._consecutive_errors += 1
        threshold = self._int_cfg("reliability.circuit_breaker_errors", 5, 1, 50)
        if self._consecutive_errors >= threshold:
            pause = self._int_cfg("reliability.circuit_breaker_pause_sec", 600, 30, 86400)
            self._suspended_until = time.time() + pause
            self._consecutive_errors = 0
            await self._notify(f"小黑盒连续请求失败，自动暂停 {pause} 秒。最后错误：{exc}")
        logger.warning("%s cycle failed: %r", PLUGIN_ID, exc)

    async def _set_auth_invalid(self, reason: str) -> None:
        self._auth_invalid = True
        self._last_error = reason
        if not self._auth_error_notified:
            self._auth_error_notified = True
            await self._notify(f"小黑盒登录已失效，请使用“小黑盒登录”重新扫码。原因：{reason}")

    async def _complete_qr_login(self, challenge: QrChallenge) -> str:
        assert self.client is not None
        timeout = self._int_cfg("account.login_timeout_sec", 180, 30, 600)
        if 0 < challenge.expires_in < 3600:
            timeout = min(timeout, challenge.expires_in)
        deadline = time.monotonic() + timeout
        try:
            while time.monotonic() < deadline:
                result = await self.client.poll_qr_login(challenge)
                if result.state == "success" and result.auth is not None:
                    self.auth = result.auth
                    self._auth_source = "qr"
                    self._auth_invalid = False
                    self._auth_error_notified = False
                    await self.put_kv_data(AUTH_STORAGE_KEY, result.auth.to_dict())
                    snapshot = await self.store.snapshot()
                    if self._bool_cfg("auto_start", True) and not snapshot["paused"]:
                        self._ensure_worker()
                    name = f"，账号：{result.auth.nickname}" if result.auth.nickname else ""
                    return "小黑盒登录成功" + name + "。"
                if result.state == "expired":
                    return "登录二维码已过期，请重新执行“小黑盒登录”。"
                if result.state == "failed":
                    return "小黑盒登录失败：" + (result.message or "未知原因")
                await asyncio.sleep(1.5)
            return "等待扫码超时，请重新执行“小黑盒登录”。"
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._last_error = str(exc)
            return f"小黑盒登录失败：{exc}"

    async def _load_auth(self) -> tuple[AuthInfo | None, str]:
        stored = AuthInfo.from_dict(await self.get_kv_data(AUTH_STORAGE_KEY, None))
        if stored is not None:
            return stored, "qr"
        cookie = self._str_cfg("account.cookie", "")
        if not cookie:
            return None, "none"
        parsed = XhhClient.parse_cookie_header(cookie)
        heybox_id = self._str_cfg("account.heybox_id", "") or str(parsed.get("user_heybox_id") or "")
        return AuthInfo(cookie=cookie, heybox_id=heybox_id, login_at=0), "config"

    async def _resolve_device_id(self) -> str:
        configured = self._str_cfg("account.device_id", "")
        if configured:
            return configured
        stored = str(await self.get_kv_data(DEVICE_STORAGE_KEY, "") or "").strip()
        if stored:
            return stored
        generated = uuid.uuid4().hex
        await self.put_kv_data(DEVICE_STORAGE_KEY, generated)
        return generated

    async def _status_text(self) -> str:
        snapshot = await self.store.snapshot()
        queue = snapshot["queue"]
        dead = snapshot["dead"]
        uncertain = sum(1 for item in dead.values() if item.get("reason") == "uncertain_delivery")
        heybox_id = self.auth.heybox_id if self.auth is not None else ""
        account = self.auth.nickname if self.auth is not None and self.auth.nickname else heybox_id
        if account and len(account) > 8:
            account = account[:4] + "…" + account[-3:]
        auth_state = "已配置"
        if self.auth is None:
            auth_state = "未登录"
        elif self._auth_invalid:
            auth_state = "已失效"
        paused = bool(snapshot["paused"])
        suspend_left = max(0, int(self._suspended_until - time.time()))
        provider = self._str_cfg("ai.provider_id", "") or "AstrBot 当前/默认模型"
        persona = self._str_cfg("ai.persona_id", "") or "AstrBot 当前/默认人设"
        user_scope = (
            "全部用户"
            if self._bool_cfg("filters.allow_all_users", False)
            else f"允许列表 {len(self._id_set_cfg('filters.allowed_user_ids'))} 人"
        )
        lines = [
            f"运行：{'运行中' if self._worker_running else '未运行'}{'（已手动停止）' if paused else ''}",
            f"登录：{auth_state}；来源：{self._auth_source}" + (f"；账号：{account}" if account else ""),
            f"游标：{snapshot['last_message_id']}；待处理：{len(queue)}；失败：{len(dead)}（发送不确定 {uncertain}）",
            (
                f"累计：已回复 {snapshot['stats']['replied']}，"
                f"已忽略 {snapshot['stats']['ignored']}，已跳过 {snapshot['stats']['skipped']}"
            ),
            f"模型：{provider}",
            f"人设：{persona}",
            f"用户范围：{user_scope}",
            (
                "LLM 工具："
                + ("已启用" if self._bool_cfg("tools.enabled", True) else "已关闭")
                + "；写工具："
                + ("已启用" if self._bool_cfg("tools.enable_write_tools", False) else "已关闭")
            ),
        ]
        if suspend_left:
            lines.append(f"熔断暂停：剩余 {suspend_left} 秒")
        if self._last_success_at:
            lines.append("最近成功检查：" + self._format_time(self._last_success_at))
        if self._last_error:
            lines.append("最近错误：" + self._last_error[:300])
        return "\n".join(lines)

    async def _notify(self, text: str) -> None:
        umo = self._str_cfg("notifications.umo", "")
        if not umo:
            return
        try:
            await self.context.send_message(umo, MessageChain().message("[小黑盒机器人] " + text))
        except Exception as exc:
            logger.warning("%s notification failed: %r", PLUGIN_ID, exc)

    def _register_llm_tools(self) -> None:
        self._unregister_llm_tools()
        if not self._bool_cfg("tools.enabled", True):
            return
        tools = self._tool_runtime.build_tools()
        self.context.add_llm_tools(*tools)
        self._registered_tool_names = [tool.name for tool in tools]
        active_count = sum(1 for tool in tools if getattr(tool, "active", True))
        logger.info(
            "%s registered %d LLM tools (%d active)",
            PLUGIN_ID,
            len(tools),
            active_count,
        )

    def _unregister_llm_tools(self) -> None:
        names = list(getattr(self, "_registered_tool_names", []))
        if not names:
            return
        getter = getattr(self.context, "get_llm_tool_manager", None)
        if callable(getter):
            manager = getter()
            for name in names:
                manager.remove_func(name)
        self._registered_tool_names = []

    def _ensure_worker(self) -> None:
        if self._stop_event.is_set():
            return
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker_loop(), name="xhhrobot-worker")

    async def _stop_worker(self) -> None:
        task = self._worker_task
        if task is None or task.done():
            self._worker_task = None
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        self._worker_task = None

    async def _wait_or_stop(self, seconds: float) -> None:
        if seconds <= 0:
            return
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)

    @staticmethod
    def _write_qr_image(qr_url: str, path: Path) -> None:
        qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=4)
        qr.add_data(qr_url)
        qr.make(fit=True)
        image = qr.make_image(fill_color="black", back_color="white")
        image.save(path)

    def _filter_can_reply_to_anyone(self) -> bool:
        return self._bool_cfg("filters.allow_all_users", False) or bool(
            self._id_set_cfg("filters.allowed_user_ids")
        )

    def _id_set_cfg(self, path: str) -> set[str]:
        value = self._cfg(path, [])
        if isinstance(value, str):
            values = re.split(r"[,，\s]+", value)
        elif isinstance(value, (list, tuple, set)):
            values = value
        else:
            values = []
        return {str(item).strip() for item in values if str(item).strip()}

    def _cfg(self, path: str, default: Any) -> Any:
        value: Any = self.config
        for key in path.split("."):
            if not isinstance(value, Mapping) or key not in value:
                return default
            value = value[key]
        return default if value is None else value

    def _str_cfg(self, path: str, default: str) -> str:
        return str(self._cfg(path, default) or "").strip()

    def _bool_cfg(self, path: str, default: bool) -> bool:
        value = self._cfg(path, default)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on", "是"}
        return bool(value)

    def _int_cfg(self, path: str, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(self._cfg(path, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    @property
    def _worker_running(self) -> bool:
        return self._worker_task is not None and not self._worker_task.done()

    @staticmethod
    def _format_time(timestamp: float) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))

    @staticmethod
    def _extract_test_message(event: AstrMessageEvent, link_id: int, parsed: str) -> str:
        raw = str(getattr(event, "message_str", "") or "").strip()
        match = re.search(rf"\b{re.escape(str(link_id))}\b\s*(.*)$", raw, flags=re.DOTALL)
        if match and match.group(1).strip():
            return match.group(1).strip()
        return str(parsed or "").strip()
