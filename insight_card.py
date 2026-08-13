from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


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
        kicker="COMMUNITY SIGNAL / XHH",
        background="#050908",
        surface="#0a1210",
        surface_alt="#0d1915",
        text="#e1eee8",
        muted="#7e978c",
        line="#244438",
        accent="#79f2a8",
        accent_alt="#f4c96b",
        warning="#f0ad63",
        danger="#ff7770",
        font_family="'Microsoft YaHei UI', 'PingFang SC', sans-serif",
        title_family="Consolas, 'Microsoft YaHei UI', monospace",
        radius=2,
        shadow="0 28px 72px rgba(0, 0, 0, .48)",
        grid="linear-gradient(rgba(121,242,168,.035) 1px, transparent 1px), linear-gradient(90deg, rgba(121,242,168,.035) 1px, transparent 1px)",
    ),
    "cyberpunk": InsightCardTheme(
        key="cyberpunk",
        label="赛博朋克",
        kicker="NEON CROWD INTELLIGENCE",
        background="#090a10",
        surface="#11121b",
        surface_alt="#171823",
        text="#f3f5ff",
        muted="#9699ad",
        line="#34374b",
        accent="#38e8f2",
        accent_alt="#ff4fa3",
        warning="#e7f45b",
        danger="#ff6a67",
        font_family="'Microsoft YaHei UI', 'PingFang SC', sans-serif",
        title_family="'Arial Black', 'Microsoft YaHei UI', sans-serif",
        radius=6,
        shadow="12px 14px 0 rgba(56, 232, 242, .12), -7px -7px 0 rgba(255, 79, 163, .10)",
        grid="linear-gradient(rgba(56,232,242,.035) 1px, transparent 1px), linear-gradient(90deg, rgba(255,79,163,.035) 1px, transparent 1px)",
    ),
    "editorial": InsightCardTheme(
        key="editorial",
        label="编辑部报告",
        kicker="AUDIENCE DESK / FIELD NOTES",
        background="#ecebe7",
        surface="#fffefa",
        surface_alt="#f4f2ec",
        text="#202527",
        muted="#6c7473",
        line="#cfd2cc",
        accent="#087f79",
        accent_alt="#c73f3b",
        warning="#a66d18",
        danger="#a93238",
        font_family="'Microsoft YaHei UI', 'PingFang SC', sans-serif",
        title_family="Georgia, 'Songti SC', serif",
        radius=0,
        shadow="0 24px 58px rgba(32, 37, 39, .16)",
        grid="none",
    ),
    "command": InsightCardTheme(
        key="command",
        label="数据指挥台",
        kicker="COMMUNITY OPERATIONS BRIEF",
        background="#111416",
        surface="#181d20",
        surface_alt="#20272b",
        text="#f1f4f2",
        muted="#96a09d",
        line="#3d4948",
        accent="#45cfca",
        accent_alt="#ffba62",
        warning="#f0d36f",
        danger="#f07874",
        font_family="'Microsoft YaHei UI', 'PingFang SC', sans-serif",
        title_family="'Microsoft YaHei UI', 'PingFang SC', sans-serif",
        radius=4,
        shadow="0 28px 70px rgba(0, 0, 0, .38)",
        grid="linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px)",
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
    "editorial": "editorial",
    "report": "editorial",
    "编辑部": "editorial",
    "编辑部报告": "editorial",
    "command": "command",
    "dashboard": "command",
    "指挥台": "command",
    "数据指挥台": "command",
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


@dataclass(frozen=True, slots=True)
class InsightCardResult:
    image_url: str
    theme: str
    theme_label: str
    mode: str


class InsightCardRenderer:
    async def render(
        self,
        plugin: Any,
        snapshot: Mapping[str, Any],
        *,
        theme: Any = "",
        default_theme: str = "terminal",
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
                "viewport_width": 1080,
                "viewport_height": 720,
                "selector": "#insight-card",
                "full_page": True,
                "type": "png",
                "animations": "disabled",
                "caret": "hide",
                "scale": "device",
            },
        )
        if not str(image_url or "").strip():
            raise RuntimeError("AstrBot HTML 渲染器没有返回图片地址。")
        return InsightCardResult(
            image_url=str(image_url),
            theme=theme_key,
            theme_label=theme_config.label,
            mode=str(payload["mode"]),
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
        "job_id": _text(snapshot.get("job_id"), 24) or "LOCAL",
        "link_id": _text(filters.get("link_id"), 24) or "全部帖子",
        "source": _source_label(filters.get("source")),
        "provider_id": _text(report.get("provider_id"), 80) or "本地统计",
        "total_comments": _integer(report.get("total_comments")),
        "unique_users": _integer(report.get("unique_users")),
        "unique_posts": _integer(report.get("unique_posts")),
        "examples": examples,
        "examples_hidden": bool(report.get("examples_hidden")),
        "counting_note": _text(report.get("counting_note"), 320),
    }
    if exploratory:
        base.update(_exploratory_payload(report))
    else:
        base.update(_directed_payload(report))
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
        "headline": "评论区正在形成怎样的共识",
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


