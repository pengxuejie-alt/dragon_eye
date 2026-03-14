"""
龙眼深度研判系统 (LongEye)
架构参考: Anthropic Financial Services Plugin
核心: 虎之眼 (Eye of Tiger) 金融审计内核
"""

import streamlit as st
import glob
import os
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# 从 core 子目录导入
from core.engine import AShareDataEngine
from core.agents import LongEyeOrchestrator

st.set_page_config(page_title="🐉 龙眼深度研判", layout="wide")

# 初始化 Session State 存储选股代码
if "ticker_input" not in st.session_state:
    st.session_state["ticker_input"] = "600519"

# --- 自定义样式 ---
st.markdown("""
<style>
    .main-title { background: linear-gradient(135deg, #8B0000 0%, #FF8C00 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 2.2rem; font-weight: 900; }
    .verdict-box { background-color: #1a1a1a; border-left: 5px solid #CC0000; padding: 1.5rem; color: #FFD700; border-radius: 4px; }
</style>
""", unsafe_allow_html=True)

engine = AShareDataEngine()
orchestrator = LongEyeOrchestrator(api_key=st.secrets["GEMINI_KEY"])

# --- 侧边栏 ---
with st.sidebar:
    st.markdown('<p class="main-title">🐉 龙眼研判</p>', unsafe_allow_html=True)
    st.caption("基于虎之眼内核 · A股多智能体审计")
    
    ticker_box = st.text_input("📌 股票代码", value=st.session_state["ticker_input"], key="manual_ticker")
    
    st.divider()
    st.subheader("🧠 专家审计配置")
    skill_files = sorted(glob.glob("skills/*.md"))
    active_skills = [sf for sf in skill_files if st.checkbox(f"✅ {os.path.basename(sf).split('_')[-1].replace('.md','')}", value=True)]
    
    run_btn = st.button("🚀 启动深度扫描", use_container_width=True, type="primary")

    # 指南针风格选股池
    st.divider()
    st.subheader("🔥 龙眼选股（指南针异动模式）")
    if st.button("刷新涨幅榜"):
        try:
            import akshare as ak
            df_spot = ak.stock_zh_a_spot_em()
            top_list = df_spot.sort_values("涨跌幅", ascending=False).head(5)
            for _, row in top_list.iterrows():
                if st.button(f"🔎 {row['名称']} (+{row['涨跌幅']}%)", key=f"s_{row['代码']}"):
                    st.session_state["ticker_input"] = row['代码']
                    st.rerun()
        except: st.error("接口繁忙")

# --- 主界面 ---
st.markdown('<h1 class="main-title">🐉 龙眼 A股深度研判系统</h1>', unsafe_allow_html=True)

if not run_btn:
    st.info("请输入代码或从左侧选股池选择标的，开启 6 维度专家并行审计。")
    st.stop()

# --- 核心分析流程 ---
with st.status("正在穿透 A 股底层数据...", expanded=True) as status:
    # 1. 引擎取数
    context = engine.get_full_context(ticker_box, ticker_box)
    price = context.get("price_info", {})
    
    if price.get("current_price") == "N/A":
        st.error("⚠️ 股价解析异常。请确认代码正确（如 002460）或东财接口未被拦截。")
        st.stop()

    st.write(f"📡 接入成功：{context.get('company_name')} | 现价：¥{price.get('current_price')}")

    # 2. 专家并行分析
    reports = []
    tab_names = [os.path.basename(sf).split("_")[-1].replace(".md","") for sf in active_skills]
    with ThreadPoolExecutor(max_workers=len(active_skills)) as executor:
        futures = {executor.submit(orchestrator.consult_skill, sf, ticker_box, context): sf for sf in active_skills}
        for future in as_completed(futures):
            reports.append(future.result())

    # 3. CIO 合成
    final_verdict = orchestrator.synthesize_cio(ticker_box, reports, context)
    status.update(label="研判完成 ✅", state="complete")

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
tabs = st.tabs([f"📋 {n}" for n in tab_names])
for i, tab in enumerate(tabs):
    with tab: st.markdown(reports[i])