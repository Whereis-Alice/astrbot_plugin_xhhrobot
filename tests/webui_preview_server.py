from __future__ import annotations

import base64
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image as PillowImage
from PIL import ImageDraw

ROOT = Path(__file__).parents[1]
PAGE = ROOT / "pages" / "dashboard" / "index.html"


STATUS = {
    "ok": True,
    "runtime": {
        "worker_running": True,
        "paused": False,
        "uptime_seconds": 3661,
        "last_success_at": 1786480200,
        "last_error": "",
        "suspended_until": 0,
    },
    "account": {
        "state": "authenticated",
        "source": "qr",
        "heybox_id": "102013423",
        "nickname": "爱丽丝",
        "proxy_configured": False,
        "profile_updated_at": 1786480200,
        "profile_error": "",
        "profile": {
            "heybox_id": "102013423",
            "nickname": "爱丽丝",
            "level": "42",
            "signature": "正在小黑盒营业",
            "ip_location": "上海",
            "following_count": 88,
            "follower_count": 520,
            "post_count": 31,
            "comment_count": 406,
        },
    },
    "events": {
        "bridge_enabled": True,
        "in_flight": 1,
        "max_in_flight": 5,
        "queue_total": 18,
        "queue_status_counts": {"pending": 15, "sending": 1, "dispatched": 2},
        "dead_total": 2,
        "uncertain_total": 0,
    },
    "comments": {
        "enabled": True,
        "received_comments": 2726,
        "received_observations": 2988,
        "bot_comments": 614,
        "semantic_cache_records": 2431,
        "cursor": 4120773322,
        "own_post_cursor": 4140170434,
        "own_post_reply_limit": 50,
        "tracked_own_posts": 9,
        "stats": {"replied": 603, "ignored": 29, "skipped": 83},
    },
    "direct_messages": {
        "enabled": True,
        "sending_blocked": False,
        "sending_blocked_reason": "",
        "last_error": "",
        "total": 126,
        "status_counts": {"sent": 102, "skipped": 12},
    },
    "features": {
        "reply_to_own_post_comments": True,
        "auto_browse": True,
        "llm_tools": True,
        "write_tools": True,
        "draft_tools": False,
        "worldbook_hooks": True,
        "comment_insights": True,
    },
}

avatar_image = PillowImage.new("RGB", (64, 64), (11, 36, 28))
avatar_draw = ImageDraw.Draw(avatar_image)
avatar_draw.ellipse((7, 7, 57, 57), fill=(63, 196, 124))
avatar_draw.rectangle((29, 18, 35, 46), fill=(5, 20, 15))
avatar_draw.rectangle((18, 29, 46, 35), fill=(5, 20, 15))
avatar_buffer = BytesIO()
avatar_image.save(avatar_buffer, format="PNG")
AVATAR_DATA_URL = "data:image/png;base64," + base64.b64encode(
    avatar_buffer.getvalue()
).decode("ascii")


ANALYTICS = {
    "ok": True,
    "generated_at": 1786480200,
    "comments": {
        "enabled": True,
        "received": {
            "unique_comments": 2726,
            "raw_observations": 2988,
            "status_counts": {"replied": 603, "ignored": 29, "skipped": 83},
        },
        "bot": {
            "comment_records": 614,
            "confirmed_sent": 603,
            "status_counts": {"sent": 603, "uncertain": 11},
        },
    },
    "direct_messages": {
        "total": 126,
        "unique_users": 34,
        "with_images": 19,
        "status_counts": {"sent": 102, "skipped": 12, "failed": 2},
    },
}


