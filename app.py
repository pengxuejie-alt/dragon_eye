"""
龙眼深度研判系统 (LongEye)
架构参考: Anthropic Financial Services Plugin
"""

import streamlit as st
import glob
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

# 🚨 确保子目录导入正确
from core.engine import AShareDataEngine
from core.agents import LongEyeOrchestrator

st.set_page_config(page_title="🐉 龙眼深度研判", layout="wide")

# 初始化 Session State
if "ticker_input" not in st.session_state:
    st.session_state["ticker_input"] = "600519"

# --- 样式渲染 ---
st.markdown("""
<style>
    .main-title { background: linear-gradient(135deg, #8B0000 0%, #FF8C00 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 2.2rem; font-weight: 900; }
    .verdict-box { background-color: #0d0d0d; border-left: 5px solid #CC0000; padding: 1.5rem; color: #FFD700; border-radius: 4px; }
</style>
""", unsafe_allow_html=True)

# 缓存组件初始化
@st.cache_resource
def load_orchestrator():
    return AShareDataEngine(), LongEyeOrchestrator(api_key=st.secrets["GEMINI_KEY"])

engine, orchestrator = load_orchestrator()

# --- 侧边栏 ---
with st.sidebar:
    st.markdown('<p class="main-title">🐉 龙眼研判</p>', unsafe_allow_html=True)
    st.caption("虎之眼内核 · A股深度审计")
    
    # 输入框绑定 session_state
    ticker_val = st.text_input("📌 股票代码 (6位数字)", value=st.session_state["ticker_input"])
    
    st.divider()
    st.subheader("🧠 专家审计配置")
    skill_files = sorted(glob.glob("skills/*.md"))
    active_skills = [sf for sf in skill_files if st.checkbox(f"✅ {os.path.basename(sf).split('_')[-1].replace('.md','')}", value=True)]
    
    run_btn = st.button("🚀 启动深度扫描", use_container_width=True, type="primary")

    # 指南针风格异动选股池
    st.divider()
    st.subheader("🔥 异动榜 (指南针模式)")
    if st.button("刷新当日涨幅榜"):
        try:
            import akshare as ak
            df_spot = ak.stock_zh_a_spot_em()
            top_list = df_spot[~df_spot['名称'].str.contains("ST")].sort_values("涨跌幅", ascending=False).head(5)
            for _, row in top_list.iterrows():
                # 点击后直接修改状态并刷新
                if st.button(f"🔎 {row['名称']} (+{row['涨跌幅']}%)", key=f"s_{row['代码']}"):
                    st.session_state["ticker_input"] = row['代码']
                    st.rerun()
        except: st.error("接口限流，请稍后再试")

# --- 主界面逻辑 ---
st.markdown('<h1 class="main-title">🐉 龙眼 A股深度研判系统</h1>', unsafe_allow_html=True)

if not run_btn and st.session_state["ticker_input"] == "600519":
    st.info("请输入 A 股代码（如 002460 赣锋锂业）或从左侧异动榜点选，点击按钮开始分析。")
    # 首页展示基础宏观数据
    c1, c2, c3 = st.columns(3)
    macro = engine._get_macro_rates()
    c1.metric("10Y国债收益率", f"{macro['macro_rate']}%")
    c2.metric("LPR (1年期)", f"{macro['lpr_1y']}%")
    c3.metric("北向资金 (今日)", engine._get_north_flow()['north_flow']['today'])
    st.stop()

# --- 核心分析流程 ---
if run_btn or st.session_state["ticker_input"] != "600519":
    target_ticker = ticker_val if run_btn else st.session_state["ticker_input"]
    
    with st.status(f"正在透视 {target_ticker} 底层数据...", expanded=True) as status:
        # 1. 引擎抓取
        context = engine.get_full_context(target_ticker, target_ticker)
        price = context.get("price_info", {})
        
        if price.get("current_price") == "N/A":
            st.error("⚠️ 股价解析异常。请确认代码正确（如 002460）或东财接口未被拦截。")
            st.stop()

        st.write(f"📡 接入成功：{context.get('company_name')} | 现价：¥{price.get('current_price')}")

        # 2. 专家并行分析
        reports = []
        tab_names = [os.path.basename(sf).split("_")[-1].replace(".md","") for sf in active_skills]
        with ThreadPoolExecutor(max_workers=len(active_skills)) as executor:
            futures = {executor.submit(orchestrator.consult_skill, sf, target_ticker, context): sf for sf in active_skills}
            for future in as_completed(futures):
                reports.append(future.result())

        # 3. CIO 合成综合意见
        final_verdict = orchestrator.synthesize_cio(target_ticker, reports, context)
        status.update(label="研判报告生成完毕 ✅", state="complete")

    # --- 结果呈现 ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("标的名称", context.get("company_name"))
    c2.metric("当前现价", f"¥{price.get('current_price')}", f"{price.get('change_pct')}%")
    c3.metric("龙眼评分", orchestrator.extract_score(final_verdict))
    c4.metric("所属行业", context.get("industry", "N/A"))

    st.divider()
    st.subheader("👑 首席投资官 (CIO) 综合裁决")
    st.markdown(f'<div class="verdict-box">{final_verdict}</div>', unsafe_allow_html=True)

    st.divider()
    tabs = st.tabs([f"📋 {n} 审计报告" for n in tab_names])
    for i, tab in enumerate(tabs):
        with tab: st.markdown(reports[i])