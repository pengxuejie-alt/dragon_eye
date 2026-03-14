"""
龙眼 (LongEye) A股深度研判系统 v4.0
内核：虎之眼 (Eye of Tiger) 金融审计内核
[修复] 云端股价读取 Bug：采用腾讯/新浪极速引擎
"""
import streamlit as st
import glob
import os
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.engine import AShareDataEngine
from core.agents import LongEyeOrchestrator

# ── 1. 页面配置与品牌样式 ──────────────────────────────────────────────────
st.set_page_config(
    page_title="🐉 龙眼 Pro — 虎之眼内核",
    page_icon="🐉",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    :root { --tiger-red: #CC0000; --tiger-gold: #FFD700; }
    .main-header { font-size: 2.2rem; font-weight: 900; color: var(--tiger-red); margin-bottom: 5px; }
    .brand-tag { font-size: 0.85rem; color: #FF8C00; font-style: italic; margin-bottom: 20px; }
    .verdict-box { background: #0d0d0d; border-left: 5px solid var(--tiger-red); padding: 1.5rem; border-radius: 8px; color: var(--tiger-gold); }
    .pool-card { background: #111; border: 1px solid #222; border-radius: 10px; padding: 15px; margin-bottom: 10px; border-left: 4px solid #444; }
</style>
""", unsafe_allow_html=True)

# ── 2. 系统初始化 ──────────────────────────────────────────────────────────
if "active_ticker" not in st.session_state:
    st.session_state["active_ticker"] = "600519"
if "ai_results" not in st.session_state:
    st.session_state["ai_results"] = None

@st.cache_resource
def load_system():
    # 注入虎之眼品牌要求
    return AShareDataEngine(), LongEyeOrchestrator(api_key=st.secrets["GEMINI_KEY"])

engine, orchestrator = load_system()

# ── 3. 侧边栏结构（严格遵循 1, 2, 3 架构） ──────────────────────────────────────
with st.sidebar:
    st.markdown('<p style="font-size:1.5rem; font-weight:900; color:#CC0000; margin:0;">🐉 龙眼研判</p>', unsafe_allow_html=True)
    st.markdown('<p class="brand-tag">虎之眼 Eye of Tiger 金融内核</p>', unsafe_allow_html=True)
    st.divider()
    
    # 严格按照用户要求的三个模块
    menu = st.tabs(["📊 股票研判", "🔭 选股雷达", "🤖 自然语言选股"])
    
    # 模块 1：股票研判
    with menu[0]:
        st.caption("输入代码并选择专家团进行审计")
        ticker_input = st.text_input("股票代码", value=st.session_state["active_ticker"], key="main_ticker")
        if ticker_input:
            st.session_state["active_ticker"] = ticker_input
            
        skill_paths = sorted(glob.glob("skills/0[1-6]*.md"))
        active_skills = [s for s in skill_paths if st.checkbox(os.path.basename(s)[3:-3], value=True, key=f"sk_{s}")]
        
        run_main = st.button("🚀 启动深度审计", type="primary", use_container_width=True)

    # 模块 2：选股雷达
    with menu[1]:
        strat = st.selectbox("雷达模式", ["涨停最强", "虎之眼价值", "游资博弈榜"])
        if st.button("🔭 扫描异动", use_container_width=True):
            with st.spinner("正在检索数据..."):
                pool_df = engine.get_strategy_pool(strat)
                st.session_state["ai_results"] = pool_df

    # 模块 3：自然语言选股
    with menu[2]:
        ai_query = st.text_area("小白口语选股", placeholder="如：快速上涨且回撤不多...", height=100)
        if st.button("🧠 AI 语义扫描", use_container_width=True):
            if ai_query.strip():
                with st.spinner("AI 正在匹配标的..."):
                    st.session_state["ai_results"] = engine.get_ai_screener(ai_query)

# ── 4. 主界面逻辑 ──────────────────────────────────────────────────────────
st.markdown('<p class="main-header">🐉 龙眼 A股深度研判系统</p>', unsafe_allow_html=True)
st.markdown('<div class="brand-bar" style="background:#1a0000; padding:8px 15px; border-radius:5px; color:#FFD700; font-size:0.8rem; margin-bottom:20px;">'
            '🐯 基于虎之眼 (Eye of Tiger) 金融内核 · 指南针 CYQ 筹码模型 · 极速行情引擎</div>', unsafe_allow_html=True)

# 选股池展示区
if st.session_state["ai_results"] is not None:
    st.subheader("🎯 匹配标的 (带胜率追踪)")
    for _, row in st.session_state["ai_results"].iterrows():
        c1, c2 = st.columns([5, 1])
        with c1:
            st.markdown(f"""
            <div class="pool-card">
                <b style="color:#fff;">{row['名称']} ({row['代码']})</b> 
                <span style="color:#FF4444; margin-left:10px;">{row['涨跌幅']}%</span>
                <span style="color:#FFD700; margin-left:15px; font-size:0.8rem;">{row['AI胜率标签']}</span>
                <p style="color:#888; font-size:0.8rem; margin:5px 0;">理由: {row['虎眼理由']}</p>
                <small style="color:#444;">历史最高涨幅: {row['入选后最高涨幅']}</small>
            </div>
            """, unsafe_allow_html=True)
        with c2:
            if st.button("研判", key=f"p_{row['代码']}"):
                st.session_state["active_ticker"] = row['代码']
                st.rerun()

# 研判报告执行
if run_main:
    target = st.session_state["active_ticker"]
    with st.status(f"🔍 虎之眼正在穿透 {target}...", expanded=True) as status:
        # [Fix] 核心修复：调用 get_full_context 确保不超时
        ctx = engine.get_full_context(target, target)
        
        if ctx.get("price_info", {}).get("current_price") == "N/A":
            st.error("⚠️ 股价读取超时。云端 IP 受限，已尝试多源保底。请确认代码正确。")
            st.stop()
            
        reports = []
        tab_names = [os.path.basename(s)[3:-3] for s in active_skills]
        with ThreadPoolExecutor(max_workers=len(active_skills)) as executor:
            futures = {executor.submit(orchestrator.consult_skill, s, target, ctx): s for s in active_skills}
            for future in as_completed(futures):
                reports.append(future.result())

        final_verdict = orchestrator.synthesize_cio(target, reports, ctx)
        status.update(label="研判成功 ✅", state="complete")

    # 渲染结果
    p = ctx['price_info']
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("标的", ctx.get('company_name'))
    c2.metric("价格", f"¥{p['current_price']}", f"{p['change_pct']}%")
    c3.metric("获利盘", ctx.get('profit_ratio', 'N/A'))
    c4.metric("中债 10Y", f"{ctx.get('macro_rate')}%")

    st.subheader("👑 CIO 综合裁决")
    st.markdown(f'<div class="verdict-box">{final_verdict}</div>', unsafe_allow_html=True)