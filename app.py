"""
龙眼深度研判系统 v1.0 (LongEye Pro)
- 架构参考: Anthropic Financial Services Plugins
- 核心内核: 虎之眼金融项目 (Eye of Tiger)
- 功能：多 Agent 并行审计、A股选股池、PDF 报告导出
"""

import streamlit as st
import glob
import os
import datetime
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

# 🚨 核心路径修改：从 core 文件夹导入逻辑
from core.engine import AShareDataEngine
from core.agents import LongEyeOrchestrator

# 必须在最开始配置页面
st.set_page_config(
    page_title="🐉 龙眼深度研判 Pro",
    page_icon="🐉",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- 自定义 CSS (龙眼专属：赤金配色) ----------
st.markdown("""
<style>
    .main-title {
        background: linear-gradient(135deg, #8B0000 0%, #CC0000 40%, #FF8C00 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.2rem;
        font-weight: 900;
        letter-spacing: 2px;
    }
    .verdict-box {
        background: linear-gradient(135deg, #1a0000 0%, #2d0a00 100%);
        border: 2px solid #CC0000;
        border-radius: 12px;
        padding: 1.5rem;
        color: #FFD700;
    }
</style>
""", unsafe_allow_html=True)

# ---------- 初始化核心组件 ----------
@st.cache_resource
def init_components():
    # 确保 secrets 中配置了 GEMINI_KEY
    engine = AShareDataEngine()
    orchestrator = LongEyeOrchestrator(api_key=st.secrets["GEMINI_KEY"])
    return engine, orchestrator

engine, orchestrator = init_components()

# ---------- 侧边栏 (Sidebar) ----------
with st.sidebar:
    st.markdown('<p class="main-title">🐉 龙眼研判</p>', unsafe_allow_html=True)
    st.caption("基于虎之眼 (Eye of Tiger) 金融内核")
    st.divider()

    # 输入模块
    ticker_input = st.text_input(
        "📌 股票代码",
        value="600519",
        placeholder="输入6位代码，如 002460",
        help="系统将自动识别沪深北市场"
    ).strip()

    st.divider()
    
    # 🧠 专家 Agent 勾选 (热插拔 Skill 模式)
    st.subheader("🧠 研判专家配置")
    skill_files = sorted(glob.glob("skills/*.md"))
    active_skills = []
    for sf in skill_files:
        name = os.path.basename(sf).split("_")[-1].replace(".md", "")
        if st.checkbox(f"✅ {name}", value=True):
            active_skills.append(sf)

    st.divider()
    
    # 🚀 启动按钮
    run_analysis = st.button("🚀 启动龙眼扫描", use_container_width=True, type="primary")

    # 🔥 选股模块 (解决你提到的没看到选股的问题)
    st.divider()
    st.subheader("🔥 龙眼选股池 (实时异动)")
    if st.button("刷新涨幅榜"):
        try:
            import akshare as ak
            df_spot = ak.stock_zh_a_spot_em()
            # 筛选涨幅前 8 的非退市标的
            top_list = df_spot[~df_spot['名称'].str.contains("退")].sort_values("涨跌幅", ascending=False).head(8)
            for _, row in top_list.iterrows():
                st.code(f"{row['名称']} ({row['代码']}) {row['涨跌幅']}%")
        except:
            st.error("选股数据获取失败")

# ---------- 主内容区 ----------
st.markdown('<h1 class="main-title">🐉 龙眼 A股深度研判系统</h1>', unsafe_allow_html=True)

if not run_analysis:
    # 欢迎引导界面
    st.info("💡 **操作指引**：在左侧输入 A 股代码并点击“启动扫描”。系统将动用多名 AI 专家并行审计财务、技术、政策及博弈面。")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("10Y 国债收益率", f"{engine._get_macro_rates()['macro_rate']}%")
    c2.metric("LPR (1年期)", f"{engine._get_macro_rates()['lpr_1y']}%")
    c3.metric("北向资金 (今日)", engine._get_north_flow()['north_flow']['today'])
    st.stop()

# ---------- 执行研判逻辑 ----------
if run_analysis:
    with st.status("🔍 龙眼正在透视市场数据...", expanded=True) as status:
        
        # 1. 抓取数据
        st.write("📡 调取东方财富与 AKShare 实时接口...")
        context = engine.get_full_context(ticker_input, ticker_input)
        
        # 校验数据是否读取成功
        price_info = context.get("price_info", {})
        if price_info.get("current_price") == "N/A":
            st.error("⚠️ 股价读取失败，请检查代码是否正确或东财接口是否波动。")
            st.stop()
            
        st.write(f"✅ 成功获取 **{context.get('company_name')}** 数据 (现价: ¥{price_info.get('current_price')})")

        # 2. 并行调用专家 Agent (Skills 模式)
        st.write(f"🧠 驱动 {len(active_skills)} 位专家进行并行审计...")
        reports = []
        tab_names = [os.path.basename(sf).split("_")[-1].replace(".md", "") for sf in active_skills]
        
        with ThreadPoolExecutor(max_workers=len(active_skills)) as executor:
            future_to_skill = {executor.submit(orchestrator.consult_skill, sf, ticker_input, context): sf for sf in active_skills}
            for future in as_completed(future_to_skill):
                reports.append(future.result())
        
        # 3. CIO 综合裁决
        st.write("👑 首席投资官 (CIO) 正在合成终审意见...")
        final_verdict = orchestrator.synthesize_cio(ticker_input, reports, context)
        
        status.update(label="✅ 研判完成", state="complete", expanded=False)

    # ---------- 渲染研判结果 ----------
    # 顶部指标卡
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("公司名称", context.get("company_name"))
    m2.metric("当前价格", f"¥{price_info.get('current_price')}", f"{price_info.get('change_pct')}%")
    m3.metric("行业板块", context.get("industry", "N/A"))
    m4.metric("龙眼评分", orchestrator.extract_score(final_verdict))

    st.divider()

    # CIO 裁决区
    st.subheader("👑 CIO 综合裁决 (虎之眼内核)")
    st.markdown(f'<div class="verdict-box">{final_verdict}</div>', unsafe_allow_html=True)

    # 导出模块
    st.divider()
    if st.download_button(
        label="📥 下载 PDF 深度研判报告",
        data=orchestrator.create_pdf(ticker_input, context.get("company_name"), final_verdict, reports, tab_names, context),
        file_name=f"LongEye_Report_{ticker_input}.pdf",
        mime="application/pdf"
    ):
        st.success("报告准备就绪！")

    # 专项专家 Tab 页
    st.subheader("📋 专项审计详情")
    tabs = st.tabs(tab_names)
    for i, tab in enumerate(tabs):
        with tab:
            st.markdown(reports[i])