INSIGHT_CARD_TEMPLATE = r"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <style>
    * { box-sizing: border-box; }
    html, body { margin: 0; width: 1080px; background: {{ theme.background }}; }
    body { padding: 44px; color: {{ theme.text }}; font-family: {{ theme.font_family }}; }
    #insight-card {
      position: relative; width: 992px; min-height: 1240px; overflow: hidden;
      padding: 54px; border: 1px solid {{ theme.line }}; border-radius: {{ theme.radius }}px;
      background-color: {{ theme.surface }}; background-image: {{ theme.grid }};
      background-size: 30px 30px; box-shadow: {{ theme.shadow }};
    }
    #insight-card::before { content: ""; position: absolute; inset: 0 auto auto 0; width: 100%; height: 7px; background: {{ theme.accent }}; }
    #insight-card::after { content: ""; position: absolute; right: 0; top: 7px; width: 24%; height: 3px; background: {{ theme.accent_alt }}; }
    .header { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 28px; align-items: start; }
    .kicker { color: {{ theme.accent }}; font: 700 15px/1.3 {{ theme.title_family }}; }
    h1 { max-width: 690px; margin: 13px 0 0; font: 700 42px/1.18 {{ theme.title_family }}; overflow-wrap: anywhere; }
    .theme-mark { padding: 10px 14px; border: 1px solid {{ theme.line }}; color: {{ theme.muted }}; font-size: 14px; white-space: nowrap; }
    .context { display: flex; flex-wrap: wrap; gap: 10px 20px; margin-top: 23px; color: {{ theme.muted }}; font-size: 15px; }
    .context b { color: {{ theme.text }}; font-weight: 600; }
    .summary { margin: 34px 0 0; padding: 24px 26px; border-left: 5px solid {{ theme.accent_alt }}; background: {{ theme.surface_alt }}; font-size: 21px; line-height: 1.65; overflow-wrap: anywhere; }
    .metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px; margin: 30px 0; border: 1px solid {{ theme.line }}; background: {{ theme.line }}; }
    .metric { min-height: 120px; padding: 20px; background: {{ theme.surface }}; }
    .metric strong { display: block; color: {{ theme.accent }}; font: 700 34px/1 {{ theme.title_family }}; }
    .metric span { display: block; margin-top: 12px; color: {{ theme.muted }}; font-size: 14px; }
    .section { margin-top: 30px; }
    .section-title { display: flex; align-items: center; gap: 13px; margin: 0 0 15px; color: {{ theme.text }}; font: 700 19px/1.3 {{ theme.title_family }}; }
    .section-title::before { content: ""; width: 22px; height: 3px; background: {{ theme.accent }}; }
    .rank-list { display: grid; gap: 10px; }
    .rank { display: grid; grid-template-columns: 38px minmax(0, 1fr) auto; gap: 14px; align-items: center; padding: 15px 17px; border: 1px solid {{ theme.line }}; background: {{ theme.surface_alt }}; }
    .rank-index { color: {{ theme.accent_alt }}; font: 700 17px/1 {{ theme.title_family }}; }
    .rank-copy strong { display: block; font-size: 17px; overflow-wrap: anywhere; }
    .rank-copy small { display: block; margin-top: 5px; color: {{ theme.muted }}; font-size: 13px; line-height: 1.45; }
    .rank-value { color: {{ theme.accent }}; font: 700 17px/1 {{ theme.title_family }}; white-space: nowrap; }
    .two-column { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
    .signal-box { padding: 18px; border: 1px solid {{ theme.line }}; background: {{ theme.surface_alt }}; }
    .signal-box h3 { margin: 0 0 13px; color: {{ theme.accent_alt }}; font: 700 15px/1.3 {{ theme.title_family }}; }
    .signal-box ul { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
    .signal-box li { padding-bottom: 9px; border-bottom: 1px solid {{ theme.line }}; color: {{ theme.text }}; font-size: 15px; line-height: 1.5; overflow-wrap: anywhere; }
    .signal-box li:last-child { padding-bottom: 0; border-bottom: 0; }
    .sentiments { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
    .sentiment { padding: 15px; border: 1px solid {{ theme.line }}; background: {{ theme.surface_alt }}; }
    .sentiment strong { display: block; font: 700 22px/1 {{ theme.title_family }}; }
    .sentiment span { display: block; margin-top: 8px; color: {{ theme.muted }}; font-size: 13px; }
    .intent-row { display: flex; flex-wrap: wrap; gap: 9px; margin-top: 13px; }
    .chip { padding: 8px 11px; border: 1px solid {{ theme.line }}; color: {{ theme.text }}; background: {{ theme.surface_alt }}; font-size: 13px; }
    .criteria { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
    .criterion { min-width: 0; padding: 15px; border: 1px solid {{ theme.line }}; background: {{ theme.surface_alt }}; }
    .criterion span { display: block; color: {{ theme.muted }}; font-size: 12px; }
    .criterion strong { display: block; margin-top: 7px; font-size: 16px; overflow-wrap: anywhere; }
    .examples { display: grid; gap: 10px; }
    .example { padding: 18px; border: 1px solid {{ theme.line }}; background: {{ theme.surface_alt }}; }
    .example-tags { display: flex; flex-wrap: wrap; gap: 7px; margin-bottom: 10px; }
    .tag { padding: 4px 8px; color: {{ theme.background }}; background: {{ theme.accent }}; font-size: 11px; font-weight: 700; }
    .example blockquote { margin: 0; color: {{ theme.text }}; font-size: 16px; line-height: 1.55; overflow-wrap: anywhere; }
    .example-meta { margin-top: 10px; color: {{ theme.muted }}; font-size: 12px; }
    .footer { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 24px; align-items: end; margin-top: 34px; padding-top: 18px; border-top: 1px solid {{ theme.line }}; color: {{ theme.muted }}; font-size: 12px; line-height: 1.5; }
    .footer strong { color: {{ theme.accent }}; font-family: {{ theme.title_family }}; }
  </style>
</head>
<body>
  <article id="insight-card">
    <header class="header">
      <div>
        <div class="kicker">{{ theme.kicker | e }}</div>
        <h1>{{ headline | e }}</h1>
        <div class="context">
          <span>模式 <b>{{ mode_label | e }}</b></span>
          <span>帖子 <b>{{ link_id | e }}</b></span>
          <span>来源 <b>{{ source | e }}</b></span>
          <span>模型 <b>{{ provider_id | e }}</b></span>
        </div>
      </div>
      <div class="theme-mark">{{ theme.label | e }}</div>
    </header>

    <div class="summary">{{ summary | e }}</div>

    <div class="metrics">
      <div class="metric"><strong>{{ primary_value }}</strong><span>{{ primary_label | e }}</span></div>
      <div class="metric"><strong>{{ '%.2f' | format(coverage_percent) }}%</strong><span>{{ coverage_label | e }}</span></div>
      <div class="metric"><strong>{{ unique_users }}</strong><span>独立用户</span></div>
      <div class="metric"><strong>{{ total_comments }}</strong><span>归档评论</span></div>
    </div>

    {% if criteria %}
    <section class="section">
      <h2 class="section-title">定向条件</h2>
      <div class="criteria">
        {% for item in criteria %}<div class="criterion"><span>{{ item.label | e }}</span><strong>{{ item.value | e }}</strong></div>{% endfor %}
      </div>
    </section>
    {% endif %}

    {% if sentiments %}
    <section class="section">
      <h2 class="section-title">情绪与互动意图</h2>
      <div class="sentiments">
        {% for item in sentiments %}<div class="sentiment"><strong>{{ '%.2f' | format(item.percentage) }}%</strong><span>{{ item.label | e }} / {{ item.count }}</span></div>{% endfor %}
      </div>
      <div class="intent-row">
        {% for item in intents %}<span class="chip">{{ item.label | e }} {{ item.count }}</span>{% endfor %}
      </div>
    </section>
    {% endif %}

    {% if topics %}
    <section class="section">
      <h2 class="section-title">主要讨论信号</h2>
      <div class="rank-list">
        {% for item in topics %}
        <div class="rank"><div class="rank-index">{{ '%02d' | format(loop.index) }}</div><div class="rank-copy"><strong>{{ item.label | e }}</strong>{% if item.description %}<small>{{ item.description | e }}</small>{% endif %}</div><div class="rank-value">{{ item.count }} / {{ '%.2f' | format(item.percentage) }}%</div></div>
        {% endfor %}
      </div>
    </section>
    {% endif %}

    {% if questions or suggestions or controversies or findings %}
    <section class="section two-column">
      {% if questions %}<div class="signal-box"><h3>高频问题</h3><ul>{% for item in questions %}<li>{{ item.label | e }} · {{ item.count }}</li>{% endfor %}</ul></div>{% endif %}
      {% if suggestions %}<div class="signal-box"><h3>用户建议</h3><ul>{% for item in suggestions %}<li>{{ item.label | e }} · {{ item.count }}</li>{% endfor %}</ul></div>{% endif %}
      {% if controversies %}<div class="signal-box"><h3>争议与分歧</h3><ul>{% for item in controversies %}<li>{{ item | e }}</li>{% endfor %}</ul></div>{% endif %}
      {% if findings %}<div class="signal-box"><h3>值得注意</h3><ul>{% for item in findings %}<li>{{ item | e }}</li>{% endfor %}</ul></div>{% endif %}
    </section>
    {% endif %}

    {% if examples %}
    <section class="section">
      <h2 class="section-title">代表评论</h2>
      <div class="examples">
        {% for item in examples %}
        <article class="example">
          <div class="example-tags">{% for label in item.labels %}<span class="tag">{{ label | e }}</span>{% endfor %}</div>
          <blockquote>{{ item.content | e }}</blockquote>
          <div class="example-meta">帖子 {{ item.link_id }} / 评论 {{ item.comment_id }}{% if item.detail %} / {{ item.detail | e }}{% endif %}</div>
        </article>
        {% endfor %}
      </div>
    </section>
    {% endif %}

    <footer class="footer">
      <div>{{ counting_note | e }}</div>
      <div><strong>XHHBOT INSIGHT</strong><br>{{ generated_at | e }} / {{ job_id | e }}</div>
    </footer>
  </article>
</body>
</html>
"""
