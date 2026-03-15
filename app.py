import streamlit as st
import glob, os, datetime, re
import pandas as pd
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.engine import AShareDataEngine
from core.agents import LongEyeOrchestrator

# 1. 基础页面配置
st.set_page_config(page_title="🐉 龙眼 Pro — 虎之眼内核", layout="wide", initial_sidebar_state="expanded")

# 2. 注入符合国内服务器审美的暗黑金配色 CSS (优化版)
st.markdown("""
<style>
    /* 全局背景 */
    .stApp { background-color: #050505; color: #e0e0e0; }
    
    /* 标签页优化 */
    .stTabs [data-baseweb="tab-list"] button { font-size: 16px !important; font-weight: 600; color: #ccc; }
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] { color: #CC0000; border-bottom: 2px solid #CC0000; }
    
    /* 指标卡统一样式 - 修复排列错乱 */
    div[data-testid="stMetric"] { 
        background:#0d0d0d; 
        border-radius:8px; 
        border:1px solid #333; 
        padding:15px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.5); 
        margin-bottom: 10px;
    }
    div[data-testid="stMetricValue"] { color: #fff; font-weight: bold; }
    div[data-testid="stMetricDelta"] { color: #00cc00; }
    
    /* CIO 裁决盒 - 金文质感 */
    .verdict-box { 
        background: linear-gradient(145deg, #0a0a0a, #111); 
        color: #FFD700; 
        padding:30px; 
        border-left:6px solid #CC0000; 
        border-radius:12px; 
        min-height:400px; 
        line-height:1.8; 
        font-size: 1.05rem;
        box-shadow: inset 0 0 30px rgba(204,0,0,0.15), 0 10px 20px rgba(0,0,0,0.5);
        overflow-y: auto;
        max-height: 600px;
    }
    .verdict-box strong { color: #fff; }
    .verdict-box blockquote { border-left: 3px solid #CC0000; margin: 10px 0; padding-left: 15px; color: #aaa; }
</style>
""", unsafe_allow_html=True)

# 3. 初始化会话状态
if "active_ticker" not in st.session_state: st.session_state["active_ticker"] = "600519"
if "report_data" not in st.session_state: st.session_state["report_data"] = None

# 4. 系统加载
@st.cache_resource
def load_system():
    return AShareDataEngine(), LongEyeOrchestrator()

engine, orchestrator = load_system()

def render_radar_hexagon(scores: list, labels: list):
    """绘制高对比度量化六边形图 (暗黑模式专用)"""
    fig = go.Figure()
    
    # 填充区域：半透明红色
    fig.add_trace(go.Scatterpolar(
        r=scores + [scores[0]], 
        theta=labels + [labels[0]],
        fill="toself", 
        fillcolor="rgba(204, 0, 0, 0.25)", 
        line=dict(color="#CC0000", width=3, shape='spline')
    ))
    
    # 关键：手动配置 Polar 布局以解决看不清的问题
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True, 
                range=[0, 100], 
                color="#888", 
                gridcolor="#444",      # 加粗网格线颜色
                gridwidth=2,
                tickcolor="#666",
                tickfont=dict(size=10, color="#aaa")
            ),
            angularaxis=dict(
                color="#fff",          # 角度文字白色
                gridcolor="#444",      # 角度网格线
                gridwidth=2,
                tickfont=dict(size=12, color="#fff")
            ),
            gridshape="polygon", 
            bgcolor="rgba(0,0,0,0)"    # 透明背景
        ),
        showlegend=False, 
        paper_bgcolor="rgba(0,0,0,0)", 
        margin=dict(l=40, r=40, t=40, b=40), 
        height=450
    )
    return fig

# ── 5. 侧边栏 ──
with st.sidebar:
    st.markdown('<p style="font-size:2rem;font-weight:900;color:#CC0000;margin-bottom:5px;">🐉 龙眼研判</p>', unsafe_allow_html=True)
    st.markdown('<p style="color:#666;font-size:0.8rem;margin-top:-10px;">虎之眼金融内核 v12.0 (百炼版)</p>', unsafe_allow_html=True)
    st.divider()
    
    menu = st.tabs(["📊 个股研判", "🔭 选股雷达"])
    
    with menu[0]:
        t_in = st.text_input("代码/名称", value=st.session_state["active_ticker"], label_visibility="collapsed")
        if t_in.strip() != st.session_state["active_ticker"]:
            st.session_state["active_ticker"] = t_in.strip()
            st.session_state["report_data"] = None # 切换股票时清空旧报告
        
        st.write("---")
        st.write("🧩 **审计专家配置**")
        skill_paths = sorted(glob.glob("skills/0[1-6]*.md"))
        active_skills = []
        for s in skill_paths:
            name = os.path.basename(s)[3:-3]
            if st.checkbox(name, value=True, key=f"sk_{s}"):
                active_skills.append(s)
        
        st.write("---")
        run_audit = st.button("🚀 启动穿透审计", type="primary", use_container_width=True)
        
    with menu[1]:
        mode = st.selectbox("雷达模式", ["异动扫描", "资金净流入", "自然语言模式"])
        q = ""
        if mode == "自然语言模式":
            q = st.text_area("描述需求 (例：低估值蓝筹)", height=60)
        
        if st.button("🔭 开启监测", use_container_width=True):
            with st.spinner("雷达扫描中..."):
                try:
                    st.session_state["radar_results"] = engine.scan_radar(mode, q)
                except Exception as e:
                    st.error(f"雷达扫描失败：{str(e)}")
            st.rerun()