INSIGHT = {
    "ok": True,
    "job_id": "51dbe8cf01234bd6b8f210d9f215ac12",
    "state": "complete",
    "created_at": 1786480000,
    "updated_at": 1786480180,
    "filters": {"link_id": 187581315, "source": "own_post_comment"},
    "progress": {
        "completed": 1734,
        "total": 1734,
        "batches_completed": 87,
        "model_calls": 12,
        "cache_hits": 1494,
    },
    "semantic_available": True,
    "semantic_batch_size": 20,
    "semantic_max_comments_per_run": 0,
    "error": "",
    "report": {
        "analysis_mode": "exploratory",
        "provider_id": "Ldc/gemini-2.5-pro",
        "total_comments": 2726,
        "selected_comments": 1734,
        "analyzed_comments": 1734,
        "not_selected": 992,
        "coverage_percent": 63.61,
        "selected_coverage_percent": 100.0,
        "unique_users": 2198,
        "unique_posts": 1,
        "sentiment_counts": {"positive": 906, "neutral": 562, "negative": 189, "mixed": 77},
        "sentiment_percentages": {"positive": 52.25, "neutral": 32.41, "negative": 10.9, "mixed": 4.44},
        "intent_counts": {"praise": 510, "criticism": 181, "question": 302, "suggestion": 96, "joke": 347, "agreement": 110, "disagreement": 40, "experience": 71, "information": 43, "other": 34},
        "top_topics": [
            {"label": "角色形象", "count": 632, "percentage": 36.45},
            {"label": "图片来源", "count": 318, "percentage": 18.34},
            {"label": "游戏梗", "count": 276, "percentage": 15.92},
            {"label": "画面质量", "count": 205, "percentage": 11.82},
        ],
        "top_questions": [{"label": "图片来源", "count": 214, "percentage": 12.34}],
        "top_suggestions": [{"label": "发布原图", "count": 68, "percentage": 3.92}],
        "summary": "评论整体偏正面，讨论集中在角色形象、图片来源和游戏梗。最明确的用户需求是获取原图，同时有少量针对画面清晰度的吐槽。",
        "themes": [
            {"label": "角色与画面反馈", "count": 781, "percentage": 45.04, "source_topics": ["角色形象", "画面质量"], "description": "多数评论在夸角色表现，也有人讨论清晰度。"},
            {"label": "图片来源需求", "count": 318, "percentage": 18.34, "source_topics": ["图片来源"], "description": "大量用户询问原图和出处。"},
            {"label": "社区玩梗", "count": 276, "percentage": 15.92, "source_topics": ["游戏梗"], "description": "围绕游戏身份和角色展开调侃。"},
        ],
        "controversies": ["少量用户认为图片压缩明显，也有人认为当前清晰度足够"],
        "notable_findings": ["原图请求是最集中的明确需求", "玩梗评论较多，但整体没有明显敌意"],
        "synthesis_complete": True,
        "cache_hits": 1494,
        "model_calls": 12,
        "semantic_enabled": True,
        "semantic_complete": True,
        "examples": [
            {"content": "这张也太好看了", "link_id": 187581315, "comment_id": 927442536, "user_id": 22566606, "sentiment": "positive", "intent": "praise", "topics": ["角色形象"], "summary": "称赞角色形象"},
            {"content": "有原图吗？", "link_id": 187581315, "comment_id": 927442537, "user_id": 30136930, "sentiment": "neutral", "intent": "question", "topics": ["图片来源"], "summary": "询问原图地址"},
            {"content": "建议发个无压缩版", "link_id": 187581315, "comment_id": 927442538, "user_id": 73225228, "sentiment": "neutral", "intent": "suggestion", "topics": ["发布原图"], "summary": "建议提供无压缩图片"},
            {"content": "原友快动[cube_喜欢]", "link_id": 187581315, "comment_id": 927442539, "user_id": 56747115, "sentiment": "positive", "intent": "joke", "topics": ["游戏梗"], "summary": "使用游戏身份梗互动"},
        ],
        "counting_note": "自动洞察分析插件 SQLite 已归档并按帖子 ID + 评论 ID 去重的外部用户评论。情绪、意图和话题占比以本轮已分析样本为分母。",
    },
}


MESSAGES = {
    "ok": True,
    "dataset": "comments",
    "matched_count": 2726,
    "returned_count": 4,
    "limit": 30,
    "offset": 0,
    "records": [
        {"dataset": "comments", "direction": "received", "sources": ["own_post_comment"], "content": "原友快动[cube_喜欢]", "status": "replied", "last_seen_at": "2026-08-12T03:10:00Z", "user_id": 22566606, "link_id": 187581315, "comment_id": 927442536},
        {"dataset": "comments", "direction": "bot", "kind": "auto_reply", "content": "自首人员请勿在评论区公开聚众 [cube_doge]", "status": "sent", "updated_at": "2026-08-12T03:11:00Z", "link_id": 187581315, "comment_id": 927442600},
        {"dataset": "comments", "direction": "received", "sources": ["mention"], "content": "这张图是原图吗", "status": "replied", "last_seen_at": "2026-08-12T03:12:00Z", "user_id": 30136930, "link_id": 187613221, "comment_id": 927495295},
        {"dataset": "comments", "direction": "received", "sources": ["own_post_comment"], "content": "不喝奶茶", "status": "replied", "last_seen_at": "2026-08-12T03:13:00Z", "user_id": 73225228, "link_id": 187613221, "comment_id": 927495296},
    ],
}


BRIDGE = """
(() => {
  const payloads = window.__previewPayloads;
  window.AstrBotPluginPage = {
    ready: async () => ({ isDark: true, locale: 'zh-CN' }),
    apiGet: async (endpoint) => {
      if (endpoint === 'status') return payloads.status;
      if (endpoint === 'account/avatar') return {ok:true,data_url:payloads.avatarDataUrl,updated_at:1786480200};
      if (endpoint === 'analytics/summary') return payloads.analytics;
      if (endpoint === 'analytics/messages') return payloads.messages;
      if (endpoint === 'analytics/insights/status') return payloads.insight;
      if (endpoint === 'login/session' || endpoint === 'login/poll') return {ok:true,state:'authenticated',message:'',account:payloads.status.account};
      return {ok:true};
    },
    apiPost: async (endpoint) => {
      if (endpoint === 'analytics/insights/run') return payloads.insight;
      if (endpoint === 'analytics/insights/cancel') return {...payloads.insight,state:'cancelled',message:'评论洞察任务已取消。'};
      if (endpoint === 'runtime/start' || endpoint === 'runtime/stop') return {ok:true,status:payloads.status};
      return {ok:true};
    },
    onContext: () => {},
  };
})();
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            html = PAGE.read_text(encoding="utf-8")
            payloads = json.dumps(
                {"status": STATUS, "analytics": ANALYTICS, "insight": INSIGHT, "messages": MESSAGES, "avatarDataUrl": AVATAR_DATA_URL},
                ensure_ascii=False,
            )
            html = html.replace("<script src=\"/api/plugin/page/bridge-sdk.js\"></script>", f"<script>window.__previewPayloads={payloads};</script><script src=\"/api/plugin/page/bridge-sdk.js\"></script>")
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        elif parsed.path == "/api/plugin/page/bridge-sdk.js":
            data = BRIDGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
        else:
            query = parse_qs(parsed.query)
            data = json.dumps({"ok": True, "query": query}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
