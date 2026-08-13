INSIGHT_CARD_TEMPLATE = r"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <style>
    * { box-sizing: border-box; }
    html, body { margin: 0; width: 720px; background: {{ theme.background }}; }
    body { padding: 20px; color: {{ theme.text }}; font-family: {{ theme.font_family | safe }}; }
    #insight-card {
      position: relative; display: flex; flex-direction: column; width: 680px; min-height: 1040px; overflow: hidden;
      padding: 34px; border: 1px solid {{ theme.line }}; border-radius: {{ theme.radius }}px;
      background: {{ theme.surface }}; box-shadow: {{ theme.shadow }};
    }
    .header { display: flex; justify-content: space-between; gap: 18px; align-items: flex-start; }
    .header-copy { min-width: 0; }
    .kicker { color: {{ theme.accent }}; font: 800 19px/1.4 {{ theme.title_family | safe }}; text-transform: uppercase; }
    h1 { margin: 12px 0 0; font: 800 46px/1.16 {{ theme.title_family | safe }}; overflow-wrap: anywhere; }
    h1[hidden] { display: none; }
    .theme-mark { flex: 0 0 auto; padding: 9px 12px; border: 1px solid {{ theme.line }}; color: {{ theme.muted }}; font-size: 18px; font-weight: 700; }
    .context { display: flex; flex-wrap: wrap; gap: 10px 16px; margin-top: 16px; color: {{ theme.muted }}; font-size: 20px; line-height: 1.55; }
    .context b { color: {{ theme.text }}; font-weight: 750; }
    .summary { margin-top: 26px; padding: 24px 25px; background: {{ theme.surface_alt }}; border-left: 7px solid {{ theme.accent_alt }}; font-size: 30px; font-weight: 650; line-height: 1.62; overflow-wrap: anywhere; }
    .metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 22px; }
    .metric { min-height: 126px; padding: 21px; border: 1px solid {{ theme.line }}; background: {{ theme.surface_alt }}; }
    .metric strong { display: block; color: {{ theme.accent }}; font: 800 46px/1 {{ theme.title_family | safe }}; }
    .metric span { display: block; margin-top: 13px; color: {{ theme.muted }}; font-size: 21px; font-weight: 650; }
    .section { margin-top: 34px; }
    .section-title { display: flex; align-items: center; gap: 12px; margin: 0 0 17px; font: 800 30px/1.3 {{ theme.title_family | safe }}; }
    .section-title::before { content: ""; width: 28px; height: 5px; background: {{ theme.accent }}; }
    .criteria, .evidence-scope, .sentiments { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .criterion, .evidence-stat, .sentiment { min-width: 0; padding: 19px 20px; border: 1px solid {{ theme.line }}; background: {{ theme.surface_alt }}; }
    .criterion span, .evidence-stat span, .sentiment span { display: block; color: {{ theme.muted }}; font-size: 20px; line-height: 1.5; }
    .criterion strong, .evidence-stat strong { display: block; margin-top: 8px; font-size: 27px; overflow-wrap: anywhere; }
    .evidence-stat strong { color: {{ theme.accent }}; font-family: {{ theme.title_family | safe }}; }
    .sentiment strong { display: block; font: 800 34px/1 {{ theme.title_family | safe }}; }
    .sentiment span { margin-top: 10px; }
    .intent-row { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }
    .chip { padding: 10px 13px; border: 1px solid {{ theme.line }}; background: {{ theme.surface_alt }}; font-size: 20px; font-weight: 700; }
    .rank-list { display: grid; gap: 12px; }
    .rank { display: grid; grid-template-columns: 44px minmax(0, 1fr); gap: 14px; padding: 20px; border: 1px solid {{ theme.line }}; background: {{ theme.surface_alt }}; }
    .rank-index { color: {{ theme.accent_alt }}; font: 800 22px/1.35 {{ theme.title_family | safe }}; }
    .rank-copy strong { display: block; padding-right: 8px; font-size: 27px; line-height: 1.4; overflow-wrap: anywhere; }
    .rank-copy small { display: block; margin-top: 8px; color: {{ theme.muted }}; font-size: 21px; line-height: 1.6; }
    .rank-value { grid-column: 2; margin-top: 4px; color: {{ theme.accent }}; font: 800 23px/1 {{ theme.title_family | safe }}; }
    .signal-grid { display: grid; gap: 14px; }
    .signal-box { padding: 22px; border: 1px solid {{ theme.line }}; background: {{ theme.surface_alt }}; }
    .signal-box h3 { margin: 0 0 14px; color: {{ theme.accent_alt }}; font: 800 26px/1.3 {{ theme.title_family | safe }}; }
    .signal-box ul { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
    .signal-box li { position: relative; padding-left: 22px; font-size: 24px; line-height: 1.58; overflow-wrap: anywhere; }
    .signal-box li::before { content: ""; position: absolute; left: 0; top: .66em; width: 8px; height: 8px; background: {{ theme.accent }}; }
    .evidence-layers { display: grid; gap: 10px; margin-top: 14px; }
    .evidence-layer { padding: 19px 20px; border: 1px solid {{ theme.line }}; background: {{ theme.surface_alt }}; }
    .evidence-layer strong { font-size: 25px; }
    .evidence-layer small { display: block; margin-top: 7px; color: {{ theme.muted }}; font-size: 20px; line-height: 1.55; }
    .evidence-layer-value { margin-top: 12px; color: {{ theme.accent }}; font: 800 24px/1 {{ theme.title_family | safe }}; }
    .evidence-overlap { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }
    .evidence-overlap span { padding: 9px 12px; border: 1px solid {{ theme.line }}; color: {{ theme.muted }}; font-size: 20px; }
    .evidence-overlap strong { margin-left: 8px; color: {{ theme.text }}; }
    .examples { display: grid; gap: 14px; }
    .example { padding: 22px; border: 1px solid {{ theme.line }}; background: {{ theme.surface_alt }}; }
    .example-tags { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 13px; }
    .tag { padding: 7px 11px; color: {{ theme.surface }}; background: {{ theme.accent }}; font-size: 18px; font-weight: 800; }
    .example blockquote { margin: 0; font-size: 27px; font-weight: 650; line-height: 1.62; overflow-wrap: anywhere; }
    .example-meta { margin-top: 12px; color: {{ theme.muted }}; font-size: 19px; line-height: 1.55; }
    .footer { display: flex; justify-content: space-between; gap: 20px; margin-top: 38px; padding-top: 18px; border-top: 1px solid {{ theme.line }}; color: {{ theme.muted }}; font-size: 17px; }
    .footer strong { color: {{ theme.accent }}; font-family: {{ theme.title_family | safe }}; }

    /* Terminal: fluorescent glass surfaces over an explicit console grid. */
    .theme-terminal#insight-card {
      border-color: rgba(98, 245, 157, .72);
      background-color: #050c09;
      background-image:
        linear-gradient(rgba(98, 245, 157, .08) 1px, transparent 1px),
        linear-gradient(90deg, rgba(98, 245, 157, .08) 1px, transparent 1px),
        repeating-linear-gradient(0deg, transparent 0 5px, rgba(98, 245, 157, .025) 5px 6px);
      background-size: 32px 32px, 32px 32px, 100% 6px;
      box-shadow: 0 0 0 1px rgba(98, 245, 157, .12), 0 0 34px rgba(98, 245, 157, .16);
    }
    .theme-terminal#insight-card::before {
      content: "[ ONLINE ]  XHHBOT ANALYTICS"; display: block; margin: -34px -34px 30px; padding: 16px 20px;
      color: {{ theme.accent }}; border-bottom: 1px solid rgba(98, 245, 157, .62);
      background: linear-gradient(90deg, rgba(98, 245, 157, .22), rgba(54, 231, 242, .08) 62%, rgba(5, 12, 9, .74));
      text-shadow: 0 0 12px rgba(98, 245, 157, .65); font: 800 18px/1 {{ theme.title_family | safe }};
    }
    .theme-terminal .theme-mark { border-color: rgba(98, 245, 157, .72); color: {{ theme.accent }}; background: rgba(98, 245, 157, .07); box-shadow: inset 0 0 18px rgba(98, 245, 157, .05); }
    .theme-terminal .summary { border-color: {{ theme.accent_alt }}; background: linear-gradient(135deg, rgba(255, 209, 102, .14), rgba(98, 245, 157, .055)); }
    .theme-terminal .section-title { color: {{ theme.accent }}; text-shadow: 0 0 10px rgba(98, 245, 157, .26); }
    .theme-terminal .section-title::before { content: ">"; width: auto; height: auto; color: {{ theme.accent }}; background: none; }
    .theme-terminal .metric, .theme-terminal .criterion, .theme-terminal .evidence-stat, .theme-terminal .sentiment, .theme-terminal .rank, .theme-terminal .signal-box, .theme-terminal .example, .theme-terminal .evidence-layer, .theme-terminal .chip {
      border-color: rgba(98, 245, 157, .34); border-left-width: 4px;
      background: linear-gradient(135deg, rgba(98, 245, 157, .105), rgba(54, 231, 242, .025) 72%);
      box-shadow: inset 0 0 22px rgba(98, 245, 157, .025);
    }
    .theme-terminal .metric:nth-child(even), .theme-terminal .sentiment:nth-child(even), .theme-terminal .signal-box:nth-child(even) { background: linear-gradient(135deg, rgba(54, 231, 242, .09), rgba(98, 245, 157, .03) 72%); }
    .theme-terminal .tag { color: {{ theme.accent }}; border: 1px solid rgba(98, 245, 157, .58); background: rgba(98, 245, 157, .12); text-shadow: 0 0 8px rgba(98, 245, 157, .3); }
    .theme-terminal .header { order: 10; }
    .theme-terminal .summary { order: 20; }
    .theme-terminal .metrics { order: 30; }
    .theme-terminal .criteria-section { order: 35; }
    .theme-terminal .sentiment-section { order: 40; }
    .theme-terminal .topics-section { order: 50; }
    .theme-terminal .signals-section { order: 60; }
    .theme-terminal .evidence-section { order: 70; }
    .theme-terminal .examples-section { order: 80; }
    .theme-terminal .footer { order: 90; }

    /* Neon street edition: translucent fluorescent gradients, never flat color slabs. */
    .theme-cyberpunk#insight-card {
      padding: 42px; border: 1px solid rgba(54, 231, 242, .62);
      background-color: #0c0913;
      background-image: linear-gradient(145deg, rgba(255, 79, 154, .075), transparent 26%, rgba(54, 231, 242, .055) 70%, transparent);
      box-shadow: 0 0 0 7px rgba(255, 79, 154, .055), 0 0 34px rgba(255, 79, 154, .22), 0 0 20px rgba(54, 231, 242, .14);
    }
    .theme-cyberpunk .header {
      position: relative; padding: 24px; border: 1px solid rgba(255, 79, 154, .55); border-left: 7px solid {{ theme.accent_alt }};
      background: linear-gradient(135deg, rgba(255, 79, 154, .24), rgba(90, 44, 140, .13) 52%, rgba(54, 231, 242, .08));
      box-shadow: inset 0 0 30px rgba(255, 79, 154, .055), 0 0 16px rgba(255, 79, 154, .08);
    }
    .theme-cyberpunk .kicker { color: #ff80b7; text-shadow: 0 0 12px rgba(255, 79, 154, .45); }
    .theme-cyberpunk .context { color: {{ theme.muted }}; }
    .theme-cyberpunk .context b { color: {{ theme.text }}; }
    .theme-cyberpunk .theme-mark { border-color: rgba(54, 231, 242, .68); color: {{ theme.accent }}; background: rgba(54, 231, 242, .08); box-shadow: 0 0 14px rgba(54, 231, 242, .12); }
    .theme-cyberpunk .summary {
      color: {{ theme.text }}; border: 1px solid rgba(232, 255, 63, .46); border-left: 7px solid {{ theme.warning }};
      background: linear-gradient(135deg, rgba(232, 255, 63, .17), rgba(255, 79, 154, .075) 64%, rgba(54, 231, 242, .055));
      box-shadow: inset 0 0 28px rgba(232, 255, 63, .035);
    }
    .theme-cyberpunk .metrics { gap: 16px; }
    .theme-cyberpunk .metric { border-color: rgba(54, 231, 242, .48); background: linear-gradient(145deg, rgba(54, 231, 242, .22), rgba(54, 231, 242, .045) 68%, rgba(255, 79, 154, .035)); box-shadow: inset 0 0 24px rgba(54, 231, 242, .045); }
    .theme-cyberpunk .metric:nth-child(even) { border-color: rgba(255, 79, 154, .5); background: linear-gradient(145deg, rgba(255, 79, 154, .22), rgba(255, 79, 154, .045) 68%, rgba(54, 231, 242, .035)); box-shadow: inset 0 0 24px rgba(255, 79, 154, .045); }
    .theme-cyberpunk .metric strong { color: {{ theme.accent }}; text-shadow: 0 0 12px rgba(54, 231, 242, .28); }
    .theme-cyberpunk .metric:nth-child(even) strong { color: #ff78b1; text-shadow: 0 0 12px rgba(255, 79, 154, .28); }
    .theme-cyberpunk .section-title { padding: 11px 15px; color: {{ theme.text }}; border-left: 6px solid {{ theme.accent }}; background: linear-gradient(90deg, rgba(54, 231, 242, .19), rgba(255, 79, 154, .08) 70%, transparent); box-shadow: inset 0 0 22px rgba(54, 231, 242, .035); }
    .theme-cyberpunk .section-title::before { display: none; }
    .theme-cyberpunk .rank, .theme-cyberpunk .signal-box, .theme-cyberpunk .example, .theme-cyberpunk .criterion, .theme-cyberpunk .evidence-stat, .theme-cyberpunk .sentiment, .theme-cyberpunk .evidence-layer, .theme-cyberpunk .chip {
      border-color: rgba(151, 115, 170, .48); background: linear-gradient(135deg, rgba(255, 79, 154, .095), rgba(54, 231, 242, .055) 68%, rgba(17, 16, 22, .2));
    }
    .theme-cyberpunk .rank:nth-child(even), .theme-cyberpunk .signal-box:nth-child(even), .theme-cyberpunk .example:nth-child(even), .theme-cyberpunk .sentiment:nth-child(even) { background: linear-gradient(135deg, rgba(54, 231, 242, .105), rgba(255, 79, 154, .05) 70%, rgba(17, 16, 22, .2)); }
    .theme-cyberpunk .tag { color: {{ theme.text }}; border: 1px solid rgba(54, 231, 242, .58); background: linear-gradient(135deg, rgba(54, 231, 242, .28), rgba(255, 79, 154, .14)); box-shadow: 0 0 10px rgba(54, 231, 242, .12); }
    .theme-cyberpunk .header { order: 10; }
    .theme-cyberpunk .metrics { order: 20; }
    .theme-cyberpunk .summary { order: 30; }
    .theme-cyberpunk .topics-section { order: 40; }
    .theme-cyberpunk .examples-section { order: 50; }
    .theme-cyberpunk .sentiment-section { order: 60; }
    .theme-cyberpunk .signals-section { order: 70; }
    .theme-cyberpunk .criteria-section { order: 75; }
    .theme-cyberpunk .evidence-section { order: 80; }
    .theme-cyberpunk .footer { order: 90; }

    /* Editorial front page: paper, rules, serif hierarchy and calm reading rhythm. */
    .theme-editorial#insight-card { padding: 46px 44px; border-top: 12px solid {{ theme.accent }}; }
    .theme-editorial .header { padding-bottom: 26px; border-bottom: 4px double {{ theme.text }}; }
    .theme-editorial .kicker { color: {{ theme.accent_alt }}; }
    .theme-editorial .summary { padding: 0 0 0 24px; background: transparent; border-color: {{ theme.accent }}; font-family: {{ theme.title_family | safe }}; font-size: 30px; }
    .theme-editorial .metrics { gap: 0; border-top: 2px solid {{ theme.text }}; border-bottom: 2px solid {{ theme.text }}; }
    .theme-editorial .metric { border: 0; border-right: 1px solid {{ theme.line }}; background: transparent; }
    .theme-editorial .metric:nth-child(2n) { border-right: 0; }
    .theme-editorial .section-title { padding-bottom: 8px; border-bottom: 3px solid {{ theme.text }}; }
    .theme-editorial .section-title::before { width: 8px; height: 28px; background: {{ theme.accent_alt }}; }
    .theme-editorial .rank, .theme-editorial .signal-box, .theme-editorial .example, .theme-editorial .criterion, .theme-editorial .evidence-stat, .theme-editorial .sentiment, .theme-editorial .evidence-layer { background: transparent; border-width: 0 0 1px; }
    .theme-editorial .header { order: 10; }
    .theme-editorial .summary { order: 20; }
    .theme-editorial .topics-section { order: 30; }
    .theme-editorial .signals-section { order: 40; }
    .theme-editorial .examples-section { order: 50; }
    .theme-editorial .metrics { order: 60; }
    .theme-editorial .sentiment-section { order: 70; }
    .theme-editorial .criteria-section { order: 75; }
    .theme-editorial .evidence-section { order: 80; }
    .theme-editorial .footer { order: 90; }

    /* Signal poster: asymmetric editorial scale, bold ink blocks and print rhythm. */
    .theme-command#insight-card { padding: 38px; border: 2px solid #171616; background: #f5f1e8; box-shadow: 16px 16px 0 #ef4136; }
    .theme-command .header { position: relative; margin: -38px -38px 0; padding: 34px 34px 30px; color: #fff; border-bottom: 12px solid {{ theme.warning }}; background: #171616; overflow: hidden; }
    .theme-command .header::after { content: ""; position: absolute; top: 0; right: -38px; width: 170px; height: 100%; background: {{ theme.accent_alt }}; clip-path: polygon(48% 0, 100% 0, 100% 100%, 0 100%); opacity: .96; }
    .theme-command .header-copy, .theme-command .theme-mark { position: relative; z-index: 1; }
    .theme-command .kicker { color: {{ theme.warning }}; }
    .theme-command .context { color: #d8d4ca; }
    .theme-command .context b { color: #fff; }
    .theme-command .theme-mark { border: 2px solid {{ theme.warning }}; color: {{ theme.warning }}; background: #171616; }
    .theme-command .summary { margin: 0 -38px; padding: 32px 38px 34px; color: #171616; border: 0; border-bottom: 3px solid #171616; background: {{ theme.warning }}; font-size: 33px; font-weight: 800; line-height: 1.48; }
    .theme-command .metrics { grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 10px; margin-top: 28px; }
    .theme-command .metric { display: flex; min-height: 154px; flex-direction: column; justify-content: flex-end; border: 2px solid #171616; background: #fffdf7; }
    .theme-command .metric strong { font-size: 54px; }
    .theme-command .metric:first-child { grid-column: span 7; color: #fff; background: {{ theme.accent }}; }
    .theme-command .metric:first-child strong, .theme-command .metric:first-child span { color: #fff; }
    .theme-command .metric:nth-child(2) { grid-column: span 5; color: #fff; background: #171616; }
    .theme-command .metric:nth-child(2) strong { color: {{ theme.warning }}; }
    .theme-command .metric:nth-child(2) span { color: #ece8de; }
    .theme-command .metric:nth-child(3) { grid-column: span 5; color: #fff; background: {{ theme.accent_alt }}; }
    .theme-command .metric:nth-child(3) strong, .theme-command .metric:nth-child(3) span { color: #fff; }
    .theme-command .metric:nth-child(4) { grid-column: span 7; }
    .theme-command .section-title { gap: 14px; padding: 10px 0 11px; border-top: 6px solid #171616; border-bottom: 2px solid #171616; font-size: 32px; }
    .theme-command .section-title::before { width: 18px; height: 18px; background: {{ theme.accent_alt }}; transform: rotate(45deg); }
    .theme-command .rank-list { gap: 0; }
    .theme-command .rank { grid-template-columns: 72px minmax(0, 1fr); gap: 10px; padding: 23px 4px; border: 0; border-bottom: 2px solid #171616; background: transparent; }
    .theme-command .rank-index { color: {{ theme.accent_alt }}; font-size: 42px; line-height: 1; }
    .theme-command .rank-value { color: {{ theme.accent }}; }
    .theme-command .signal-grid { gap: 20px; }
    .theme-command .signal-box { border: 2px solid #171616; border-left: 12px solid {{ theme.accent_alt }}; background: #fffdf7; box-shadow: 7px 7px 0 #171616; }
    .theme-command .signal-box:nth-child(even) { border-left-color: {{ theme.accent }}; }
    .theme-command .signal-box h3 { color: {{ theme.accent_alt }}; }
    .theme-command .signal-box:nth-child(even) h3 { color: {{ theme.accent }}; }
    .theme-command .criterion, .theme-command .evidence-stat, .theme-command .sentiment, .theme-command .evidence-layer { border: 2px solid #171616; background: #fffdf7; }
    .theme-command .chip { border: 2px solid #171616; background: {{ theme.warning }}; }
    .theme-command .example { color: #fff; border: 0; border-left: 12px solid {{ theme.warning }}; background: #171616; }
    .theme-command .example-meta { color: #c8c2b8; }
    .theme-command .tag { color: #fff; background: {{ theme.accent }}; }
    .theme-command .header { order: 10; }
    .theme-command .summary { order: 20; }
    .theme-command .metrics { order: 30; }
    .theme-command .signals-section { order: 40; }
    .theme-command .topics-section { order: 50; }
    .theme-command .sentiment-section { order: 60; }
    .theme-command .criteria-section { order: 65; }
    .theme-command .evidence-section { order: 70; }
    .theme-command .examples-section { order: 80; }
    .theme-command .footer { order: 90; }
  </style>
</head>
<body>
  <article id="insight-card" class="theme-{{ theme.key | e }} mode-{{ mode | e }}">
    <header class="header">
      <div class="header-copy">
        <div class="kicker">{{ theme.kicker | e }}</div>
        <h1{% if not headline %} hidden{% endif %}>{{ headline | e }}</h1>
        <div class="context">
          <span>模式 <b>{{ mode_label | e }}</b></span>
          <span>帖子 <b>{{ link_id | e }}</b></span>
          <span>来源 <b>{{ source | e }}</b></span>
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
    <section class="section criteria-section">
      <h2 class="section-title">定向条件</h2>
      <div class="criteria">{% for item in criteria %}<div class="criterion"><span>{{ item.label | e }}</span><strong>{{ item.value | e }}</strong></div>{% endfor %}</div>
    </section>
    {% endif %}

    {% if sentiments %}
    <section class="section sentiment-section">
      <h2 class="section-title">情绪与互动意图</h2>
      <div class="sentiments">{% for item in sentiments %}<div class="sentiment"><strong>{{ '%.2f' | format(item.percentage) }}%</strong><span>{{ item.label | e }} / {{ item.count }}</span></div>{% endfor %}</div>
      <div class="intent-row">{% for item in intents %}<span class="chip">{{ item.label | e }} {{ item.count }}</span>{% endfor %}</div>
    </section>
    {% endif %}

    {% if topics %}
    <section class="section topics-section">
      <h2 class="section-title">主要讨论信号</h2>
      <div class="rank-list">
        {% for item in topics %}<div class="rank"><div class="rank-index">{{ '%02d' | format(loop.index) }}</div><div class="rank-copy"><strong>{{ item.label | e }}</strong>{% if item.description %}<small>{{ item.description | e }}</small>{% endif %}</div><div class="rank-value">{{ item.count }} / {{ '%.2f' | format(item.percentage) }}%</div></div>{% endfor %}
      </div>
    </section>
    {% endif %}

    {% if questions or suggestions or controversies or findings %}
    <section class="section signals-section">
      <h2 class="section-title">可行动信号</h2>
      <div class="signal-grid">
        {% if questions %}<div class="signal-box"><h3>高频问题</h3><ul>{% for item in questions %}<li>{{ item.label | e }} · {{ item.count }}</li>{% endfor %}</ul></div>{% endif %}
        {% if suggestions %}<div class="signal-box"><h3>用户建议</h3><ul>{% for item in suggestions %}<li>{{ item.label | e }} · {{ item.count }}</li>{% endfor %}</ul></div>{% endif %}
        {% if controversies %}<div class="signal-box"><h3>争议与分歧</h3><ul>{% for item in controversies %}<li>{{ item | e }}</li>{% endfor %}</ul></div>{% endif %}
        {% if findings %}<div class="signal-box"><h3>值得注意</h3><ul>{% for item in findings %}<li>{{ item | e }}</li>{% endfor %}</ul></div>{% endif %}
      </div>
    </section>
    {% endif %}

    {% if show_evidence and evidence.scope %}
    <section class="section evidence-section">
      <h2 class="section-title">{{ evidence.label | e }}</h2>
      <div class="evidence-scope">{% for item in evidence.scope %}<div class="evidence-stat"><span>{{ item.label | e }}</span><strong>{{ item.value | e }}</strong></div>{% endfor %}</div>
      {% if evidence.layers %}<div class="evidence-layers">{% for item in evidence.layers %}<div class="evidence-layer"><strong>{{ item.label | e }}</strong>{% if item.items %}<small>{% for detail in item.items %}{{ detail.label | e }} {{ detail.count }}{% if not loop.last %} · {% endif %}{% endfor %}</small>{% endif %}<div class="evidence-layer-value">{{ item.count }} / {{ '%.2f' | format(item.percentage) }}%</div></div>{% endfor %}</div>{% endif %}
      {% if evidence.overlap %}<div class="evidence-overlap">{% for item in evidence.overlap %}<span>{{ item.label | e }}<strong>{{ item.value }}</strong></span>{% endfor %}</div>{% endif %}
    </section>
    {% endif %}

    {% if examples %}
    <section class="section examples-section">
      <h2 class="section-title">代表评论</h2>
      <div class="examples">
        {% for item in examples %}<article class="example"><div class="example-tags">{% for label in item.labels %}<span class="tag">{{ label | e }}</span>{% endfor %}</div><blockquote>{{ item.content | e }}</blockquote><div class="example-meta">帖子 {{ item.link_id }} · 评论 {{ item.comment_id }}{% if item.detail %} · {{ item.detail | e }}{% endif %}</div></article>{% endfor %}
      </div>
    </section>
    {% endif %}

    <footer class="footer"><strong>XHHBOT INSIGHT</strong><span>{{ generated_at | e }}</span></footer>
  </article>
</body>
</html>
"""
