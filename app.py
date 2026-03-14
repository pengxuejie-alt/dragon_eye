"""
龙眼 (LongEye) A股深度研判系统 v4.0
内核：虎之眼 (Eye of Tiger) 金融审计内核
功能：全维度研判 + AI 语义选股池 + 历史胜率追踪
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
    .win-badge { background: #330000; color: #FF4444; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: bold; border: 1px solid #660000; }
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

# ── 3. 侧边栏：选股与配置 ──────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<p style="font-size:1.5rem; font-weight:900; color:#CC0000;">🐉 龙眼研判</p>', unsafe_allow_html=True)
    st.markdown('<p class="brand-tag">虎之眼 Eye of Tiger 金融内核</p>', unsafe_allow_html=True)
    
    side_tab1, side_tab2 = st.tabs(["🤖 AI 选股", "⚙️ 配置"])
    
    with side_tab1:
        st.caption("支持小白口语，如：快速上涨且回撤少")
        ai_query = st.text_area("选股描述", placeholder="帮我挑几只快速上涨而回撤不多的股票...", height=100)
        if st.button("🧠 AI 语义扫描", use_container_width=True, type="primary"):
            if ai_query.strip():
                with st.spinner("AI 引擎正在检索全市场数据..."):
                    st.session_state["ai_results"] = engine.get_ai_screener(ai_query)
            else:
                st.warning("请输入描述建议")
                
    with side_tab2:
        skill_paths = sorted(glob.glob("skills/0[1-6]*.md"))
        active_skills = [s for s in skill_paths if st.checkbox(os.path.basename(s)[3:-3], value=True, key=f"sk_{s}")]

# ── 4. 主界面：研判交互 ────────────────────────────────────────────────────
st.markdown('<p class="main-header">🐉 龙眼 A股深度研判系统</p>', unsafe_allow_html=True)
st.markdown('<div style="background:#1a0000; padding:5px 15px; border-radius:5px; color:#FFD700; font-size:0.8rem; margin-bottom:20px;">'
            '🐯 本研判由龙眼系统执行，基于虎之眼 (Eye of Tiger) 金融内核 · 指南针 CYQ 筹码模型</div>', unsafe_allow_html=True)

# 搜索与研判入口
col_search, col_run = st.columns([4, 1])
with col_search:
    ticker_input = st.text_input("📍 输入标的代码", value=st.session_state["active_ticker"], help="支持 6 位代码")
with col_run:
    st.write(" ") # 占位
    run_main = st.button("🚀 启动研判", use_container_width=True, type="primary")

# ── 5. AI 选股池展示 (亮点功能) ──────────────────────────────────────────────
if st.session_state["ai_results"] is not None:
    st.subheader(f"🎯 AI 选股池推荐 ({len(st.session_state['ai_results'])} 只)")
    for _, row in st.session_state["ai_results"].iterrows():
        with st.container():
            c1, c2 = st.columns([5, 1])
            with c1:
                st.markdown(f"""
                <div class="pool-card">
                    <span style="font-size:1.1rem; font-weight:bold; color:#fff;">{row['名称']} ({row['代码']})</span>
                    <span style="color:#FF4444; font-weight:bold; margin-left:15px;">{row['涨跌幅']}%</span>
                    <span class="win-badge" style="margin-left:10px;">{row['AI胜率标签']}</span>
                    <p style="color:#FF8C00; font-size:0.85rem; margin-top:5px;">🐯 <b>理由:</b> {row['虎眼理由']}</p>
                    <div style="font-size:0.75rem; color:#666;">
                        AI 入选日: {row['AI入选日']} | <b>入选后最高涨幅: <span style="color:#00FF88;">{row['入选后最高涨幅']}</span></b>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            with c2:
                st.write("") # 占位
                if st.button("分析标的", key=f"btn_{row['代码']}", use_container_width=True):
                    st.session_state["active_ticker"] = row['代码']
                    st.rerun()

# ── 6. 研判报告呈现 ────────────────────────────────────────────────────────
if run_main or (ticker_input != st.session_state["active_ticker"]):
    target = ticker_input.strip()
    with st.status(f"🔍 虎之眼正在穿透 {target}...", expanded=True) as status:
        # 1. 获取增强版上下文（包含中债10Y、筹码、ATR等）
        ctx = engine.get_full_context(target, target)
        
        if ctx.get("price_info", {}).get("current_price") == "N/A":
            st.error("⚠️ 股价读取失败，可能由于云端 IP 限制或非交易时段。")
            st.stop()
            
        # 2. 并行调用专家 Agent
        reports = []
        tab_names = [os.path.basename(s)[3:-3] for s in active_skills]
        with ThreadPoolExecutor(max_workers=len(active_skills)) as executor:
            futures = {executor.submit(orchestrator.consult_skill, s, target, ctx): s for s in active_skills}
            for future in as_completed(futures):
                reports.append(future.result())

        # 3. CIO 最终裁决合成
        final_verdict = orchestrator.synthesize_cio(target, reports, ctx)
        status.update(label="研判报告合成完毕 ✅", state="complete")

    # 数据展示区
    pi = ctx['price_info']
    ca = ctx['chip_analysis']
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("标的名称", ctx.get('company_name'))
    m2.metric("当前现价", f"¥{pi['current_price']}", f"{pi['change_pct']}%")
    m3.metric("获利盘 (CYQ)", ca['profit_ratio'])
    m4.metric("中债 10Y", f"{ctx['macro_rate']}%")

    st.divider()
    st.subheader("👑 CIO 综合裁决")
    st.markdown(f'<div class="verdict-box">{final_verdict}</div>', unsafe_allow_html=True)

    # 专家 Tab 分页
    tabs = st.tabs(tab_names)
    for i, tab in enumerate(tabs):
        with tab:
            st.markdown(f'<div style="background:#1a1a1a; padding:10px; border-left:3px solid #666; font-size:0.75rem; color:#888; margin-bottom:15px;">'
                        f'🐯 虎之眼 {tab_names[i]} 专项审计报告</div>', unsafe_allow_html=True)
            st.markdown(reports[i])