"""
龙眼 A股深度研判系统 v3.0
虎之眼 (Eye of Tiger) 金融内核
"""
import streamlit as st
import glob
import os
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.engine import AShareDataEngine
from core.agents import LongEyeOrchestrator

# ── 页面配置 ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="🐉 龙眼 Pro — 虎之眼内核",
    page_icon="🐉",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 品牌水印 CSS ──────────────────────────────────────────────────────
st.markdown("""
<style>
  /* 全局品牌色 */
  :root { --tiger-red:#CC0000; --tiger-gold:#FFD700; --tiger-dark:#0d0d0d; }

  .tiger-h1 {
      background: linear-gradient(135deg,#8B0000,#CC0000,#FF8C00);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      font-size: 1.9rem; font-weight: 900; letter-spacing: 2px; margin: 0;
  }
  .brand-bar {
      background: linear-gradient(90deg,#1a0000,#2d0000);
      border-left: 4px solid var(--tiger-red);
      padding: 6px 14px; border-radius: 4px;
      color: var(--tiger-gold); font-size: 0.78rem; font-style: italic;
      margin-bottom: 6px;
  }
  .verdict-box {
      background: var(--tiger-dark);
      border-left: 5px solid var(--tiger-red);
      border-radius: 8px; padding: 1.3rem;
      color: var(--tiger-gold); line-height: 1.75; font-size: 0.94rem;
  }
  .pool-card {
      background: #111; border: 1px solid #2a2a2a;
      border-radius: 8px; padding: 10px 14px; margin-bottom: 8px;
  }
  .pool-card:hover { border-color: var(--tiger-red); }
  .gain-badge {
      display: inline-block; border-radius: 20px;
      padding: 2px 10px; font-size: 0.78rem; font-weight: 700;
  }
  .gain-green  { background:#003300; color:#00FF88; }
  .gain-yellow { background:#332200; color:#FFCC00; }
  .gain-red    { background:#330000; color:#FF6666; }
  .chip-bar-outer { background:#222; border-radius:6px; height:14px; overflow:hidden; margin:3px 0; }
  .chip-bar-inner { height:100%; border-radius:6px; }
  /* 页脚水印 */
  footer::after {
      content: "🐉 龙眼研判系统 · 虎之眼 (Eye of Tiger) 金融内核 · 仅供学习研究";
      display: block; text-align: center;
      color: #444; font-size: 0.72rem; padding: 8px 0;
  }
</style>
""", unsafe_allow_html=True)

# ── Session State ─────────────────────────────────────────────────────
_SS_DEFAULTS = {
    "active_ticker":    "600519",
    "pool_df":          None,
    "pool_label":       "",
    "analysis_result":  None,
    "ai_pool_df":       None,
    "ai_pool_label":    "",
}
for k, v in _SS_DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── 初始化系统 ────────────────────────────────────────────────────────
@st.cache_resource
def init_system():
    return AShareDataEngine(), LongEyeOrchestrator(api_key=st.secrets["GEMINI_KEY"])

engine, orchestrator = init_system()

# ── 工具函数 ──────────────────────────────────────────────────────────
def _f(val, default=0.0):
    try:    return float(val)
    except: return default

def _pct(val):
    return f"{_f(val):+.2f}%"

def _extract_drive(orch, text):
    if hasattr(orch, "extract_drive_type"):
        return orch.extract_drive_type(text)
    for t in ["价值驱动", "博弈驱动", "政策陷阱"]:
        if t in text: return t
    return "—"

def _gain_badge(label: str) -> str:
    if "🏆" in label:
        return f'<span class="gain-badge gain-red">{label}</span>'
    if "✅" in label:
        return f'<span class="gain-badge gain-yellow">{label}</span>'
    return f'<span class="gain-badge gain-green">{label}</span>'


