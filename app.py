import streamlit as st
import glob
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.engine import AShareDataEngine
from core.agents import LongEyeOrchestrator

st.set_page_config(
    page_title="🐉 龙眼 Pro - 选股研判一体化",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session State 初始化 ──────────────────────────────────────────────
if "active_ticker"   not in st.session_state: st.session_state["active_ticker"]   = "600519"
if "pool_df"         not in st.session_state: st.session_state["pool_df"]          = None
if "pool_label"      not in st.session_state: st.session_state["pool_label"]       = ""
if "sidebar_tab"     not in st.session_state: st.session_state["sidebar_tab"]      = "研判"
if "analysis_result" not in st.session_state: st.session_state["analysis_result"]  = None

@st.cache_resource
def init_system():
    return AShareDataEngine(), LongEyeOrchestrator(api_key=st.secrets["GEMINI_KEY"])

engine, orchestrator = init_system()

# ── 工具函数 ─────────────────────────────────────────────────────────
def safe_float(val, default=0.0):
    try:    return float(val)
    except: return default

def safe_fmt_pct(val):
    return f"{safe_float(val):+.2f}%"

def extract_drive(orchestrator, text):
    if hasattr(orchestrator, "extract_drive_type"):
        return orchestrator.extract_drive_type(text)
    for t in ["价值驱动", "博弈驱动", "政策陷阱"]:
        if t in text: return t
    return "—"

# ════════════════════════════════════════════════════════════════════
# 侧边栏
# ════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(
        '<p style="font-size:1.5rem;font-weight:900;color:#CC0000;letter-spacing:2px;margin:0;">🐉 龙眼研判</p>',
        unsafe_allow_html=True,
    )
    st.caption("虎之眼 Eye of Tiger 金融内核")
    st.divider()

    # ── 三个功能 Tab ─────────────────────────────────────────────────
    t1, t2, t3 = st.tabs(["📊 股票研判", "🔭 选股雷达", "🤖 AI选股"])

    # ────────────────────────────────────────────────
    # Tab 1：股票研判
    # ────────────────────────────────────────────────
    with t1:
        st.markdown("**输入标的代码**")
        ticker_input = st.text_input(
            "股票代码",
            value=st.session_state["active_ticker"],
            placeholder="如 600519 / 000858 / 300750",
            label_visibility="collapsed",
        )
        if ticker_input:
            st.session_state["active_ticker"] = ticker_input.strip()

        st.markdown("**专家审计团队**")
        skill_paths = sorted(glob.glob("skills/0[1-6]*.md"))
        active_skills = [
            s for s in skill_paths
            if st.checkbox(
                os.path.basename(s)[3:-3],
                value=True,
                key=f"skill_{s}",
            )
        ]

        run_btn = st.button(
            "🚀 启动全维度审计",
            type="primary",
            use_container_width=True,
            key="run_analysis",
        )

    # ────────────────────────────────────────────────
    # Tab 2：选股雷达
    # ────────────────────────────────────────────────
    with t2:
        st.markdown("**选股策略**")
        strat = st.selectbox(
            "策略",
            ["涨停最强", "虎之眼价值", "全市场监控"],
            label_visibility="collapsed",
        )
        scan_btn = st.button("🔭 扫描市场信号", use_container_width=True, key="scan_btn")

        if scan_btn:
            with st.spinner("虎之眼雷达扫描中..."):
                pool = engine.get_strategy_pool(strat)
            st.session_state["pool_df"]    = pool
            st.session_state["pool_label"] = strat

        pool_df = st.session_state["pool_df"]
        if pool_df is not None and not pool_df.empty:
            st.caption(f"📋 {st.session_state['pool_label']} — 点击直接研判")
            for _, row in pool_df.head(12).iterrows():
                code = str(row.get("代码", ""))
                name = str(row.get("名称", code))[:6]
                chg  = safe_float(row.get("涨跌幅", 0))
                win  = row.get("AI胜率标签", "")
                col_a, col_b = st.columns([3, 2])
                with col_a:
                    if st.button(
                        f"{name}  {chg:+.1f}%",
                        key=f"radar_{code}",
                        use_container_width=True,
                    ):
                        st.session_state["active_ticker"] = code
                        st.session_state["sidebar_active"] = "研判"
                        st.rerun()
                with col_b:
                    if win:
                        st.markdown(
                            f'<span style="font-size:0.75rem;color:#FF8C00;">{win}</span>',
                            unsafe_allow_html=True,
                        )

            # 胜率摘要
            if "AI最高涨幅" in pool_df.columns:
                try:
                    gains = pool_df["AI最高涨幅"].str.replace("%","").str.replace("+","").astype(float, errors="ignore")
                    avg_g = round(gains.mean(), 1)
                    hits  = int((gains > 10).sum())
                    st.caption(f"均最高涨幅 **+{avg_g}%** | >10%命中 **{hits}只**")
                except Exception:
                    pass

    # ────────────────────────────────────────────────
    # Tab 3：自然语言 AI 选股
    # ────────────────────────────────────────────────
    with t3:
        st.markdown("**用自然语言描述你想要的股票**")
        ai_query = st.text_area(
            "描述",
            placeholder=(
                "例如：\n"
                "• 快速上涨且回撤不多\n"
                "• 低估值蓝筹\n"
                "• 缩量锁仓上涨\n"
                "• 小盘黑马弹性大\n"
                "• 外资偏好北上资金"
            ),
            height=130,
            label_visibility="collapsed",
        )
        ai_btn = st.button("🧠 AI语义扫描", type="primary", use_container_width=True, key="ai_btn")

        if ai_btn and ai_query.strip():
            with st.spinner("AI 选股引擎运转中..."):
                ai_pool = engine.get_ai_screener(ai_query.strip())
            st.session_state["pool_df"]    = ai_pool
            st.session_state["pool_label"] = f"AI: {ai_query[:18]}"

            if ai_pool is not None and not ai_pool.empty:
                st.success(f"找到 {len(ai_pool)} 只候选股，已同步到「选股雷达」Tab")
                for _, row in ai_pool.head(10).iterrows():
                    code = str(row.get("代码", ""))
                    name = str(row.get("名称", code))[:6]
                    chg  = safe_float(row.get("涨跌幅", 0))
                    win  = row.get("AI胜率标签", "")
                    tag  = row.get("策略标签", "")
                    col_a, col_b = st.columns([3, 2])
                    with col_a:
                        if st.button(
                            f"{name}  {chg:+.1f}%",
                            key=f"ai_{code}",
                            use_container_width=True,
                        ):
                            st.session_state["active_ticker"] = code
                            st.rerun()
                    with col_b:
                        lbl = win or tag
                        if lbl:
                            st.markdown(
                                f'<span style="font-size:0.72rem;color:#FF8C00;">{lbl[:10]}</span>',
                                unsafe_allow_html=True,
                            )
            else:
                st.warning("未找到符合条件的股票，请换一个描述试试")

        # 支持的语义关键词提示
        with st.expander("💡 支持的语义关键词"):
            st.markdown(
                "| 描述 | 过滤逻辑 |\n"
                "|------|----------|\n"
                "| 快速上涨 + 回撤不多 | 涨幅>5% & 振幅<6% |\n"
                "| 低估值 / 蓝筹 / 价值 | PE 3-20 & 涨幅>0 |\n"
                "| 高换手 / 强势 / 活跃 | 换手率>5% & 涨幅>3% |\n"
                "| 北上 / 外资 | PE 5-30 & 价格>10 |\n"
                "| 小盘 / 黑马 / 弹性 | 涨幅>4% & 小市值 |\n"
                "| 缩量 / 锁仓 | 涨幅>2% & 换手率<2% |\n"
                "| 涨停 / 打板 | 涨幅>9.5% |\n"
            )

