"""
龙眼 (LongEye) A股深度研判系统 v4.0
内核：虎之眼 (Eye of Tiger) 金融审计内核
[核心修复] 侧边栏架构固定 & 云端股价读取 Bug 修复
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
    .pool-card:hover { border-left-color: var(--tiger-red); background: #161616; }
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

# ── 3. 侧边栏（严格固定架构） ────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<p style="font-size:1.5rem; font-weight:900; color:#CC0000; margin:0;">🐉 龙眼研判</p>', unsafe_allow_html=True)
    st.markdown('<p class="brand-tag">虎之眼 Eye of Tiger 金融内核</p>', unsafe_allow_html=True)
    st.divider()
    
    # 严格遵循用户要求的 1, 2, 3 结构
    sb_tabs = st.tabs(["📊 股票研判", "🔭 选股雷达", "🤖 自然语言选股"])
    
    # --- 1. 股票研判 ---
    with sb_tabs[0]:
        st.caption("输入代码后点击「启动研判」")
        ticker_input = st.text_input("股票代码", value=st.session_state["active_ticker"], key="in_ticker")
        if ticker_input:
            st.session_state["active_ticker"] = ticker_input
            
        skill_paths = sorted(glob.glob("skills/0[1-6]*.md"))
        active_skills = [s for s in skill_paths if st.checkbox(os.path.basename(s)[3:-3], value=True, key=f"sk_{s}")]
        
        run_main = st.button("🚀 启动全维度审计", type="primary", use_container_width=True)

    # --- 2. 选股雷达 ---
    with sb_tabs[1]:
        strat = st.selectbox("选择雷达模式", ["涨停最强", "虎之眼价值", "游资博弈榜"])
        if st.button("🔭 执行扫描", use_container_width=True):
            with st.spinner("雷达正在探测异动..."):
                st.session_state["ai_results"] = engine.get_strategy_pool(strat)

    # --- 3. 自然语言选股 ---
    with sb_tabs[2]:
        ai_query = st.text_area("小白选股描述", placeholder="例如：帮我挑几只快速上涨而回撤不多的股票", height=100)
        if st.button("🧠 语义扫描", use_container_width=True):
            if ai_query.strip():
                with st.spinner("AI 正在匹配标的..."):
                    st.session_state["ai_results"] = engine.get_ai_screener(ai_query)

# ── 4. 主界面：研判报告区 ────────────────────────────────────────────────────
st.markdown('<p class="main-header">🐉 龙眼 A股深度研判系统</p>', unsafe_allow_html=True)
st.markdown('<div style="background:#1a0000; padding:8px 15px; border-radius:5px; color:#FFD700; font-size:0.8rem; margin-bottom:20px;">'
            '🐯 虎之眼 (Eye of Tiger) 金融内核 · 极速多源行情引擎 · 指南针 CYQ 筹码模型</div>', unsafe_allow_html=True)

# 选股池展示逻辑
if st.session_state["ai_results"] is not None:
    st.subheader("🎯 推荐标的 (AI 胜率追踪)")
    for _, row in st.session_state["ai_results"].iterrows():
        c1, c2 = st.columns([5, 1])
        with c1:
            st.markdown(f"""
            <div class="pool-card">
                <b style="color:#fff;">{row['名称']} ({row['代码']})</b> 
                <span style="color:#FF4444; margin-left:10px;">{row['涨跌幅']}%</span>
                <span style="color:#FFD700; margin-left:15px; font-size:0.8rem;">{row['AI胜率标签']}</span>
                <p style="color:#888; font-size:0.8rem; margin:5px 0;">🐯 推荐理由: {row['虎眼理由']}</p>
                <small style="color:#444;">入选日期: {row['AI入选日']} | 历史最高涨幅: <span style="color:#00FF88;">{row['入选后最高涨幅']}</span></small>
            </div>
            """, unsafe_allow_html=True)
        with c2:
            st.write("") # 间距
            if st.button("研判", key=f"p_{row['代码']}"):
                st.session_state["active_ticker"] = row['代码']
                st.rerun()

# 执行深度审计
if run_main:
    target = st.session_state["active_ticker"]
    with st.status(f"🔍 虎之眼正在穿透 {target}...", expanded=True) as status:
        # [Fix] 核心修复点：调用 get_full_context 触发多源保底行情
        ctx = engine.get_full_context(target, target)
        
        if ctx.get("price_info", {}).get("current_price") == "N/A":
            st.error("⚠️ 行情读取失败。Streamlit 云端 IP 受限，已尝试新浪/腾讯多源保底。请确认代码正确。")
            st.stop()
            
        reports = []
        tab_names = [os.path.basename(s)[3:-3] for s in active_skills]
        with ThreadPoolExecutor(max_workers=len(active_skills)) as executor:
            futures = {executor.submit(orchestrator.consult_skill, s, target, ctx): s for s in active_skills}
            for future in as_completed(futures):
                reports.append(future.result())

        final_verdict = orchestrator.synthesize_cio(target, reports, ctx)
        status.update(label="研判报告生成完毕 ✅", state="complete")

    # 指标卡渲染
    p = ctx['price_info']
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("标的名称", ctx.get('company_name'))
    c2.metric("当前价格", f"¥{p['current_price']}", f"{p['change_pct']}%")
    c3.metric("获利盘 (CYQ)", ctx.get('profit_ratio', '暂无数据'))
    c4.metric("中债 10Y", f"{ctx.get('macro_rate')}%")

    st.divider()
    st.subheader("👑 CIO 综合裁决")
    st.markdown(f'<div class="verdict-box">{final_verdict}</div>', unsafe_allow_html=True)