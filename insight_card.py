from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

try:
    from .insight_card_template import INSIGHT_CARD_TEMPLATE
except ImportError:  # pragma: no cover - supports direct preview-server imports
    from insight_card_template import INSIGHT_CARD_TEMPLATE  # type: ignore[no-redef]


@dataclass(frozen=True, slots=True)
class InsightCardTheme:
    key: str
    label: str
    kicker: str
    background: str
    surface: str
    surface_alt: str
    text: str
    muted: str
    line: str
    accent: str
    accent_alt: str
    warning: str
    danger: str
    font_family: str
    title_family: str
    radius: int
    shadow: str
    grid: str


THEMES: dict[str, InsightCardTheme] = {
    "terminal": InsightCardTheme(
        key="terminal",
        label="小黑盒终端",
        kicker="XHHBOT // COMMENT INTELLIGENCE",
        background="#030806",
        surface="#07110d",
        surface_alt="#0c1b14",
        text="#f2fff8",
        muted="#9cb9ac",
        line="#28533e",
        accent="#5cff9a",
        accent_alt="#58ddeb",
        warning="#ffad66",
        danger="#ff6b6b",
        font_family="'Microsoft YaHei UI', 'PingFang SC', sans-serif",
        title_family="Consolas, 'Microsoft YaHei UI', monospace",
        radius=2,
        shadow="0 0 32px rgba(92, 255, 154, .14)",
        grid="none",
    ),
    "cyberpunk": InsightCardTheme(
        key="cyberpunk",
        label="霓虹街刊",
        kicker="人群信号 · 街刊特辑",
        background="#07050e",
        surface="#100c19",
        surface_alt="#1c1628",
        text="#fffaff",
        muted="#c5bdca",
        line="#725f82",
        accent="#36e7f2",
        accent_alt="#ff4f9a",
        warning="#e8ff3f",
        danger="#ff6b57",
        font_family="'Microsoft YaHei UI', 'PingFang SC', sans-serif",
        title_family="'Arial Black', 'Microsoft YaHei UI', sans-serif",
        radius=0,
        shadow="0 0 34px rgba(255, 79, 154, .22), 0 0 18px rgba(54, 231, 242, .12)",
        grid="none",
    ),
    "editorial": InsightCardTheme(
        key="editorial",
        label="编辑部头版",
        kicker="评论观察 · 编辑部",
        background="#dce3eb",
        surface="#fcfdff",
        surface_alt="#edf1f6",
        text="#17191d",
        muted="#5c6572",
        line="#b7c1cd",
        accent="#1748a0",
        accent_alt="#d83b30",
        warning="#9a6418",
        danger="#a92f36",
        font_family="'Microsoft YaHei UI', 'PingFang SC', sans-serif",
        title_family="Georgia, 'Songti SC', serif",
        radius=0,
        shadow="0 18px 0 rgba(23, 72, 160, .14)",
        grid="none",
    ),
    "command": InsightCardTheme(
        key="command",
        label="信号海报",
        kicker="社区回声 · 信号海报",
        background="#171616",
        surface="#f5f1e8",
        surface_alt="#fffdf7",
        text="#171616",
        muted="#5f5b55",
        line="#171616",
        accent="#1746d1",
        accent_alt="#ef4136",
        warning="#ffd84d",
        danger="#c9233f",
        font_family="'Microsoft YaHei UI', 'PingFang SC', sans-serif",
        title_family="'Microsoft YaHei UI', 'PingFang SC', sans-serif",
        radius=0,
        shadow="16px 16px 0 #ef4136",
        grid="none",
    ),
}

THEME_ALIASES = {
    "terminal": "terminal",
    "hacker": "terminal",
    "xhh": "terminal",
    "小黑盒": "terminal",
    "终端": "terminal",
    "黑客": "terminal",
    "小黑盒终端": "terminal",
    "cyberpunk": "cyberpunk",
    "cyber": "cyberpunk",
    "赛博": "cyberpunk",
    "赛博朋克": "cyberpunk",
    "霓虹": "cyberpunk",
    "霓虹街刊": "cyberpunk",
    "editorial": "editorial",
    "report": "editorial",
    "编辑部": "editorial",
    "编辑部报告": "editorial",
    "编辑部头版": "editorial",
    "command": "command",
    "dashboard": "command",
    "指挥台": "command",
    "数据指挥台": "command",
    "作战室": "command",
    "信号作战室": "command",
    "海报": "command",
    "信号海报": "command",
}