# ════════════════════════════════════════════════════════════════════
#  侧边栏（3 个功能 Tab）
# ════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(
        '<p style="font-size:1.4rem;font-weight:900;color:#CC0000;margin:0;">🐉 龙眼研判</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<span style="font-size:0.72rem;color:#FF8C00;font-style:italic;">'
        '虎之眼 Eye of Tiger 金融内核</span>',
        unsafe_allow_html=True,
    )
    st.divider()

    sb_t1, sb_t2, sb_t3 = st.tabs(["📊 股票研判", "🔭 选股雷达", "🤖 AI选股"])

    # ──────────────────────────────────────────────────────────────
    # Tab 1：股票研判
    # ──────────────────────────────────────────────────────────────
    with sb_t1:
        ticker_input = st.text_input(
            "股票代码",
            value=st.session_state["active_ticker"],
            placeholder="如 600519 / 000858",
            label_visibility="visible",
        )
        if ticker_input.strip():
            st.session_state["active_ticker"] = ticker_input.strip()

        skill_paths   = sorted(glob.glob("skills/0[1-6]*.md"))
        active_skills = [
            s for s in skill_paths
            if st.checkbox(os.path.basename(s)[3:-3], value=True, key=f"sk_{s}")
        ]

        run_btn = st.button(
            "🚀 启动全维度审计",
            type="primary", use_container_width=True, key="run_btn",
        )

    # ──────────────────────────────────────────────────────────────
    # Tab 2：选股雷达
    # ──────────────────────────────────────────────────────────────
    with sb_t2:
        strat    = st.selectbox("策略", ["涨停最强", "虎之眼价值", "全市场监控"],
                                label_visibility="collapsed")
        scan_btn = st.button("🔭 扫描市场信号", use_container_width=True, key="scan_btn")

        if scan_btn:
            with st.spinner("虎之眼雷达扫描..."):
                _pool = engine.get_strategy_pool(strat)
            st.session_state["pool_df"]    = _pool
            st.session_state["pool_label"] = strat

        radar_df = st.session_state["pool_df"]
        if radar_df is not None and not radar_df.empty:
            st.caption(f"📋 {st.session_state['pool_label']}")
            for _, row in radar_df.head(12).iterrows():
                code = str(row.get("代码", ""))
                name = str(row.get("名称", code))[:6]
                chg  = _f(row.get("涨跌幅", 0))
                win  = row.get("AI胜率标签", "")
                c_a, c_b = st.columns([3, 2])
                with c_a:
                    if st.button(f"{name}  {chg:+.1f}%", key=f"r_{code}",
                                 use_container_width=True):
                        st.session_state["active_ticker"] = code
                        st.rerun()
                with c_b:
                    if win:
                        st.markdown(
                            f'<span style="font-size:.72rem;color:#FF8C00;">{win}</span>',
                            unsafe_allow_html=True)

            # 胜率摘要行
            if "AI最高涨幅" in radar_df.columns:
                try:
                    gains = (radar_df["AI最高涨幅"]
                             .str.replace("%", "", regex=False)
                             .str.replace("+", "", regex=False)
                             .astype(float, errors="ignore"))
                    avg_g = round(float(gains.mean()), 1)
                    hits  = int((gains > 10).sum())
                    st.caption(f"均最高涨幅 **+{avg_g}%** | >10% **{hits}只**")
                except Exception:
                    pass

    # ──────────────────────────────────────────────────────────────
    # Tab 3：AI 自然语言选股
    # ──────────────────────────────────────────────────────────────
    with sb_t3:
        ai_query = st.text_area(
            "描述",
            placeholder=(
                "• 快速上涨且回撤不多\n"
                "• 低估值蓝筹长线稳\n"
                "• 缩量锁仓主力控盘\n"
                "• 超跌反弹弹性大\n"
                "• 外资北上资金青睐"
            ),
            height=120, label_visibility="collapsed",
        )
        ai_btn = st.button("🧠 AI语义扫描", type="primary",
                           use_container_width=True, key="ai_btn")

        if ai_btn and ai_query.strip():
            with st.spinner("AI 选股引擎运转中..."):
                _ai_pool = engine.get_ai_screener(ai_query.strip())
            st.session_state["ai_pool_df"]    = _ai_pool
            st.session_state["ai_pool_label"] = ai_query[:20]

            if _ai_pool is not None and not _ai_pool.empty:
                st.success(f"命中 {len(_ai_pool)} 只 → 见主界面「AI选股池」")
            else:
                st.warning("未找到匹配股票，换个描述试试")

        with st.expander("💡 支持的语义"):
            st.markdown(
                "快速上涨 · 回撤小 · 长线稳 · 低估值 · 缩量锁仓\n\n"
                "超跌反弹 · 大盘龙头 · 放量上涨 · 涨停打板\n\n"
                "外资北上 · 科技AI · 新能源 · 医药 · 军工\n\n"
                "低价弹性 · 高换手活跃 · 小盘黑马"
            )


# ════════════════════════════════════════════════════════════════════
#  主内容区
# ════════════════════════════════════════════════════════════════════

# ── 品牌水印头部 ─────────────────────────────────────────────────────
st.markdown('<p class="tiger-h1">🐉 龙眼 A股深度研判系统</p>', unsafe_allow_html=True)
st.markdown(
    '<div class="brand-bar">'
    '🐯 本系统由龙眼多Agent架构驱动，基于虎之眼 (Eye of Tiger) 金融内核 · '
    '指南针CYQ筹码模型 · 多智能体并行研判 · 仅供学习研究，不构成投资建议'
    '</div>',
    unsafe_allow_html=True,
)

