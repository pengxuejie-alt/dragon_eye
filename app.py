import streamlit as st
import glob
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.engine import AShareDataEngine
from core.agents import LongEyeOrchestrator

st.set_page_config(page_title="🐉 龙眼 Pro - 选股研判一体化", layout="wide")

if "active_ticker" not in st.session_state:
    st.session_state["active_ticker"] = "600519"

@st.cache_resource
def init_system():
    return AShareDataEngine(), LongEyeOrchestrator(api_key=st.secrets["GEMINI_KEY"])

engine, orchestrator = init_system()

# ── 安全取值工具 ──────────────────────────────────────────────────────
def safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default

def safe_fmt_pct(val):
    return f"{safe_float(val):+.2f}%"

# ---------- 侧边栏 ----------
with st.sidebar:
    st.markdown("### 🏹 异动选股雷达")
    strat = st.selectbox("审计策略", ["涨停最强", "虎之眼价值", "全市场监控"])

    if st.button("🔭 扫描市场信号"):
        pool = engine.get_strategy_pool(strat)
        if pool is not None and not pool.empty:
            for _, row in pool.head(10).iterrows():
                chg = safe_float(row.get("涨跌幅", 0))
                lbl = f"🔎 {row.get('名称', row.get('代码',''))} ({chg:+.1f}%)"
                if st.button(lbl, key=f"sel_{row.get('代码','')}"):
                    st.session_state["active_ticker"] = str(row.get("代码", ""))
                    st.rerun()

    st.divider()
    st.subheader("🧠 专家审计团队")
    skill_paths = sorted(glob.glob("skills/0[1-6]*.md"))
    active_skills = [s for s in skill_paths if st.checkbox(f"✅ {os.path.basename(s)[3:-3]}", value=True)]

# ---------- 主界面 ----------
st.markdown('<h1 style="color: #CC0000;">🐉 龙眼 A股深度研判系统</h1>', unsafe_allow_html=True)
st.caption("基于虎之眼 (Eye of Tiger) 金融内核 · 指南针CYQ筹码模型 · 多智能体并行研判")

ticker = st.text_input("📍 分析标的代码", value=st.session_state["active_ticker"])

if st.button("🚀 启动全维度审计", type="primary"):
    with st.status(f"正在驱动专家团透视 {ticker}...", expanded=True) as status:
        ctx = engine.get_full_context(ticker, ticker)

        reports = []
        if active_skills:
            with ThreadPoolExecutor(max_workers=max(len(active_skills), 1)) as exe:
                futures = {exe.submit(orchestrator.consult_skill, s, ticker, ctx): s for s in active_skills}
                for f in as_completed(futures):
                    try:
                        reports.append(f.result())
                    except Exception as e:
                        reports.append(f"⚠️ 专家研判出错: {e}")

        final_verdict = orchestrator.synthesize_cio(ticker, reports, ctx)
        status.update(label="研判报告合成完毕 ✅", state="complete")

    # ── 安全提取字段 ──────────────────────────────────────────────
    price_info = ctx.get("price_info", {})
    chip_info  = ctx.get("chip_analysis", {})
    atr_info   = ctx.get("atr_analysis", {})
    turn_info  = ctx.get("turnover_analysis", {})

    current_price = price_info.get("current_price", "N/A")
    change_pct    = safe_float(price_info.get("change_pct", 0))
    profit_ratio  = ctx.get("profit_ratio") or chip_info.get("profit_ratio", "N/A")
    macro_rate    = ctx.get("macro_rate", "N/A")
    company_name  = ctx.get("company_name") or ticker

    # 驱动类型：兼容新旧 agents.py
    drive_val = "—"
    if hasattr(orchestrator, "extract_drive_type"):
        drive_val = orchestrator.extract_drive_type(final_verdict)
    else:
        for t in ["价值驱动", "博弈驱动", "政策陷阱"]:
            if t in final_verdict:
                drive_val = t
                break

    score_val  = orchestrator.extract_score(final_verdict)  if hasattr(orchestrator, "extract_score")  else "—"
    signal_val = orchestrator.extract_signal(final_verdict) if hasattr(orchestrator, "extract_signal") else "—"

    # ── 顶部指标卡 ────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("标的",     company_name)
    c2.metric("价格",     f"¥{current_price}", safe_fmt_pct(change_pct))
    c3.metric("获利盘",   profit_ratio)
    c4.metric("中债10Y",  f"{macro_rate}%")
    c5.metric("驱动类型", drive_val)

    # ── CYQ 仪表盘（有数据才渲染）────────────────────────────────
    if chip_info.get("vwap_60") or atr_info.get("atr_pct") or turn_info.get("avg_turnover_5d"):
        st.divider()
        st.caption("💎 虎之眼 · 指南针CYQ筹码仪表盘")
        ca, cb, cc, cd = st.columns(4)
        ca.metric("主力成本(60日VWAP)", f"¥{chip_info.get('vwap_60','N/A')}", chip_info.get("chip_lock_signal",""))
        cb.metric("筹码密集度", ctx.get("chip_density", chip_info.get("chip_density","N/A")))
        cc.metric("ATR波动率", atr_info.get("atr_pct","N/A"), atr_info.get("atr_percentile",""))
        turn_sig = (turn_info.get("turnover_signal") or "")[:22]
        cd.metric("换手承接", turn_info.get("avg_turnover_5d","N/A"), turn_sig)

    # ── CIO 裁决 ──────────────────────────────────────────────────
    st.divider()
    st.subheader("👑 CIO 综合裁决 (虎之眼内核)")
    st.markdown(
        f'<div style="background:#0d0d0d;padding:20px;border-left:5px solid #CC0000;'
        f'color:#FFD700;border-radius:8px;line-height:1.7;">{final_verdict}</div>',
        unsafe_allow_html=True
    )

    # ── 分项专家 Tabs ──────────────────────────────────────────────
    st.divider()
    tab_names = [os.path.basename(s)[3:-3] for s in active_skills]
    if tab_names and reports:
        for tab, report in zip(st.tabs(tab_names), reports):
            with tab:
                st.markdown(report)