SENTIMENT_LABELS = {
    "positive": "正面",
    "neutral": "中立",
    "negative": "负面",
    "mixed": "混合",
}
INTENT_LABELS = {
    "praise": "夸奖",
    "criticism": "吐槽",
    "question": "提问",
    "suggestion": "建议",
    "joke": "玩梗",
    "agreement": "赞同",
    "disagreement": "反对",
    "experience": "经历",
    "information": "信息",
    "other": "其他",
}


def available_insight_card_themes() -> list[dict[str, str]]:
    return [{"key": item.key, "label": item.label} for item in THEMES.values()]


def normalize_insight_card_theme(value: Any, default: str = "terminal") -> str:
    normalized_default = THEME_ALIASES.get(str(default or "").strip().casefold(), "terminal")
    text = str(value or "").strip().casefold()
    if not text:
        return normalized_default
    try:
        return THEME_ALIASES[text]
    except KeyError as exc:
        labels = "、".join(item.label for item in THEMES.values())
        raise ValueError(f"未知洞察卡片主题：{value}。可选：{labels}。") from exc


CARD_RESOLUTION_ALIASES = {
    "standard": "standard",
    "标准": "standard",
    "high": "high",
    "高清": "high",
    "高清（推荐）": "high",
    "高清(推荐)": "high",
    "recommended": "high",
    "ultra": "ultra",
    "超清": "ultra",
}

CARD_RESOLUTION_LABELS = {
    "standard": "标准",
    "high": "高清（推荐）",
    "ultra": "超清",
}


def available_insight_card_resolutions() -> list[dict[str, str]]:
    return [
        {"key": key, "label": label}
        for key, label in CARD_RESOLUTION_LABELS.items()
    ]


def normalize_insight_card_resolution(value: Any, default: str = "high") -> str:
    normalized_default = CARD_RESOLUTION_ALIASES.get(
        str(default or "").strip().casefold(), "high"
    )
    text = str(value or "").strip().casefold()
    if not text:
        return normalized_default
    try:
        return CARD_RESOLUTION_ALIASES[text]
    except KeyError as exc:
        raise ValueError("未知洞察卡片清晰度：%s。可选：标准、高清、超清。" % value) from exc


@dataclass(frozen=True, slots=True)
class InsightCardResult:
    image_url: str
    theme: str
    theme_label: str
    mode: str
    resolution: str = "high"


class InsightCardRenderer:
    async def render(
        self,
        plugin: Any,
        snapshot: Mapping[str, Any],
        *,
        theme: Any = "",
        default_theme: str = "terminal",
        resolution: Any = "",
        default_resolution: str = "high",
        example_limit: int = 4,
        include_examples: bool = True,
    ) -> InsightCardResult:
        if str(snapshot.get("state") or "") != "complete":
            raise ValueError("最近一次评论洞察尚未完成，请先运行并等待分析完成。")
        report = snapshot.get("report")
        if not isinstance(report, Mapping):
            raise ValueError("当前没有可渲染的评论洞察结果。")
        render = getattr(plugin, "html_render", None)
        if not callable(render):
            raise RuntimeError("当前 AstrBot 版本未提供 HTML 图片渲染能力。")

        theme_key = normalize_insight_card_theme(theme, default_theme)
        theme_config = THEMES[theme_key]
        resolution_key = normalize_insight_card_resolution(resolution, default_resolution)
        payload = build_insight_card_payload(
            snapshot,
            theme_config,
            example_limit=example_limit,
            include_examples=include_examples,
        )
        image_url = await render(
            INSIGHT_CARD_TEMPLATE,
            payload,
            return_url=True,
            options={
                "viewport_width": 720,
                "viewport_height": 720,
                "selector": "#insight-card",
                "full_page": True,
                "type": "png",
                "animations": "disabled",
                "caret": "hide",
                "scale": "device",
                "device_scale_factor_level": resolution_key,
                "wait_until": "load",
            },
        )
        if not str(image_url or "").strip():
            raise RuntimeError("AstrBot HTML 渲染器没有返回图片地址。")
        return InsightCardResult(
            image_url=str(image_url),
            theme=theme_key,
            theme_label=theme_config.label,
            mode=str(payload["mode"]),
            resolution=resolution_key,
        )


