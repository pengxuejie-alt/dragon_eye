import streamlit as st
import glob, os, datetime, re
import pandas as pd
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.engine import AShareDataEngine
from core.agents import LongEyeOrchestrator

st.set_page_config(page_title="🐉 龙眼 Pro — 虎之眼内核", layout="wide")

# UI 固定与修复
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] button { font-size: 15px !important; }
    .stMetric { background:#0d0d0d; border-radius:8px; border-bottom:3px solid #CC0000; padding:12px; }
    .verdict-box { background:#0d0d0d; color:#FFD700; padding:25px; border-left:5px solid #CC0000; border-radius:10px; min-height:380px; }
</style>
""", unsafe_allow_html=True)

if "active_ticker" not in st.session_state: st.session_state["active_ticker"] = "600519"
if "report_data" not in st.session_state: st.session_state["report_data"] = None

@st.cache_resource
def load_system():
    return AShareDataEngine(), LongEyeOrchestrator(api_key=st.secrets["GEMINI_KEY"])

engine, orchestrator = load_system()

def render_hexagon(scores: list, labels: list):
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=scores + [scores[0]], theta=labels + [labels[0]],
        fill="toself", fillcolor="rgba(204,0,0,0.4)", line=dict(color="#CC0000", width=2)
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100], color="#555"), gridshape="polygon", bgcolor="#0d0d0d"),
        showlegend=False, paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=40, r=40, t=30, b=30), height=380
    )
    return fig

# ── 侧边栏：1, 2 固定架构 ──
with st.sidebar:
    st.markdown('<p style="font-size:1.8rem;font-weight:900;color:#CC0000;margin:0;">🐉 龙眼研判</p>', unsafe_allow_html=True)
    st.divider()
    menu = st.tabs(["📊 个股研判", "🔭 选股雷达"])

    with menu[0]:
        t_in = st.text_input("代码/名称", value=st.session_state["active_ticker"])
        st.session_state["active_ticker"] = t_in.strip()
        skill_paths = sorted(glob.glob("skills/0[1-6]*.md"))
        active_skills = [s for s in skill_paths if st.checkbox(os.path.basename(s)[3:-3], value=True, key=f"sk_{s}")]
        run_audit = st.button("🚀 启动穿透审计", type="primary", use_container_width=True)

    with menu[1]:
        mode = st.selectbox("雷达模式", ["异动扫描", "资金净流入", "自然语言模式"])
        q = st.text_area("描述需求") if mode == "自然语言模式" else ""
        if st.button("🔭 开启监测", use_container_width=True):
            st.session_state["radar_results"] = engine.scan_radar(mode, q)
            st.rerun()

# ── 主界面渲染 ──
st.markdown('<h1 style="color:#CC0000;">🐉 龙眼 — 虎之眼金融内核</h1>', unsafe_allow_html=True)

# 选股池 (修复跳转)
if st.session_state.get("radar_results") is not None:
    with st.expander("🎯 雷达结果 (点击审计)", expanded=True):
        for _, row in st.session_state["radar_results"].iterrows():
            if st.button(f"{row['名称']} ({row['代码']}) | 涨幅: {row['涨跌幅']}%", key=row['代码']):
                st.session_state["active_ticker"] = row['代码']
                st.session_state["report_data"] = None
                st.rerun()

# 审计逻辑
if run_audit:
    target = st.session_state["active_ticker"]
    with st.status(f"🔍 正在穿透审计: {target}...", expanded=True) as status:
        ctx = engine.get_full_context(target, target)
        if ctx["price_info"]["current_price"] == "N/A":
            st.error("⚠️ 通讯链路受阻，IP 已被封锁。建议稍后重试。")
            st.stop()
        
        t_names = [os.path.basename(s)[3:-3] for s in active_skills]
        reports_map = {}
        with ThreadPoolExecutor(max_workers=len(active_skills)) as exe:
            futs = {exe.submit(orchestrator.consult_skill, s, target, ctx): s for s in active_skills}
            for f in as_completed(futs): reports_map[futs[f]] = f.result()
        
        ordered_reports = [reports_map[s] for s in active_skills]
        verdict = orchestrator.synthesize_cio(target, ordered_reports, ctx)
        st.session_state["report_data"] = {"ctx": ctx, "reports": ordered_reports, "verdict": verdict, "t_names": t_names, "scores": [85, 75, 90, 60, 80, 95]}
        status.update(label="审计完毕 ✅", state="complete")

if st.session_state.get("report_data"):
    data = st.session_state["report_data"]
    p = data["ctx"]["price_info"]
    st.divider()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("公司名称", data["ctx"]["company_name"])
    c2.metric("价格", f"¥{p['current_price']}", f"{p['change_pct']}%")
    c3.metric("获利比例", data["ctx"]["profit_ratio"])
    c4.metric("中债 10Y", f"{data['ctx']['macro_rate']}%")

    l, r = st.columns([3, 2])
    with l:
        st.subheader("👑 CIO 综合裁决")
        st.markdown(f'<div class="verdict-box">{data["verdict"]}</div>', unsafe_allow_html=True)
    with r:
        st.subheader("📊 维度评分图")
        st.plotly_chart(render_hexagon(data["scores"], data["t_names"]), use_container_width=True)

    st.divider()
    tabs = st.tabs(data["t_names"])
    for i, tab in enumerate(tabs):
        with tab: st.markdown(data["reports"][i])