# ── 6. 主界面渲染 ──
st.markdown('<h1 style="color:#CC0000;margin-top:-20px;font-family:sans-serif;">🐉 龙眼 — A股智能研判终端</h1>', unsafe_allow_html=True)

# 处理雷达跳转逻辑 (优化点击反馈)
if st.session_state.get("radar_results") is not None and not st.session_state.get("radar_results").empty:
    with st.expander("🎯 指南针异动雷达 (点击卡片立即研判)", expanded=True):
        cols = st.columns(2)
        for idx, row in st.session_state["radar_results"].iterrows():
            with cols[idx % 2]:
                # 使用 container 包裹按钮以增加点击区域感
                with st.container():
                    btn_label = f"**{row['名称']} ({row['代码']})** \n\n涨幅：{row['涨跌幅']}%"
                    if st.button(btn_label, key=f"radar_{row['代码']}", use_container_width=True):
                        st.session_state["active_ticker"] = str(row['代码'])
                        st.session_state["report_data"] = None
                        st.rerun() # 立即重载

# 审计逻辑执行
if run_audit:
    target = st.session_state["active_ticker"]
    if not target:
        st.warning("请输入股票代码或名称")
    else:
        with st.status(f"🔍 虎之眼正在深度审计：**{target}** ...", expanded=True) as status:
            try:
                # 获取国内行情与宏观数据
                ctx = engine.get_full_context(target, target)
                
                t_names = [os.path.basename(s)[3:-3] for s in active_skills]
                reports_map = {}
                
                # 开启多线程并行审计
                with ThreadPoolExecutor(max_workers=min(len(active_skills), 6)) as exe:
                    futs = {exe.submit(orchestrator.consult_skill, s, target, ctx): s for s in active_skills}
                    for f in as_completed(futs): 
                        reports_map[futs[f]] = f.result()
                
                ordered_reports = [reports_map[s] for s in active_skills]
                
                # CIO 汇总最终裁决
                verdict = orchestrator.synthesize_cio(target, ordered_reports, ctx)
                
                # 【优化】评分提取鲁棒性增强
                scores = [50, 50, 50, 50, 50, 50] # 默认分
                score_match = re.search(r"评分[:：]\s*\[(.*?)\]", verdict)
                
                if score_match:
                    try:
                        raw_scores = score_match.group(1).split(',')
                        parsed_scores = []
                        for s in raw_scores:
                            # 清理非数字字符
                            clean_s = re.sub(r'[^\d]', '', s.strip())
                            if clean_s:
                                val = int(clean_s)
                                # 限制范围 0-100
                                parsed_scores.append(min(max(val, 0), 100))
                        
                        scores = parsed_scores
                        # 补齐长度
                        while len(scores) < 6: scores.append(50)
                        scores = scores[:6] # 截断多余
                    except Exception as e:
                        st.warning(f"评分解析异常，使用默认分：{e}")
                else:
                    # Fallback: 尝试从文本关键词推断 (简单版)
                    if "强烈买入" in verdict: scores = [90]*6
                    elif "卖出" in verdict or "高危" in verdict: scores = [30]*6
                
                st.session_state["report_data"] = {
                    "ctx": ctx, "reports": ordered_reports, "verdict": verdict, 
                    "t_names": t_names, "scores": scores
                }
                status.update(label="✅ 研判完毕", state="complete")
            except Exception as e:
                st.error(f"审计过程中发生错误：{str(e)}")
                status.update(label="❌ 审计失败", state="error")

# 7. 最终成果展示
if st.session_state.get("report_data"):
    data = st.session_state["report_data"]
    p = data["ctx"]["price_info"]
    st.divider()
    
    # 顶部关键指标栏 (优化列间距)
    m1, m2, m3, m4 = st.columns(4, gap="large")
    m1.metric("标的名字", data["ctx"]["company_name"])
    
    # 处理价格显示
    price_val = p.get('current_price', 'N/A')
    change_val = p.get('change_pct', 0)
    delta_color = "normal" if change_val >= 0 else "inverse" # A股红涨绿跌通常需自定义，这里保持默认或反转
    # 注意：Streamlit 默认绿色为正，A股需心理转换或自定义CSS，此处暂用默认
    m2.metric("当前价格", f"¥{price_val}", f"{change_val}%")
    
    m3.metric("获利比例 (CYQ)", data["ctx"].get("profit_ratio", "N/A"))
    m4.metric("十年债收益", f"{data['ctx']['macro_rate']}%")
    
    # 核心结论与六边形图
    res_l, res_r = st.columns([3, 2], gap="large")
    
    with res_l:
        st.subheader("👑 CIO 综合裁决")
        # 使用 HTML 容器渲染裁决，支持更好的 Markdown 嵌套
        st.markdown(f'<div class="verdict-box">{data["verdict"]}</div>', unsafe_allow_html=True)
        
    with res_r:
        st.subheader("📊 虎之眼量化维度")
        st.plotly_chart(render_radar_hexagon(data["scores"], data["t_names"]), use_container_width=True)
        
        # 简易评分列表
        st.write("**维度得分详情:**")
        for label, score in zip(data["t_names"], data["scores"]):
            st.progress(score/100)
            st.caption(f"{label}: {score}")

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
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()