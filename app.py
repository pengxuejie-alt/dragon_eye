import streamlit as st
import glob, os, datetime
import pandas as pd
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.engine import AShareDataEngine
from core.agents import LongEyeOrchestrator

# ── 1. 页面配置与 CSS ──
st.set_page_config(page_title="🐉 龙眼 Pro — 虎之眼内核", layout="wide")

st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] button { font-size: 14px !important; padding: 0 10px !important; }
    .stMetric { background: #0d0d0d; border-radius: 8px; border-bottom: 3px solid #CC0000; padding: 12px; }
    .verdict-box { background: #0d0d0d; color: #FFD700; padding: 25px; border-left: 5px solid #CC0000; border-radius: 10px; min-height: 380px;}
</style>
""", unsafe_allow_html=True)

# ── 2. 初始化 Session ──
if "active_ticker" not in st.session_state: st.session_state["active_ticker"] = "600519"
if "report_data" not in st.session_state: st.session_state["report_data"] = None
if "radar_results" not in st.session_state: st.session_state["radar_results"] = None

@st.cache_resource
def load_system():
    return AShareDataEngine(), LongEyeOrchestrator(api_key=st.secrets["GEMINI_KEY"])

engine, orchestrator = load_system()

# ── 3. 辅助函数：六边形评分图 ──
def render_hexagon(scores):
    categories = ['价值审计', '技术强度', '行业格局', '资金博弈', '成长质量', '风控安全']
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=scores + [scores[0]], theta=categories + [categories[0]],
        fill='toself', fillcolor='rgba(204, 0, 0, 0.4)', line=dict(color='#CC0000', width=2)
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100], color="#555"), 
                   gridshape='polygon', bgcolor="#0d0d0d"),
        showlegend=False, paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=40, r=40, t=30, b=30), height=380
    )
    return fig

# ── 4. 侧边栏：模块化架构 (遵循长期记忆) ──
with st.sidebar:
    st.markdown('<p style="font-size:1.8rem;font-weight:900;color:#CC0000;margin:0;">🐉 龙眼研判</p>', unsafe_allow_html=True)
    st.markdown('<p style="color:#FF8C00;font-style:italic;font-size:0.8rem;">虎之眼 Eye of Tiger 金融内核</p>', unsafe_allow_html=True)
    st.divider()

    # 严格固定 1, 2 架构
    menu = st.tabs(["📊 个股研判", "🔭 选股雷达"])

    with menu[0]:
        t_in = st.text_input("代码/名称", value=st.session_state["active_ticker"], key="main_search")
        st.session_state["active_ticker"] = t_in
        skill_paths = sorted(glob.glob("skills/0[1-6]*.md"))
        active_skills = [s for s in skill_paths if st.checkbox(os.path.basename(s)[3:-3], value=True, key=f"sk_{s}")]
        run_audit = st.button("🚀 启动穿透审计", type="primary", use_container_width=True)

    with menu[1]:
        st.markdown("**指南针模式选股**")
        radar_mode = st.selectbox("核心指标", ["异动扫描", "资金净流入", "自然语言模式"])
        
        user_query = ""
        if radar_mode == "自然语言模式":
            user_query = st.text_area("需求描述", placeholder="如：回撤小且处于上涨趋势的科技股")
        
        if st.button("🔭 开启雷达监测", use_container_width=True):
            with st.spinner("雷达探测中..."):
                # 修复核心报错点
                st.session_state["radar_results"] = engine.scan_radar(mode=radar_mode, query=user_query)
                st.rerun()

# ── 5. 主界面渲染 ──
st.markdown('<h1 style="color:#CC0000;">🐉 龙眼 — 虎之眼金融内核</h1>', unsafe_allow_html=True)

# 选股雷达结果展示 (修复点击无反应)
if st.session_state["radar_results"] is not None:
    with st.expander("🎯 雷达扫描结果 (点击标的跳转研判)", expanded=True):
        for _, row in st.session_state["radar_results"].iterrows():
            c1, c2 = st.columns([5, 1])
            with c1:
                st.markdown(f"""<div style="background:#111;padding:10px 15px;border-radius:5px;border-left:4px solid #CC0000;margin-bottom:5px;">
                    <b>{row['名称']} ({row['代码']})</b> <span style="color:#FFD700;margin-left:20px;">历史最高涨幅: {row['最高涨幅']}</span>
                    <span style="color:#666;font-size:0.8rem;margin-left:15px;">理由: {row['理由']}</span></div>""", unsafe_allow_html=True)
            with c2:
                if st.button("审计", key=f"r_{row['代码']}", use_container_width=True):
                    st.session_state["active_ticker"] = row['代码']
                    st.session_state["report_data"] = None 
                    st.rerun()

# 审计逻辑执行
if run_audit:
    target = st.session_state["active_ticker"]
    with st.status(f"🔍 正在穿透审计: {target}...", expanded=True) as status:
        ctx = engine.get_full_context(target, target)
        if ctx["price_info"]["current_price"] == "N/A":
            st.error("⚠️ 股价读取超时，云端 IP 受限。请确认代码正确后重试。")
            st.stop()

        reports, t_names = [], [os.path.basename(s)[3:-3] for s in active_skills]
        with ThreadPoolExecutor(max_workers=len(active_skills)) as exe:
            futs = {exe.submit(orchestrator.consult_skill, s, target, ctx): s for s in active_skills}
            for f in as_completed(futs): reports.append(f.result())
        verdict = orchestrator.synthesize_cio(target, reports, ctx)
        
        # [新增] 让 AI 输出分数以驱动六边形图 (目前为模拟分)
        scores = [85, 70, 95, 60, 80, 90]
        st.session_state["report_data"] = {"ctx": ctx, "reports": reports, "verdict": verdict, "t_names": t_names, "scores": scores}
        status.update(label="研判完毕 ✅", state="complete")

# ── 6. 最终成果展示 (六边形图) ──
if st.session_state["report_data"]:
    data = st.session_state["report_data"]
    p = data["ctx"]['price_info']
    
    st.divider()
    c_info1, c_info2, c_info3, c_info4 = st.columns(4)
    c_info1.metric("公司名称", data["ctx"].get('company_name', st.session_state["active_ticker"]))
    c_info2.metric("当前价格", f"¥{p['current_price']}", f"{p['change_pct']}%")
    c_info3.metric("获利比例", data["ctx"].get('profit_ratio', 'N/A'))
    c_info4.metric("十年债收益", f"{data['ctx'].get('macro_rate')}%")

    res_l, res_r = st.columns([3, 2])
    with res_l:
        st.subheader("👑 CIO 综合裁决")
        st.markdown(f'<div class="verdict-box">{data["verdict"]}</div>', unsafe_allow_html=True)
    with res_r:
        st.subheader("📊 虎之眼维度评分")
        # 渲染六边形图
        st.plotly_chart(render_hexagon(data["scores"]), use_container_width=True)

    st.divider()
    tabs = st.tabs(data["t_names"])
    for i, tab in enumerate(tabs):
        with tab:
            st.markdown(f'<p style="color:#888;font-size:0.8rem;">🐯 虎之眼 {data["t_names"][i]} 专项审计报告</p>', unsafe_allow_html=True)
            st.markdown(data["reports"][i])