# ════════════════════════════════════════════════════════════════════
# 主内容区
# ════════════════════════════════════════════════════════════════════
st.markdown(
    '<h1 style="color:#CC0000;font-weight:900;">🐉 龙眼 A股深度研判系统</h1>',
    unsafe_allow_html=True,
)
st.caption("基于虎之眼 (Eye of Tiger) 金融内核 · 指南针CYQ筹码模型 · 多智能体并行研判")

# 当前标的展示条
active = st.session_state["active_ticker"]
st.info(f"📍 当前标的：**{active}** — 在左侧「股票研判」修改代码，点击「启动全维度审计」开始分析")

# ── 执行分析 ─────────────────────────────────────────────────────────
if run_btn and active:
    ticker = active
    active_skills_ref = active_skills  # 侧边栏 Tab1 中已定义

    with st.status(f"正在驱动专家团透视 {ticker}...", expanded=True) as status:
        ctx = engine.get_full_context(ticker, ticker)

        reports = []
        if active_skills_ref:
            with ThreadPoolExecutor(max_workers=max(len(active_skills_ref), 1)) as exe:
                futures = {
                    exe.submit(orchestrator.consult_skill, s, ticker, ctx): s
                    for s in active_skills_ref
                }
                for f in as_completed(futures):
                    try:
                        reports.append(f.result())
                    except Exception as e:
                        reports.append(f"⚠️ 专家研判出错: {e}")

        final_verdict = orchestrator.synthesize_cio(ticker, reports, ctx)
        status.update(label="研判报告合成完毕 ✅", state="complete")

    # ── 缓存结果 ────────────────────────────────────────────────────
    st.session_state["analysis_result"] = {
        "ticker":        ticker,
        "ctx":           ctx,
        "reports":       reports,
        "final_verdict": final_verdict,
        "tab_names":     [os.path.basename(s)[3:-3] for s in active_skills_ref],
    }