def build_insight_card_payload(
    snapshot: Mapping[str, Any],
    theme: InsightCardTheme,
    *,
    example_limit: int = 4,
    include_examples: bool = True,
) -> dict[str, Any]:
    report = snapshot.get("report")
    if not isinstance(report, Mapping):
        raise ValueError("当前没有可渲染的评论洞察结果。")
    exploratory = str(report.get("analysis_mode") or "") == "exploratory"
    filters = snapshot.get("filters")
    filters = filters if isinstance(filters, Mapping) else {}
    safe_example_limit = max(0, min(8, int(example_limit)))
    examples = (
        _examples(report.get("examples"), safe_example_limit, exploratory)
        if include_examples and safe_example_limit
        else []
    )
    base: dict[str, Any] = {
        "theme": asdict(theme),
        "mode": "exploratory" if exploratory else "directed",
        "mode_label": "自动探索" if exploratory else "定向统计",
        "generated_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        "link_id": _text(filters.get("link_id"), 24) or "全部帖子",
        "source": _source_label(filters.get("source")),
        "total_comments": _integer(report.get("total_comments")),
        "unique_users": _integer(report.get("unique_users")),
        "unique_posts": _integer(report.get("unique_posts")),
        "examples": examples,
        "examples_hidden": bool(report.get("examples_hidden")),
        "show_evidence": not (exploratory and theme.key == "editorial"),
    }
    if exploratory:
        base.update(_exploratory_payload(report))
    else:
        base.update(_directed_payload(report))
    base["evidence"] = _evidence_payload(report, exploratory)
    return base


def _exploratory_payload(report: Mapping[str, Any]) -> dict[str, Any]:
    sentiments = report.get("sentiment_counts")
    sentiments = sentiments if isinstance(sentiments, Mapping) else {}
    percentages = report.get("sentiment_percentages")
    percentages = percentages if isinstance(percentages, Mapping) else {}
    intents = report.get("intent_counts")
    intents = intents if isinstance(intents, Mapping) else {}
    sentiment_rows = [
        {
            "key": key,
            "label": label,
            "count": _integer(sentiments.get(key)),
            "percentage": _number(percentages.get(key)),
        }
        for key, label in SENTIMENT_LABELS.items()
    ]
    intent_rows = sorted(
        (
            {
                "key": str(key),
                "label": INTENT_LABELS.get(str(key), _text(key, 30)),
                "count": _integer(value),
            }
            for key, value in intents.items()
        ),
        key=lambda item: (-item["count"], item["label"]),
    )[:6]
    return {
        "headline": "",
        "summary": _text(report.get("summary"), 600)
        or "本次分析已完成，主要信号见下方数据。",
        "primary_value": _integer(report.get("analyzed_comments")),
        "primary_label": "已分析评论",
        "coverage_percent": _number(report.get("coverage_percent")),
        "coverage_label": "总体样本覆盖",
        "sentiments": sentiment_rows,
        "intents": intent_rows,
        "topics": _ranked_items(report.get("themes") or report.get("top_topics"), 6),
        "questions": _ranked_items(report.get("top_questions"), 4),
        "suggestions": _ranked_items(report.get("top_suggestions"), 4),
        "controversies": _text_items(report.get("controversies"), 4, 150),
        "findings": _text_items(report.get("notable_findings"), 4, 150),
        "criteria": [],
    }


def _directed_payload(report: Mapping[str, Any]) -> dict[str, Any]:
    criteria = report.get("criteria")
    criteria = criteria if isinstance(criteria, Mapping) else {}
    topic = _text(criteria.get("topic"), 180) or "指定条件"
    keyword_count = len(_sequence(criteria.get("keywords")))
    emoji_count = len(_sequence(criteria.get("emoji_tokens")))
    semantic_complete = bool(report.get("semantic_complete"))
    return {
        "headline": topic,
        "summary": (
            f"共确认 {_integer(report.get('union_matches'))} 条匹配评论，"
            f"占已归档评论的 {_number(report.get('union_percentage')):.2f}%。"
            + ("语义范围已完成。" if semantic_complete else "语义结果为当前已确认下限。")
        ),
        "primary_value": _integer(report.get("union_matches")),
        "primary_label": "确认匹配",
        "coverage_percent": _number(report.get("semantic_coverage_percent")),
        "coverage_label": "语义候选覆盖",
        "sentiments": [],
        "intents": [],
        "topics": [],
        "questions": [],
        "suggestions": [],
        "controversies": [],
        "findings": [
            f"关键词命中 {_integer(report.get('keyword_matches'))} 条",
            f"表情命中 {_integer(report.get('emoji_matches'))} 条",
            f"语义补充 {_integer(report.get('semantic_matches'))} 条",
        ],
        "criteria": [
            {"label": "主题", "value": topic},
            {"label": "关键词", "value": f"{keyword_count} 个"},
            {"label": "表情", "value": f"{emoji_count} 个"},
            {
                "label": "确定性命中",
                "value": str(_integer(report.get("deterministic_union"))),
            },
        ],
    }


