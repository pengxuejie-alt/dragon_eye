import streamlit as st
import glob
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.engine import AShareDataEngine
from core.agents import LongEyeOrchestrator

st.set_page_config(page_title="🐉 龙眼深度研判 Pro", layout="wide")

@st.cache_resource
def init_system():
    # 注入虎之眼品牌要求 [cite: 1]
    return AShareDataEngine(), LongEyeOrchestrator(api_key=st.secrets["GEMINI_KEY"])

engine, orchestrator = init_system()

with st.sidebar:
    st.markdown("### 🐉 龙眼专家团 (虎之眼内核)")
    # 动态扫描 01-06 所有专家
    skill_paths = sorted(glob.glob("skills/0[1-6]*.md"))
    active_skills = [s for s in skill_paths if st.checkbox(f"✅ {os.path.basename(s)[3:-3]}", value=True)]
    
    ticker = st.text_input("请输入股票代码", value="600519")
    run_btn = st.button("启动深度审计", type="primary")

st.markdown('<h1 style="color: #CC0000;">🐉 龙眼 A股深度研判系统</h1>', unsafe_allow_html=True)

if run_btn:
    with st.status("正在进行多 Agent 并行穿透...", expanded=True) as status:
        # 获取包含中债 10Y 利率和筹码数据的上下文
        ctx = engine.get_full_context(ticker, ticker)
        
        # 并行审计
        reports = []
        with ThreadPoolExecutor(max_workers=len(active_skills)) as exe:
            futures = {exe.submit(orchestrator.consult_skill, s, ticker, ctx): s for s in active_skills}
            for f in as_completed(futures):
                reports.append(f.result())

        # CIO 综合裁决 (包含 00 号协议逻辑)
        final_verdict = orchestrator.synthesize_cio(ticker, reports, ctx)
        status.update(label="研判报告合成完毕 ✅", state="complete")

    # 展示结果
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("标的", ctx.get("company_name"))
    c2.metric("最新现价", f"¥{ctx['price_info']['current_price']}", f"{ctx['price_info']['change_pct']}%")
    c3.metric("获利盘估算", ctx['chip_analysis']['profit_ratio'])
    c4.metric("中债 10Y", f"{ctx['macro_rate']}%")

    st.divider()
    st.subheader("👑 CIO 综合裁决 (基于虎之眼内核)")
    st.markdown(f'<div style="border-left: 5px solid red; padding-left: 15px;">{final_verdict}</div>', unsafe_allow_html=True)
    
    # 分项 Tab
    tabs = st.tabs([os.path.basename(s)[3:-3] for s in active_skills])
    for i, tab in enumerate(tabs):
        with tab: st.markdown(reports[i])