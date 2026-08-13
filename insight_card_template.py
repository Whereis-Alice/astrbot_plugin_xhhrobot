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

    /* Terminal: restrained console, scan lines, command-like labels. */
    .theme-terminal#insight-card { border-color: {{ theme.accent }}; background-image: repeating-linear-gradient(0deg, transparent 0 5px, rgba(98,245,157,.018) 5px 6px); }
    .theme-terminal#insight-card::before { content: "[ ONLINE ]  XHHBOT ANALYTICS"; display: block; margin: -34px -34px 30px; padding: 16px 20px; color: {{ theme.background }}; background: {{ theme.accent }}; font: 800 18px/1 {{ theme.title_family | safe }}; }
    .theme-terminal .theme-mark { border-color: {{ theme.accent }}; color: {{ theme.accent }}; }
    .theme-terminal .section-title::before { content: ">"; width: auto; height: auto; color: {{ theme.accent }}; background: none; }
    .theme-terminal .metric, .theme-terminal .criterion, .theme-terminal .evidence-stat, .theme-terminal .sentiment, .theme-terminal .rank, .theme-terminal .signal-box, .theme-terminal .example, .theme-terminal .evidence-layer { border-left-width: 4px; }
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

    /* Neon street edition: asymmetric poster blocks and oversized numbers. */
    .theme-cyberpunk#insight-card { border: 8px solid {{ theme.text }}; padding: 42px; }
    .theme-cyberpunk .header { padding: 22px; background: {{ theme.accent_alt }}; transform: rotate(-.45deg); }
    .theme-cyberpunk .kicker, .theme-cyberpunk .context, .theme-cyberpunk .context b { color: #111016; }
    .theme-cyberpunk .theme-mark { border: 2px solid #111016; color: #111016; }
    .theme-cyberpunk .summary { border: 0; color: #111016; background: {{ theme.warning }}; transform: rotate(.35deg); }
    .theme-cyberpunk .metrics { gap: 16px; }
    .theme-cyberpunk .metric:nth-child(odd) { background: {{ theme.accent }}; color: #111016; transform: rotate(-.4deg); }
    .theme-cyberpunk .metric:nth-child(even) { background: {{ theme.accent_alt }}; color: #111016; transform: rotate(.4deg); }
    .theme-cyberpunk .metric strong, .theme-cyberpunk .metric span { color: #111016; }
    .theme-cyberpunk .section-title { padding: 10px 14px; color: #111016; background: {{ theme.accent }}; }
    .theme-cyberpunk .section-title::before { display: none; }
    .theme-cyberpunk .tag { color: #111016; }
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

    /* Signal room: operational bands, numbered sections and hard status blocks. */
    .theme-command#insight-card { border: 0; border-left: 18px solid {{ theme.accent }}; }
    .theme-command .header { margin: -34px -34px 0; padding: 32px 30px; color: #f7fff9; background: #18332b; }
    .theme-command .kicker { color: #87e5c4; }
    .theme-command .context, .theme-command .context b { color: #d9eee5; }
    .theme-command .theme-mark { border-color: #87e5c4; color: #87e5c4; }
    .theme-command .summary { margin: 0 -34px; padding: 28px 30px; color: #fff; background: {{ theme.accent_alt }}; border: 0; }
    .theme-command .metrics { margin-top: 0; gap: 0; border: 1px solid {{ theme.line }}; }
    .theme-command .metric { border: 0; border-right: 1px solid {{ theme.line }}; border-bottom: 1px solid {{ theme.line }}; background: transparent; }
    .theme-command .section { counter-increment: section; }
    .theme-command .section-title::before { content: counter(section, decimal-leading-zero); display: grid; place-items: center; width: 44px; height: 44px; color: #fff; background: {{ theme.accent }}; font: 800 17px/1 {{ theme.title_family | safe }}; }
    .theme-command .rank { border-left: 7px solid {{ theme.accent }}; }
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
  <article id="insight-card" class="theme-{{ theme.key | e }}">
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

    {% if evidence.scope %}
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