active_code = st.session_state["active_ticker"]
st.info(f"📍 当前标的：**{active_code}** — 在左侧「📊 股票研判」修改代码后点击启动审计")


# ── 执行分析 ──────────────────────────────────────────────────────────
if run_btn and active_code:
    ticker = active_code
    with st.status(f"🔍 虎之眼透视 {ticker}...", expanded=True) as _status:
        ctx = engine.get_full_context(ticker, ticker)

        reports: list = []
        if active_skills:
            with ThreadPoolExecutor(max_workers=max(len(active_skills), 1)) as exe:
                futs = {exe.submit(orchestrator.consult_skill, s, ticker, ctx): s
                        for s in active_skills}
                for fut in as_completed(futs):
                    try:    reports.append(fut.result())
                    except Exception as e:
                        reports.append(
                            f"> 🐯 本研判由龙眼系统执行，基于虎之眼金融内核\n\n"
                            f"⚠️ 专家研判出错: {e}"
                        )

        verdict = orchestrator.synthesize_cio(ticker, reports, ctx)
        _status.update(label="✅ 研判报告合成完毕", state="complete", expanded=False)

    st.session_state["analysis_result"] = {
        "ticker":    ticker,
        "ctx":       ctx,
        "reports":   reports,
        "verdict":   verdict,
        "tab_names": [os.path.basename(s)[3:-3] for s in active_skills],
        "ts":        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ── 渲染分析结果 ──────────────────────────────────────────────────────
res = st.session_state.get("analysis_result")
if res:
    ticker    = res["ticker"]
    ctx       = res["ctx"]
    reports   = res["reports"]
    verdict   = res["verdict"]
    tab_names = res["tab_names"]
    ts        = res.get("ts", "")

    pi   = ctx.get("price_info",       {})
    chip = ctx.get("chip_analysis",    {})
    atr  = ctx.get("atr_analysis",     {})
    turn = ctx.get("turnover_analysis",{})

    cp       = pi.get("current_price", "N/A")
    chg      = _f(pi.get("change_pct", 0))
    profit_r = ctx.get("profit_ratio") or chip.get("profit_ratio", "暂无数据")
    macro_r  = ctx.get("macro_rate", "N/A")
    company  = ctx.get("company_name") or ticker
    drive    = _extract_drive(orchestrator, verdict)
    score    = orchestrator.extract_score(verdict)  if hasattr(orchestrator, "extract_score")  else "—"
    signal   = orchestrator.extract_signal(verdict) if hasattr(orchestrator, "extract_signal") else "—"

    # ── 顶部指标卡 ────────────────────────────────────────────────
    st.divider()
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("公司",     company)
    m2.metric("价格",     f"¥{cp}", _pct(chg))
    m3.metric("龙眼评分", score)
    m4.metric("获利盘",   profit_r)
    m5.metric("中债10Y",  f"{macro_r}%")
    m6.metric("驱动类型", drive)

    # ── 获利盘进度条 ──────────────────────────────────────────────
    try:
        pct_v = float(profit_r.replace("%", ""))
        bar_color = "#FF4444" if pct_v > 70 else "#FF8C00" if pct_v > 40 else "#00CC66"
        st.markdown(
            f'<div class="chip-bar-outer">'
            f'<div class="chip-bar-inner" '
            f'style="width:{int(pct_v)}%;background:{bar_color};"></div></div>'
            f'<small style="color:{bar_color};">获利盘 {profit_r}</small>',
            unsafe_allow_html=True,
        )
    except Exception:
        pass

    # ── CYQ 仪表盘 ────────────────────────────────────────────────
    if any([chip.get("vwap_60"), atr.get("atr_pct"), turn.get("avg_turnover_5d")]):
        st.caption("💎 虎之眼 · 指南针CYQ筹码仪表盘")
        ca, cb, cc, cd = st.columns(4)
        ca.metric("主力成本(60日VWAP)", f"¥{chip.get('vwap_60','N/A')}",
                  chip.get("chip_lock_signal",""))
        cb.metric("筹码密集度",
                  ctx.get("chip_density", chip.get("chip_density","N/A")))
        cc.metric("ATR波动率", atr.get("atr_pct","N/A"),
                  atr.get("atr_percentile",""))
        cd.metric("换手承接", turn.get("avg_turnover_5d","N/A"),
                  (turn.get("turnover_signal") or "")[:22])

    # ── CIO 裁决 ──────────────────────────────────────────────────
    st.divider()
    st.subheader("👑 CIO 综合裁决")
    st.markdown(
        f'<div class="verdict-box">'
        f'<small style="color:#666;">🐯 本研判由龙眼系统执行，基于虎之眼(Eye of Tiger)金融内核 · {ts}</small>'
        f'<hr style="border-color:#222;margin:8px 0;">'
        f'{verdict}'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── 分项专家 Tabs ─────────────────────────────────────────────
    st.divider()
    if tab_names and reports:
        for tab, report in zip(st.tabs(tab_names), reports):
            with tab:
                # 每个 Tab 也注入品牌水印
                st.markdown(
                    '<div class="brand-bar">'
                    '🐯 本研判由龙眼系统执行，基于虎之眼 (Eye of Tiger) 金融内核'
                    '</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(report)


# ── AI 选股池展示（独立区块，始终可见）────────────────────────────────
ai_df = st.session_state.get("ai_pool_df")
if ai_df is not None and not ai_df.empty:
    st.divider()
    st.subheader(f"🤖 AI 选股池 — {st.session_state.get('ai_pool_label','')}")
    st.markdown(
        '<div class="brand-bar">'
        '🐯 以下个股由虎之眼语义引擎筛选，追踪"入选日→当前最高涨幅"作为AI正确率参考'
        '</div>',
        unsafe_allow_html=True,
    )

    # 汇总胜率统计
    if "AI最高涨幅" in ai_df.columns:
        try:
            gains = (ai_df["AI最高涨幅"]
                     .str.replace("%", "", regex=False)
                     .str.replace("+", "", regex=False)
                     .astype(float, errors="ignore"))
            avg_g  = round(float(gains.mean()), 1)
            hits10 = int((gains > 10).sum())
            hits20 = int((gains > 20).sum())
            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("本批平均最高涨幅", f"+{avg_g}%")
            sc2.metric("命中>10%", f"{hits10}只")
            sc3.metric("命中>20% 🏆", f"{hits20}只")
        except Exception:
            pass

    # 逐行渲染选股卡片
    for _, row in ai_df.iterrows():
        code   = str(row.get("代码", ""))
        name   = str(row.get("名称", code))
        chg    = _f(row.get("涨跌幅", 0))
        price  = row.get("最新价",  "N/A")
        pe     = row.get("PE",       "N/A")
        reason = row.get("虎眼推荐理由", "虎之眼筛选")
        stag   = row.get("策略标签",  "")
        win    = row.get("AI胜率标签", "")
        entry  = row.get("AI入选日",   "—")
        gain   = row.get("AI最高涨幅", "—")

        chg_color = "#FF4444" if chg >= 0 else "#00CC66"
        badge_html = _gain_badge(win) if win else ""

        col_card, col_btn = st.columns([5, 1])
        with col_card:
            st.markdown(
                f'<div class="pool-card">'
                f'<span style="font-size:1rem;font-weight:700;color:#fff;">{name}</span>'
                f'<span style="color:#888;font-size:.8rem;margin-left:8px;">{code}</span>'
                f'<span style="color:{chg_color};font-weight:bold;margin-left:12px;">{chg:+.2f}%</span>'
                f'<span style="color:#888;font-size:.8rem;margin-left:10px;">¥{price}</span>'
                f'{"  PE "+str(pe) if pe != "N/A" else ""}'
                f'<br>'
                f'<span style="color:#FF8C00;font-size:.78rem;">🐯 {reason}</span>'
                f'{"  <span style=color:#666;font-size:.74rem;>["+stag+"]</span>" if stag else ""}'
                f'<br>'
                f'<small style="color:#555;">AI入选: {entry}</small>'
                f'<small style="color:#555;margin-left:10px;">入选后最高涨幅: {gain}</small>'
                f'{"  "+badge_html if badge_html else ""}'
                f'</div>',
                unsafe_allow_html=True,
            )
        with col_btn:
            if st.button("研判 →", key=f"pool_{code}", use_container_width=True):
                st.session_state["active_ticker"] = code
                st.rerun()


# ── 落地页（无任何结果时）────────────────────────────────────────────
elif not res and (ai_df is None or ai_df.empty):
    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.info("**📊 股票研判**\n\n左侧输入代码，选专家团队，点击启动")
    c2.info("**🔭 选股雷达**\n\n预设策略扫描全市场，点击个股直接研判")
    c3.info("**🤖 AI语义选股**\n\n自然语言描述想要的股票，AI自动过滤")

    st.markdown("---")
    st.markdown(
        '<div class="brand-bar" style="text-align:center;">'
        '🐉 龙眼研判系统 v3.0 · 虎之眼 (Eye of Tiger) 金融内核 · '
        '指南针CYQ筹码模型 · 多智能体并行研判 · 仅供学习研究，不构成投资建议'
        '</div>',
        unsafe_allow_html=True,
    )
