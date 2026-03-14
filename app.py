"""
龙眼 A股深度研判系统 v2.0
虎之眼 (Eye of Tiger) 金融内核
===================================
新增：
1. AI 语义化选股（自然语言 → pandas 过滤）
2. 选股信心模块（首次入选日 + AI最高涨幅 = 命中率展示）
3. 指南针 CYQ 获利盘仪表盘
4. ATR波动率 + 换手率承接 显示
5. 全报告品牌声明强制注入
"""

import streamlit as st
import glob
import os
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.engine import AShareDataEngine
from core.agents import LongEyeOrchestrator

# ─── 页面配置 ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="🐉 龙眼 Pro — 虎之眼内核",
    page_icon="🐉",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .tiger-header { 
      background: linear-gradient(135deg, #8B0000, #CC0000, #FF8C00);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      font-size: 2rem; font-weight: 900; letter-spacing: 2px;
  }
  .verdict-box {
      background: #0d0d0d; border-left: 5px solid #CC0000;
      border-radius: 8px; padding: 1.4rem;
      color: #FFD700; font-size: 0.95rem; line-height: 1.7;
  }
  .chip-bar-outer {
      background: #222; border-radius: 6px; height: 18px;
      width: 100%; overflow: hidden; margin-top: 4px;
  }
  .chip-bar-inner {
      background: linear-gradient(90deg, #CC0000, #FF8C00);
      height: 100%; border-radius: 6px; transition: width 0.5s;
  }
  .win-badge { 
      display: inline-block; padding: 2px 10px;
      border-radius: 12px; font-size: 0.78rem; font-weight: bold;
      background: #1a1a2e; border: 1px solid #444;
  }
  .brand-tag {
      background: #1a0000; color: #FF8C00;
      border: 1px solid #CC0000; border-radius: 4px;
      padding: 3px 10px; font-size: 0.75rem; font-style: italic;
  }
</style>
""", unsafe_allow_html=True)

# ─── 初始化 ───────────────────────────────────────────────────────────
if "active_ticker" not in st.session_state:
    st.session_state["active_ticker"] = "600519"
if "screener_df" not in st.session_state:
    st.session_state["screener_df"] = None

@st.cache_resource
def init_system():
    return AShareDataEngine(), LongEyeOrchestrator(api_key=st.secrets["GEMINI_KEY"])

engine, orchestrator = init_system()

# ─── 侧边栏 ───────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<p class="tiger-header">🐉 龙眼选股</p>', unsafe_allow_html=True)
    st.markdown('<span class="brand-tag">虎之眼 Eye of Tiger 内核</span>', unsafe_allow_html=True)
    st.divider()

    # ── AI 语义选股 ──────────────────────────────────────────────────
    st.subheader("🤖 AI 语义选股")
    ai_query = st.text_input(
        "用自然语言描述你想要的股票",
        placeholder="快速上涨且回撤不多 / 低估值蓝筹 / 缩量锁仓...",
        help="支持：快速上涨回撤小、低估值蓝筹、高换手强势、外资偏好、小盘黑马、缩量锁仓、涨停打板"
    )

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        strat = st.selectbox("预设策略", ["涨停最强", "虎之眼价值", "全市场监控"], label_visibility="collapsed")
    with col_s2:
        btn_preset = st.button("🔭 预设扫描", use_container_width=True)

    btn_ai = st.button("🧠 AI语义扫描", use_container_width=True, type="primary")

    if btn_ai and ai_query:
        with st.spinner("AI 选股引擎运转中..."):
            st.session_state["screener_df"] = engine.get_ai_screener(ai_query)
            st.session_state["screener_label"] = f"AI语义: {ai_query[:20]}"
    elif btn_preset:
        with st.spinner("虎之眼雷达扫描中..."):
            st.session_state["screener_df"] = engine.get_strategy_pool(strat)
            st.session_state["screener_label"] = strat

    # ── 选股池展示（信心模块）────────────────────────────────────────
    pool_df = st.session_state.get("screener_df")
    if pool_df is not None and not pool_df.empty:
        label = st.session_state.get("screener_label", "选股结果")
        st.markdown(f"**📋 {label}**")

        for _, row in pool_df.head(12).iterrows():
            code  = str(row.get("代码", ""))
            name  = str(row.get("名称", code))[:6]
            chg   = row.get("涨跌幅", 0)
            win   = row.get("AI胜率标签", "")
            entry = row.get("AI入选日", "—")
            gain  = row.get("AI最高涨幅", "—")
            strat_tag = row.get("策略标签", "")

            chg_color = "#FF4444" if float(chg or 0) > 0 else "#00CC66"

            col_a, col_b = st.columns([3, 2])
            with col_a:
                if st.button(
                    f"{name} {chg:+.1f}%",
                    key=f"sel_{code}_{name}",
                    use_container_width=True,
                ):
                    st.session_state["active_ticker"] = code
                    st.rerun()
            with col_b:
                st.markdown(
                    f'<span class="win-badge" title="入选:{entry} | 最高:{gain}">{win}</span>',
                    unsafe_allow_html=True
                )

        # 胜率统计
        if "AI最高涨幅" in pool_df.columns:
            gains = pool_df["AI最高涨幅"].str.replace("%", "").str.replace("+", "").astype(float, errors="ignore")
            if hasattr(gains, "mean"):
                try:
                    avg_gain = round(gains.mean(), 1)
                    win_cnt  = (gains > 10).sum()
                    st.caption(f"📊 本批平均最高涨幅 **+{avg_gain}%** | 命中>10%: **{win_cnt}只**")
                except Exception:
                    pass

    st.divider()

    # ── 专家团配置 ────────────────────────────────────────────────────
    st.subheader("🧠 专家审计团队")
    skill_paths = sorted(glob.glob("skills/0[1-6]*.md"))
    active_skills = [
        s for s in skill_paths
        if st.checkbox(f"✅ {os.path.basename(s)[3:-3]}", value=True)
    ]

# ─── 主界面 ───────────────────────────────────────────────────────────
st.markdown('<h1 class="tiger-header">🐉 龙眼 A股深度研判系统 v2.0</h1>', unsafe_allow_html=True)
st.markdown(
    '<span class="brand-tag">基于虎之眼 (Eye of Tiger) 金融内核 · 指南针CYQ筹码模型 · 多智能体并行研判</span>',
    unsafe_allow_html=True
)

ticker_input = st.text_input(
    "📍 分析标的代码",
    value=st.session_state["active_ticker"],
    placeholder="输入6位股票代码，如 600519",
)

run_btn = st.button("🚀 启动全维度虎眼审计", type="primary", use_container_width=False)

if run_btn and ticker_input:
    import re
    code_match = re.search(r"\d{6}", ticker_input)
    code = code_match.group(0) if code_match else ticker_input.strip()

    header_ph = st.empty()

    def render_header(status: str, score: str = "—", signal: str = "", drive: str = ""):
        with header_ph.container():
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("标的", code)
            c2.metric("龙眼评分", score)
            c3.metric("评级信号", signal or "研判中")
            c4.metric("驱动类型", drive or "研判中")
            c5.metric("AI状态", status)

    render_header("数据接入中...")

    with st.status(f"🔍 虎之眼透视 {code} ...", expanded=True) as status_box:

        # ── 数据采集 ──────────────────────────────────────────────
        st.write("📡 三重备份引擎接入行情数据...")
        ctx = engine.get_full_context(code, code)

        company  = ctx.get("company_name", code)
        price    = ctx.get("price_info", {}).get("current_price", "N/A")
        change   = ctx.get("price_info", {}).get("change_pct", 0)
        industry = ctx.get("industry", "N/A")
        mktcap   = ctx.get("market_cap", "N/A")
        macro_r  = ctx.get("macro_rate", "N/A")
        profit_r = ctx.get("profit_ratio", "N/A")
        chip_sig = ctx.get("chip_analysis", {}).get("chip_lock_signal", "N/A")
        atr_lab  = ctx.get("atr_analysis", {}).get("volatility_label", "N/A")
        turn_sig = ctx.get("turnover_analysis", {}).get("turnover_signal", "N/A")

        st.write(f"✅ 行情就绪 | ¥{price} ({change:+.2f}%) | {industry} | {mktcap}")
        st.write(f"💎 CYQ筹码: 获利盘 **{profit_r}** | {chip_sig}")
        st.write(f"⚡ ATR: {atr_lab} | 换手: {turn_sig[:20]}...")

        render_header("专家并行研判中...", score="计算中")

        # ── 并行专家研判 ──────────────────────────────────────────
        st.write(f"🧠 {len(active_skills)} 位专家并行启动...")
        tab_names_raw = [os.path.basename(s)[3:-3] for s in active_skills]
        reports_map = {}

        with ThreadPoolExecutor(max_workers=max(len(active_skills), 1)) as exe:
            futures = {
                exe.submit(orchestrator.consult_skill, s, code, ctx): s
                for s in active_skills
            }
            for f in as_completed(futures):
                sf = futures[f]
                label = os.path.basename(sf)[3:-3]
                try:
                    reports_map[sf] = f.result()
                    st.write(f"  ✅ {label} 完成")
                except Exception as e:
                    reports_map[sf] = f"> 🐉 本研判由龙眼系统执行，基于虎之眼金融内核\n\n⚠️ 研判出错: {e}"
                    st.write(f"  ❌ {label} 错误")

        ordered_reports = [reports_map.get(s, "") for s in active_skills]

        # ── CIO 裁决 ──────────────────────────────────────────────
        st.write("👑 CIO 融合虎之眼内核生成最终裁决...")
        verdict = orchestrator.synthesize_cio(code, ordered_reports, ctx)

        score_val = orchestrator.extract_score(verdict)
        signal_val = orchestrator.extract_signal(verdict)
        drive_val = orchestrator.extract_drive_type(verdict)

        render_header("研判完成 ✅", score=score_val, signal=signal_val, drive=drive_val)
        status_box.update(label="✅ 虎之眼研判报告生成成功", state="complete", expanded=False)

    # ─── 结果渲染 ────────────────────────────────────────────────────
    st.divider()

    # 顶部指标行
    mc1, mc2, mc3, mc4, mc5, mc6 = st.columns(6)
    mc1.metric("🏢 公司", company)
    mc2.metric("💰 现价", f"¥{price}", f"{change:+.2f}%")
    mc3.metric("🏭 行业", industry)
    mc4.metric("📊 市值", mktcap)
    mc5.metric("🏦 中债10Y", f"{macro_r}%")
    mc6.metric("💎 获利盘", profit_r)

    # 指南针 CYQ 可视化仪表盘
    st.divider()
    st.subheader("💎 指南针 CYQ 筹码仪表盘")
    chip = ctx.get("chip_analysis", {})
    atr  = ctx.get("atr_analysis", {})
    turn = ctx.get("turnover_analysis", {})

    cq1, cq2, cq3, cq4 = st.columns(4)
    with cq1:
        try:
            pct_val = float(profit_r.replace("%", ""))
        except Exception:
            pct_val = 0
        st.markdown(f"**获利盘比例**")
        bar_w = int(pct_val)
        color = "#FF4444" if pct_val > 70 else "#FF8C00" if pct_val > 40 else "#00CC66"
        st.markdown(
            f'<div class="chip-bar-outer"><div class="chip-bar-inner" '
            f'style="width:{bar_w}%; background:{color};"></div></div>'
            f'<small style="color:{color}"><b>{profit_r}</b></small>',
            unsafe_allow_html=True
        )
    with cq2:
        st.metric("主力成本(60日VWAP)", f"¥{chip.get('vwap_60', 'N/A')}")
        st.caption(chip.get("chip_lock_signal", ""))
    with cq3:
        st.metric("ATR波动率", atr.get("atr_pct", "N/A"))
        st.caption(atr.get("volatility_label", ""))
    with cq4:
        st.metric("换手承接", turn.get("avg_turnover_5d", "N/A"))
        st.caption(turn.get("turnover_signal", "")[:30] + "..." if len(turn.get("turnover_signal", "")) > 30 else turn.get("turnover_signal", ""))

    # CIO 裁决
    st.divider()
    st.subheader("👑 CIO 综合裁决 — 虎之眼内核")
    st.markdown(f'<div class="verdict-box">{verdict}</div>', unsafe_allow_html=True)

    # PDF 导出
    st.divider()
    col_pdf, col_info = st.columns([1, 3])
    with col_pdf:
        if os.path.exists("MSYH.TTC"):
            try:
                pdf_bytes = orchestrator.create_pdf(
                    code, company, verdict, ordered_reports, tab_names_raw, ctx
                )
                st.download_button(
                    "📥 下载 PDF 研判报告",
                    data=bytes(pdf_bytes),
                    file_name=f"LongEye_{code}_{datetime.date.today()}.pdf",
                    use_container_width=True,
                )
            except Exception as e:
                st.warning(f"PDF渲染失败: {e}")
        else:
            st.info("放置 MSYH.TTC 到根目录以启用 PDF 导出")
    with col_info:
        st.caption(
            f"📍 {code} · {company} · {industry}  |  "
            f"🕐 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  |  "
            f"🐉 虎之眼(Eye of Tiger)金融内核"
        )

    # 分项专家 Tabs
    if active_skills:
        tabs = st.tabs([f"📋 {n}" for n in tab_names_raw])
        for i, tab in enumerate(tabs):
            with tab:
                if i < len(ordered_reports):
                    st.markdown(ordered_reports[i])

elif not run_btn:
    # 落地页
    st.divider()
    st.markdown("### 🐉 龙眼 v2.0 核心升级")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.success("**🧠 AI语义选股**\n\n自然语言描述你想要的股票，如「快速上涨且回撤不多」")
    with col2:
        st.info("**💎 CYQ筹码仪表盘**\n\n指南针获利盘可视化 + 主力锁仓信号 + VWAP成本线")
    with col3:
        st.warning("**📊 AI预测命中率**\n\n记录每只股票首次入选日期 + 追踪后续最高涨幅")

    col4, col5, col6 = st.columns(3)
    with col4:
        st.info("**⚡ ATR波动率审计**\n\n判断当前波动是否处于历史低位（低波=优质信号）")
    with col5:
        st.success("**🔄 换手率承接**\n\n涨中缩量→主力锁仓 | 涨中放量→游资接力")
    with col6:
        st.error("**🛡️ 一票否决机制**\n\n质押>50% / 筹码派发 / ATR极值，强制下调评级")
