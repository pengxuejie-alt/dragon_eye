import streamlit as st
import glob, os, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.engine import AShareDataEngine
from core.agents import LongEyeOrchestrator

st.set_page_config(page_title="🐉 龙眼 Pro — 虎之眼内核", layout="wide")

# 初始化 Session
if "active_ticker" not in st.session_state: st.session_state["active_ticker"] = "600519"
if "ai_results" not in st.session_state: st.session_state["ai_results"] = None

@st.cache_resource
def load_system():
    return AShareDataEngine(), LongEyeOrchestrator(api_key=st.secrets["GEMINI_KEY"])

engine, orchestrator = load_system()

# ── 侧边栏：1, 2, 3 固定架构 ──
with st.sidebar:
    st.markdown('<p style="font-size:1.5rem;font-weight:900;color:#CC0000;margin:0;">🐉 龙眼研判</p>', unsafe_allow_html=True)
    st.markdown('<p style="color:#FF8C00;font-style:italic;font-size:0.8rem;">虎之眼 Eye of Tiger 金融内核</p>', unsafe_allow_html=True)
    st.divider()

    sb_tabs = st.tabs(["📊 股票研判", "🔭 选股雷达", "🤖 自然语言选股"])

    with sb_tabs[0]:
        t_input = st.text_input("代码", value=st.session_state["active_ticker"])
        st.session_state["active_ticker"] = t_input
        skill_paths = sorted(glob.glob("skills/0[1-6]*.md"))
        active_skills = [s for s in skill_paths if st.checkbox(os.path.basename(s)[3:-3], value=True, key=f"sk_{s}")]
        run_main = st.button("🚀 启动全维度审计", type="primary", use_container_width=True)

    with sb_tabs[1]:
        strat = st.selectbox("模式", ["涨停最强", "虎之眼价值"])
        if st.button("🔭 执行扫描", use_container_width=True):
            st.session_state["ai_results"] = engine.get_strategy_pool(strat)

    with sb_tabs[2]:
        ai_q = st.text_area("小白选股描述", placeholder="如：快速上涨而回撤不多")
        if st.button("🧠 AI 语义扫描", use_container_width=True):
            st.session_state["ai_results"] = engine.get_ai_screener(ai_q)

# ── 主界面：展示逻辑 ──
st.markdown('<h1 style="color:#CC0000;">🐉 龙眼 A股深度研判系统</h1>', unsafe_allow_html=True)

# 展示选股池 (AI 胜率追踪)
if st.session_state["ai_results"] is not None:
    st.subheader("🎯 推荐标的 (历史胜率追踪)")
    for _, row in st.session_state["ai_results"].iterrows():
        c1, c2 = st.columns([5, 1])
        with c1:
            st.markdown(f"""
            <div style="background:#111;padding:12px;border-radius:8px;border-left:4px solid #CC0000;margin-bottom:8px;">
                <b>{row['名称']} ({row['代码']})</b> <span style="color:#FFD700;margin-left:15px;">{row['AI胜率标签']} | 最高涨幅: {row['最高涨幅']}</span>
                <p style="color:#888;font-size:0.8rem;margin:5px 0;">理由: {row['理由']}</p>
                <small style="color:#444;">入选日期: {row['AI入选日']}</small>
            </div>""", unsafe_allow_html=True)
        with c2:
            if st.button("研判", key=f"p_{row['代码']}"):
                st.session_state["active_ticker"] = row['代码']
                st.rerun()

# 启动深度研判报告
if run_main:
    target = st.session_state["active_ticker"]
    with st.status(f"🔍 虎之眼透视 {target}...", expanded=True) as status:
        ctx = engine.get_full_context(target, target)
        if ctx["price_info"]["current_price"] == "N/A":
            st.error("⚠️ 股价读取超时，云端 IP 受限。请确认代码正确或重试。")
            st.stop()
        
        reports = []
        with ThreadPoolExecutor(max_workers=len(active_skills)) as exe:
            futs = {exe.submit(orchestrator.consult_skill, s, target, ctx): s for s in active_skills}
            for f in as_completed(futs): reports.append(f.result())
        
        verdict = orchestrator.synthesize_cio(target, reports, ctx)
        status.update(label="研判报告合成完毕 ✅", state="complete")

    # 指标展示
    p = ctx['price_info']
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("标的", ctx.get('company_name'))
    c2.metric("价格", f"¥{p['current_price']}", f"{p['change_pct']}%")
    c3.metric("获利盘 (CYQ)", ctx.get('profit_ratio', '暂无数据'))
    c4.metric("中债 10Y", f"{ctx.get('macro_rate')}%")

    st.subheader("👑 CIO 综合裁决")
    st.markdown(f'<div style="background:#0d0d0d;color:#FFD700;padding:20px;border-left:5px solid #CC0000;">{verdict}</div>', unsafe_allow_html=True)