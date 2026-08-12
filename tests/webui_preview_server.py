from __future__ import annotations

import base64
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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

AVATAR_DATA_URL = "data:image/png;base64," + base64.b64encode(
    base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
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
        "criteria": {
            "topic": "喜欢、爱意、心动或明确好感",
            "keywords": ["喜欢", "爱你", "爱了", "心动", "好感"],
            "emoji_tokens": ["cube_喜欢", "heygirl_喜欢"],
        },
        "provider_id": "Ldc/gemini-2.5-pro",
        "total_comments": 2726,
        "unique_users": 2198,
        "unique_posts": 1,
        "keyword_matches": 520,
        "emoji_matches": 458,
        "keyword_emoji_overlap": 366,
        "deterministic_union": 612,
        "semantic_candidates": 2114,
        "semantic_selected": 2114,
        "semantic_analyzed": 2114,
        "semantic_matches": 69,
        "semantic_pending": 0,
        "semantic_not_selected": 0,
        "semantic_coverage_percent": 100.0,
        "union_matches": 681,
        "union_percentage": 24.98,
        "semantic_enabled": True,
        "semantic_complete": True,
        "examples": [
            {"content": "我喜欢你", "link_id": 187581315, "comment_id": 927442536, "user_id": 22566606, "matched_by": ["keyword"], "reason": ""},
            {"content": "好好好，喜欢上你了[cube_喜欢]", "link_id": 187581315, "comment_id": 927442537, "user_id": 30136930, "matched_by": ["keyword", "emoji"], "reason": ""},
            {"content": "你对我的好感度是多少", "link_id": 187581315, "comment_id": 927442538, "user_id": 73225228, "matched_by": ["keyword"], "reason": ""},
            {"content": "真的很心动", "link_id": 187581315, "comment_id": 927442539, "user_id": 56747115, "matched_by": ["semantic"], "reason": "明确表达心动"},
        ],
        "counting_note": "统计对象是插件 SQLite 已归档并按帖子 ID + 评论 ID 去重的外部用户评论。文字命中与表情命中可能重叠；语义匹配只分析前两类未命中的评论。",
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