# ── 渲染结果（缓存后刷新不消失）────────────────────────────────────────
result = st.session_state.get("analysis_result")
if result:
    ticker        = result["ticker"]
    ctx           = result["ctx"]
    reports       = result["reports"]
    final_verdict = result["final_verdict"]
    tab_names     = result["tab_names"]

    price_info = ctx.get("price_info", {})
    chip_info  = ctx.get("chip_analysis", {})
    atr_info   = ctx.get("atr_analysis", {})
    turn_info  = ctx.get("turnover_analysis", {})

    current_price = price_info.get("current_price", "N/A")
    change_pct    = safe_float(price_info.get("change_pct", 0))
    profit_ratio  = ctx.get("profit_ratio") or chip_info.get("profit_ratio", "N/A")
    macro_rate    = ctx.get("macro_rate", "N/A")
    company_name  = ctx.get("company_name") or ticker
    drive_val     = extract_drive(orchestrator, final_verdict)
    score_val     = orchestrator.extract_score(final_verdict)  if hasattr(orchestrator, "extract_score")  else "—"
    signal_val    = orchestrator.extract_signal(final_verdict) if hasattr(orchestrator, "extract_signal") else "—"

    # ── 指标卡 ────────────────────────────────────────────────────
    st.divider()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("标的",     company_name)
    c2.metric("价格",     f"¥{current_price}", safe_fmt_pct(change_pct))
    c3.metric("获利盘",   profit_ratio)
    c4.metric("中债10Y",  f"{macro_rate}%")
    c5.metric("驱动类型", drive_val)

    # ── CYQ 仪表盘 ────────────────────────────────────────────────
    if chip_info.get("vwap_60") or atr_info.get("atr_pct") or turn_info.get("avg_turnover_5d"):
        st.caption("💎 虎之眼 · 指南针CYQ筹码仪表盘")
        ca, cb, cc, cd = st.columns(4)
        ca.metric("主力成本(60日VWAP)", f"¥{chip_info.get('vwap_60','N/A')}", chip_info.get("chip_lock_signal",""))
        cb.metric("筹码密集度",         ctx.get("chip_density", chip_info.get("chip_density","N/A")))
        cc.metric("ATR波动率",          atr_info.get("atr_pct","N/A"), atr_info.get("atr_percentile",""))
        turn_sig = (turn_info.get("turnover_signal") or "")[:22]
        cd.metric("换手承接",           turn_info.get("avg_turnover_5d","N/A"), turn_sig)

    # ── CIO 裁决 ──────────────────────────────────────────────────
    st.divider()
    st.subheader("👑 CIO 综合裁决 (虎之眼内核)")
    st.markdown(
        f'<div style="background:#0d0d0d;padding:20px;border-left:5px solid #CC0000;'
        f'color:#FFD700;border-radius:8px;line-height:1.7;">{final_verdict}</div>',
        unsafe_allow_html=True,
    )

    # ── 分项专家 Tabs ─────────────────────────────────────────────
    st.divider()
    if tab_names and reports:
        for tab, report in zip(st.tabs(tab_names), reports):
            with tab:
                st.markdown(report)

elif not result:
    # 落地页
    st.divider()
    col1, col2, col3 = st.columns(3)
    col1.info("**📊 股票研判**\n\n左侧输入股票代码，选择专家团队，点击启动审计")
    col2.info("**🔭 选股雷达**\n\n预设策略扫描全市场，点击个股直接跳转研判")
    col3.info("**🤖 自然语言AI选股**\n\n用中文描述你想要的股票，AI自动过滤匹配")
