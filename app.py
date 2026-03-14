"""
龙眼深度研判系统 v1.0
Long Eye - A-Share Multi-Agent Research Platform
Architecture inspired by Anthropic Financial Services Plugins
(skills / commands / hooks / mcp layering pattern)
"""

import streamlit as st
import glob
import os
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.engine import AShareDataEngine
from core.agents import LongEyeOrchestrator

st.set_page_config(
    page_title="🐉 龙眼深度研判 Pro",
    page_icon="🐉",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- 自定义 CSS ----------
st.markdown("""
<style>
    /* 龙眼主题：赤金配色 */
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
    .metric-card {
        background: #0f0f0f;
        border: 1px solid #333;
        border-radius: 8px;
        padding: 0.8rem;
        text-align: center;
    }
    .red-up { color: #FF4444; font-weight: bold; }
    .green-down { color: #00CC66; font-weight: bold; }
    .score-badge {
        display: inline-block;
        background: #CC0000;
        color: #FFD700;
        border-radius: 50px;
        padding: 4px 16px;
        font-size: 1.1rem;
        font-weight: bold;
    }
    .agent-tag {
        display: inline-block;
        background: #1a1a2e;
        border: 1px solid #4a4a8a;
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 0.75rem;
        color: #8888ff;
        margin-right: 4px;
    }
</style>
""", unsafe_allow_html=True)

# ---------- 初始化核心组件 ----------
@st.cache_resource
def init_engine():
    return AShareDataEngine()

@st.cache_resource
def init_orchestrator():
    return LongEyeOrchestrator(api_key=st.secrets["GEMINI_KEY"])

engine = init_engine()
orchestrator = init_orchestrator()

# ---------- 侧边栏 ----------
with st.sidebar:
    st.markdown('<p class="main-title">🐉 龙眼研判</p>', unsafe_allow_html=True)
    st.caption("A股多智能体深度审计系统")
    st.divider()

    ticker = st.text_input(
        "📌 股票代码 / 名称",
        value="600519",
        help="输入A股代码（如 600519）或公司简称（如 贵州茅台）",
        placeholder="600519 或 贵州茅台"
    ).strip()

    market = st.selectbox("交易所", ["自动识别", "上交所 (SH)", "深交所 (SZ)", "北交所 (BJ)"])

    st.divider()
    st.subheader("🧠 研判专家配置")

    # 动态加载 skill 文件
    skill_files = sorted(glob.glob("skills/*.md"))
    skill_display = {}
    for sf in skill_files:
        name = os.path.basename(sf).replace(".md", "")
        label = name.split("_", 1)[-1] if "_" in name else name
        skill_display[sf] = st.checkbox(f"✅ {label.upper()}", value=True)

    active_skills = [sf for sf, enabled in skill_display.items() if enabled]

    st.divider()
    run_analysis = st.button(
        "🚀 启动龙眼扫描",
        use_container_width=True,
        type="primary",
        disabled=not ticker
    )

    st.caption("⚠️ 本系统仅供学习研究，不构成投资建议")

# ---------- 主内容区 ----------
st.markdown('<h1 class="main-title">🐉 龙眼 A股深度研判系统</h1>', unsafe_allow_html=True)
st.caption("基于 Anthropic Financial Services Plugin 架构 · 多智能体并行审计 · A股专属研判逻辑")

if not run_analysis:
    # 欢迎页
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.info("📊 **价值审计**\n财务健康度·盈利质量·安全边际")
    with col2:
        st.info("📈 **技术量化**\n均线系统·量价结构·筹码分布")
    with col3:
        st.info("🏛️ **政策宏观**\n产业政策·北向资金·货币环境")
    with col4:
        st.info("🎭 **资金博弈**\n龙虎榜·机构动向·游资策略")

    st.markdown("---")
    st.markdown("""
    ### 🔧 系统架构
    龙眼采用 **Anthropic Financial Services Plugin** 的多层架构设计：
    - **Skills 层**：每个专家 Agent 对应独立 `.md` 协议文件，可热插拔
    - **Engine 层**：统一数据接入（AKShare · 同花顺 · 东方财富）
    - **Orchestrator 层**：CIO 综合裁决，输出鹰眼评分 + 操盘建议
    - **Output 层**：支持 PDF 导出 + 多 Tab 专项报告
    """)
    st.stop()

# ---------- 分析执行 ----------
if run_analysis:
    header_placeholder = st.empty()

    # 解析代码
    raw_ticker = ticker
    if market == "上交所 (SH)" and not ticker.endswith(".SH"):
        ticker_full = ticker.lstrip("0") and ticker + ".SH"
    elif market == "深交所 (SZ)" and not ticker.endswith(".SZ"):
        ticker_full = ticker + ".SZ"
    else:
        # 自动识别
        if ticker.startswith("6"):
            ticker_full = ticker + ".SH"
        elif ticker.startswith(("0", "3")):
            ticker_full = ticker + ".SZ"
        elif ticker.startswith(("4", "8")):
            ticker_full = ticker + ".BJ"
        else:
            ticker_full = ticker  # 可能是名称

    def render_header(status_text: str, score: str = "—", signal: str = ""):
        with header_placeholder.container():
            st.subheader(f"🐉 {raw_ticker} 实时研判状态")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("当前标的", raw_ticker, ticker_full)
            c2.metric("龙眼评分", score)
            c3.metric("AI状态", status_text)
            c4.metric("研判信号", signal if signal else "研判中...")

    render_header("数据抓取中...")

    with st.status(f"🔍 正在执行 {raw_ticker} 龙眼深度审计...", expanded=True) as status:

        # ── STEP 1: 数据抓取 ──
        st.write("📡 接入 AKShare / 东方财富数据源...")
        context = engine.get_full_context(ticker_full, raw_ticker)

        price_info = context.get("price_info", {})
        current_price = price_info.get("current_price", "N/A")
        change_pct = price_info.get("change_pct", 0)
        company_name = context.get("company_name", raw_ticker)
        macro_rate = context.get("macro_rate", "N/A")
        industry = context.get("industry", "N/A")
        market_cap = context.get("market_cap", "N/A")

        render_header("并行专家研判中...", score="计算中")
        st.write(f"✅ 数据就绪 | 价格: ¥{current_price} | 行业: {industry}")

        # ── STEP 2: 专家并行研判 (Anthropic plugin skills 模式) ──
        st.write(f"🧠 启动 {len(active_skills)} 位专家并行审计...")
        tab_names = []
        for sf in active_skills:
            name = os.path.basename(sf).replace(".md", "")
            label = name.split("_", 1)[-1] if "_" in name else name
            tab_names.append(label.upper())

        reports = {}
        with ThreadPoolExecutor(max_workers=max(len(active_skills), 1)) as exe:
            future_to_skill = {
                exe.submit(orchestrator.consult_skill, sf, raw_ticker, context): sf
                for sf in active_skills
            }
            for future in as_completed(future_to_skill):
                sf = future_to_skill[future]
                name = os.path.basename(sf).replace(".md", "")
                label = name.split("_", 1)[-1] if "_" in name else name
                try:
                    reports[sf] = future.result()
                    st.write(f"  ✅ {label.upper()} 专家研判完成")
                except Exception as e:
                    reports[sf] = f"⚠️ 研判出错: {str(e)}"
                    st.write(f"  ❌ {label.upper()} 出错: {e}")

        ordered_reports = [reports.get(sf, "无报告") for sf in active_skills]

        # ── STEP 3: CIO 合成裁决 ──
        st.write("👑 CIO 综合裁决生成中...")
        final_verdict = orchestrator.synthesize_cio(raw_ticker, ordered_reports, context)

        # 从结论中提取评分和信号
        score_val = orchestrator.extract_score(final_verdict)
        signal_val = orchestrator.extract_signal(final_verdict)

        render_header("研判完成 ✅", score=score_val, signal=signal_val)
        status.update(label="✅ 龙眼深度报告生成成功", state="complete", expanded=False)

    # ── 结果渲染 ──
    st.divider()

    # 顶部指标栏
    m1, m2, m3, m4, m5 = st.columns(5)
    change_color = "red-up" if change_pct >= 0 else "green-down"
    m1.metric("📛 公司", company_name)
    m2.metric("💰 现价", f"¥{current_price}", f"{change_pct:+.2f}%")
    m3.metric("🏭 行业", industry)
    m4.metric("📊 市值", market_cap)
    m5.metric("🏦 LPR/10Y", f"{macro_rate}%")

    st.divider()

    # CIO 裁决
    st.subheader("👑 首席投资官 (CIO) 综合裁决")
    st.markdown(f'<div class="verdict-box">{final_verdict}</div>', unsafe_allow_html=True)

    st.divider()

    # PDF 导出
    col_pdf, col_ts = st.columns([1, 3])
    with col_pdf:
        if os.path.exists("MSYH.TTC"):
            try:
                pdf_data = orchestrator.create_pdf(
                    raw_ticker, company_name, final_verdict, ordered_reports, tab_names, context
                )
                st.download_button(
                    "📥 下载 PDF 研判报告",
                    data=bytes(pdf_data),
                    file_name=f"LongEye_{raw_ticker}_{datetime.date.today()}.pdf",
                    use_container_width=True,
                )
            except Exception as e:
                st.warning(f"PDF 渲染失败: {e}")
        else:
            st.info("💡 放置 MSYH.TTC 字体文件到根目录以启用 PDF 导出")
    with col_ts:
        st.caption(f"🕐 报告生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 数据来源: AKShare · 东财 · FRED")

    # 分项 Tabs
    if tab_names:
        tabs = st.tabs([f"📋 {n}" for n in tab_names])
        for i, tab in enumerate(tabs):
            with tab:
                if i < len(ordered_reports):
                    st.markdown(ordered_reports[i])
