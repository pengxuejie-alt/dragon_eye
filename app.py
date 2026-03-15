import streamlit as st
import glob, os, datetime, re
import pandas as pd
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.engine import AShareDataEngine
from core.agents import LongEyeOrchestrator

# 1. 基础页面配置
st.set_page_config(page_title="🐉 龙眼 Pro — 虎之眼内核", layout="wide", initial_sidebar_state="expanded")

# 2. 注入符合国内服务器审美的暗黑金配色 CSS
st.markdown("""
<style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    .stTabs [data-baseweb="tab-list"] button { font-size: 16px !important; font-weight: 600; }
    .stMetric { background:#0d0d0d; border-radius:10px; border-bottom:3px solid #CC0000; padding:15px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
    .verdict-box { 
        background:#0a0a0a; color:#FFD700; padding:25px; 
        border-left:5px solid #CC0000; border-radius:10px; 
        min-height:400px; line-height:1.8; font-size: 1.1rem;
        box-shadow: inset 0 0 20px rgba(204,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

# 3. 初始化会话状态
if "active_ticker" not in st.session_state: st.session_state["active_ticker"] = "600519"
if "report_data" not in st.session_state: st.session_state["report_data"] = None

# 4. 系统加载 (已修正 rreturn 语法错误)
@st.cache_resource
def load_system():
    # 这里的 Orchestrator 会自动读取 .streamlit/secrets.toml 中的百炼 Key
    return AShareDataEngine(), LongEyeOrchestrator()

engine, orchestrator = load_system()

def render_radar_hexagon(scores: list, labels: list):
    """绘制量化六边形图"""
    # 确保标签和数据对齐
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=scores + [scores[0]], 
        theta=labels + [labels[0]],
        fill="toself", 
        fillcolor="rgba(204,0,0,0.4)", 
        line=dict(color="#CC0000", width=3)
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], color="#888", gridcolor="#333"),
            angularaxis=dict(color="#888", gridcolor="#333"),
            gridshape="polygon", 
            bgcolor="rgba(0,0,0,0)"
        ),
        showlegend=False, 
        paper_bgcolor="rgba(0,0,0,0)", 
        margin=dict(l=50, r=50, t=40, b=40), 
        height=400
    )
    return fig

# ── 5. 侧边栏：1, 2 固定架构 ──
with st.sidebar:
    st.markdown('<p style="font-size:2rem;font-weight:900;color:#CC0000;margin-bottom:10px;">🐉 龙眼研判</p>', unsafe_allow_html=True)
    st.markdown('<p style="color:#666;font-size:0.8rem;">虎之眼金融内核 v12.0 (百炼版)</p>', unsafe_allow_html=True)
    st.divider()
    
    menu = st.tabs(["📊 个股研判", "🔭 选股雷达"])

    with menu[0]:
        t_in = st.text_input("代码/名称", value=st.session_state["active_ticker"])
        st.session_state["active_ticker"] = t_in.strip()
        
        st.write("---")
        st.write("🧩 审计专家配置")
        skill_paths = sorted(glob.glob("skills/0[1-6]*.md"))
        active_skills = [s for s in skill_paths if st.checkbox(os.path.basename(s)[3:-3], value=True, key=f"sk_{s}")]
        
        st.write("---")
        run_audit = st.button("🚀 启动穿透审计", type="primary", use_container_width=True)

    with menu[1]:
        mode = st.selectbox("雷达模式", ["异动扫描", "资金净流入", "自然语言模式"])
        q = st.text_area("描述需求") if mode == "自然语言模式" else ""
        if st.button("🔭 开启监测", use_container_width=True):
            with st.spinner("雷达扫描中..."):
                st.session_state["radar_results"] = engine.scan_radar(mode, q)
            st.rerun()

# ── 6. 主界面渲染 ──
st.markdown('<h1 style="color:#CC0000;margin-top:-20px;">🐉 龙眼 — A股智能研判终端</h1>', unsafe_allow_html=True)

# 处理雷达跳转逻辑
if st.session_state.get("radar_results") is not None:
    with st.expander("🎯 指南针异动雷达 (点击即可研判)", expanded=True):
        cols = st.columns(2)
        for idx, row in st.session_state["radar_results"].iterrows():
            with cols[idx % 2]:
                if st.button(f"{row['名称']} ({row['代码']}) | 涨幅: {row['涨跌幅']}%", key=f"radar_{row['代码']}", use_container_width=True):
                    st.session_state["active_ticker"] = row['代码']
                    st.session_state["report_data"] = None
                    st.rerun()

# 审计逻辑执行
if run_audit:
    target = st.session_state["active_ticker"]
    with st.status(f"🔍 虎之眼正在深度审计: {target}...", expanded=True) as status:
        # 获取国内行情与宏观数据
        ctx = engine.get_full_context(target, target)
        
        t_names = [os.path.basename(s)[3:-3] for s in active_skills]
        reports_map = {}
        
        # 开启多线程并行审计，大幅减少等待时间
        with ThreadPoolExecutor(max_workers=len(active_skills)) as exe:
            futs = {exe.submit(orchestrator.consult_skill, s, target, ctx): s for s in active_skills}
            for f in as_completed(futs): 
                reports_map[futs[f]] = f.result()
        
        ordered_reports = [reports_map[s] for s in active_skills]
        # CIO 汇总最终裁决
        verdict = orchestrator.synthesize_cio(target, ordered_reports, ctx)
        
        # 动态分数提取逻辑 (正则匹配：评分: [x,x,x,x,x,x])
        scores = [50, 50, 50, 50, 50, 50] # 默认分
        score_match = re.search(r"评分[:：]\s*\[(.*?)\]", verdict)
        if score_match:
            try:
                scores = [int(s.strip()) for s in score_match.group(1).split(',')]
                # 补齐长度不足的情况
                while len(scores) < 6: scores.append(50)
            except: pass

        st.session_state["report_data"] = {
            "ctx": ctx, "reports": ordered_reports, "verdict": verdict, 
            "t_names": t_names, "scores": scores
        }
        status.update(label="研判完毕 ✅", state="complete")

# 7. 最终成果展示
if st.session_state.get("report_data"):
    data = st.session_state["report_data"]
    p = data["ctx"]["price_info"]
    st.divider()
    
    # 顶部关键指标栏
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("标的名字", data["ctx"]["company_name"])
    m2.metric("当前价格", f"¥{p['current_price']}", f"{p['change_pct']}%")
    m3.metric("获利比例 (CYQ)", data["ctx"]["profit_ratio"])
    m4.metric("十年债收益", f"{data['ctx']['macro_rate']}%")

    # 核心结论与六边形图
    res_l, res_r = st.columns([3, 2])
    with res_l:
        st.subheader("👑 CIO 综合裁决")
        st.markdown(f'<div class="verdict-box">{data["verdict"]}</div>', unsafe_allow_html=True)
    with res_r:
        st.subheader("📊 虎之眼量化维度评分")
        st.plotly_chart(render_radar_hexagon(data["scores"], data["t_names"]), use_container_width=True)

    # 专家研判详情 Tabs
    st.divider()
    st.subheader("🕵️ 专项审计专家报告")
    tabs = st.tabs(data["t_names"])
    for i, tab in enumerate(tabs):
        with tab: 
            st.markdown(data["reports"][i])

# 8. 自动清理与维持
st.sidebar.write("---")
if st.sidebar.button("🧹 清理会话缓存"):
    st.session_state["report_data"] = None
    st.rerun()