def _evidence_payload(report: Mapping[str, Any], exploratory: bool) -> dict[str, Any]:
    raw = report.get("evidence")
    raw = raw if isinstance(raw, Mapping) else {}
    if exploratory:
        scope = raw.get("scope")
        scope = scope if isinstance(scope, Mapping) else {}
        return {
            "mode": "exploratory",
            "label": "分析依据",
            "summary": "按归档样本中的已分析评论汇总。",
            "scope": [
                {"label": "归档样本", "value": _integer(scope.get("archived"))},
                {"label": "入选样本", "value": _integer(scope.get("selected"))},
                {"label": "已分析", "value": _integer(scope.get("analyzed"))},
                {
                    "label": "总体覆盖",
                    "value": f"{_number(scope.get('coverage_percent')):.2f}%",
                },
            ],
            "layers": [],
            "overlap": [],
            "topics": _ranked_items(raw.get("topics"), 4),
        }

    layers: list[dict[str, Any]] = []
    for layer in _sequence(raw.get("layers"))[:3]:
        if not isinstance(layer, Mapping):
            continue
        layers.append(
            {
                "key": _text(layer.get("key"), 30),
                "label": _text(layer.get("label"), 40),
                "count": _integer(layer.get("count")),
                "percentage": _number(layer.get("percentage")),
                "items": [
                    {
                        "label": _text(item.get("label"), 80),
                        "count": _integer(item.get("count")),
                    }
                    for item in _sequence(layer.get("items"))[:8]
                    if isinstance(item, Mapping) and _text(item.get("label"), 80)
                ],
            }
        )
    return {
        "mode": "directed",
        "label": "分析依据",
        "summary": "先统计文字与表情，再对未命中的候选评论做语义补充；每层均按评论去重。",
        "scope": [
            {"label": "归档评论", "value": _integer(report.get("total_comments"))},
            {"label": "最终并集", "value": _integer(raw.get("final_union"))},
            {
                "label": "最终占比",
                "value": f"{_number(raw.get('final_percentage')):.2f}%",
            },
            {
                "label": "语义覆盖",
                "value": f"{_number(raw.get('semantic_coverage_percent')):.2f}%",
            },
        ],
        "layers": layers,
        "overlap": [
            {"label": "文字 / 表情重叠", "value": _integer(raw.get("keyword_emoji_overlap"))},
            {"label": "确定性去重并集", "value": _integer(raw.get("deterministic_union"))},
            {"label": "语义补充", "value": _integer(raw.get("semantic_matches"))},
        ],
        "topics": [],
    }


def _ranked_items(value: Any, limit: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in _sequence(value)[:limit]:
        if not isinstance(item, Mapping):
            continue
        label = _text(item.get("label"), 80)
        if not label:
            continue
        result.append(
            {
                "label": label,
                "count": _integer(item.get("count")),
                "percentage": _number(item.get("percentage")),
                "description": _text(item.get("description"), 180),
            }
        )
    return result


def _examples(value: Any, limit: int, exploratory: bool) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in _sequence(value)[:limit]:
        if not isinstance(item, Mapping):
            continue
        content = _text(item.get("content"), 240)
        if not content:
            continue
        if exploratory:
            labels = [
                SENTIMENT_LABELS.get(str(item.get("sentiment") or ""), ""),
                INTENT_LABELS.get(str(item.get("intent") or ""), ""),
            ]
            detail = _text(item.get("summary"), 100)
        else:
            labels = [
                {"keyword": "文字", "emoji": "表情", "semantic": "语义"}.get(
                    str(name), str(name)
                )
                for name in _sequence(item.get("matched_by"))
            ]
            detail = _text(item.get("reason"), 100)
        result.append(
            {
                "content": content,
                "labels": [label for label in labels if label],
                "detail": detail,
                "link_id": _integer(item.get("link_id")),
                "comment_id": _integer(item.get("comment_id")),
            }
        )
    return result


def _source_label(value: Any) -> str:
    return {
        "mention": "@ 消息",
        "own_post_comment": "自己帖子评论",
    }.get(str(value or ""), "全部来源")


def _text_items(value: Any, limit: int, max_length: int) -> list[str]:
    return [item for item in (_text(raw, max_length) for raw in _sequence(value)[:limit]) if item]


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _text(value: Any, max_length: int) -> str:
    text = " ".join(str(value or "").replace("\x00", " ").split())
    if len(text) <= max_length:
        return text
    return text[: max(1, max_length - 1)].rstrip() + "…"


def _integer(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _number(value: Any) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0
