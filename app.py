import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import os
from core.engine import fetch_stock_info
from core.agents import LongEyeOrchestrator

# --- 页面配置 ---
# 移除了 theme="dark"，让界面恢复为默认明亮风格
st.set_page_config(page_title="龙眼 - A股智能研判终端", page_icon="🐉", layout="wide")
st.title("🐉 龙眼 — A股智能研判终端")

# 初始化 Orchestrator
orchestrator = LongEyeOrchestrator()

# --- 主界面 ---
col1, col2 = st.columns([1, 1])
with col1:
    st.header("📊 个股研判")
    ticker_input = st.text_input("请输入股票代码", placeholder="例如：000001, 600519", help="支持A股上海和深圳市场股票代码")

with col2:
    st.header("🔭 选股雷达")
    # 读取技能文件列表
    SKILLS_DIR = "skills"
    if os.path.exists(SKILLS_DIR):
        skill_files = [f.replace('.txt', '') for f in os.listdir(SKILLS_DIR) if f.endswith('.txt')]
    else:
        skill_files = ["技能文件夹不存在"]

    selected_skills = st.multiselect(
        "选择审计专家配置",
        options=skill_files,
        default=skill_files,
        help="多选，可同时启用多个审计专家"
    )

# --- 分析按钮 ---
if st.button("🚀 开始龙眼研判", type="primary"):
    if not ticker_input:
        st.error("请输入股票代码！")
    else:
        ticker = ticker_input.strip()
        # 为了兼容性，去掉可能的 .SH 或 .SZ 后缀
        clean_ticker = ticker.split('.')[0]
        if len(clean_ticker) != 6 or not clean_ticker.isdigit():
            st.error("请输入正确的6位股票代码！")
        else:
            with st.spinner('正在启动虎之眼金融内核 v12.0 (百炼版)...'):
                # 获取股票基础信息
                stock_data = fetch_stock_info(clean_ticker)
                if not stock_data:
                    st.error(f"未能获取到 {clean_ticker} 的数据，请检查代码是否正确。")
                else:
                    st.success("✅ 研判完毕")
                    
                    # --- 展示基础信息 ---
                    st.subheader(f"标的名字: {stock_data.get('股票名称', '未知')}")
                    current_price = stock_data.get('最新价', 'N/A')
                    st.metric(label="当前价格", value=f"¥{current_price}")
                    
                    # --- 调用专家进行分析 ---
                    expert_reports = []
                    context_summary = f"{stock_data.get('股票名称', '未知')}({clean_ticker}): 最新价¥{current_price}, 涨跌幅{stock_data.get('涨跌幅', 'N/A')}%, 行业:{stock_data.get('行业', 'N/A')}, 概念:{stock_data.get('概念', 'N/A')}"

                    for skill_name in selected_skills:
                        skill_file = f"{skill_name}.txt"
                        skill_path = os.path.join(SKILLS_DIR, skill_file)
                        
                        if os.path.exists(skill_path):
                            with st.spinner(f'正在调用 **{skill_name}** 专家进行深度审计...'):
                                report = orchestrator.consult_skill(skill_path, clean_ticker, context_summary)
                                expert_reports.append(report)
                                
                                # 为每个专家报告创建一个可折叠的区域
                                with st.expander(f"🔍 {skill_name} 专家报告"):
                                    st.markdown(report)
                        else:
                            st.warning(f"⚠️ 专家配置文件 {skill_file} 未找到。")

                    # --- CIO 综合裁决 ---
                    if expert_reports:
                        st.info("🧠 AI 正在深度思考，整合专家意见并撰写综合报告...")
                        synthesis_report = orchestrator.synthesize_cio(clean_ticker, expert_reports, context_summary)
                        
                        st.subheader("👑 CIO 综合裁决")
                        st.markdown(synthesis_report)

                        # --- 提取并展示雷达图 ---
                        scores = orchestrator.extract_scores(synthesis_report)
                        if scores and len(scores) == 6:
                            # 定义维度名称
                            t_names = ['价值', '技术', '行业', '资金', '成长', '风控']
                            
                            # 创建雷达图
                            fig = go.Figure()
                            
                            # 添加数据
                            fig.add_trace(go.Scatterpolar(
                                r=scores,
                                theta=t_names,
                                fill='toself',
                                name='评分'
                            ))

                            # 更新布局，修复 gridshape 错误
                            fig.update_layout(
                                polar=dict(
                                    radialaxis=dict(
                                        visible=True,
                                        range=[0, 100] # 设置径向轴范围
                                    ),
                                    # 将 gridshape 从 'polygon' 改为 'circular'
                                    gridshape='circular' 
                                ),
                                showlegend=False,
                                title=f"{stock_data.get('股票名称', clean_ticker)} 综合能力雷达图"
                            )

                            st.subheader("📊 虎之眼量化维度")
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.warning("⚠️ 未能从CIO报告中解析出有效评分，无法生成雷达图。")