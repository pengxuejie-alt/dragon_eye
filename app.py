"""
龙眼 A股智能研判终端 v4.0
修复：
  [L1] 控件全部移入侧边栏，主区域专用于结果展示
  [L2] skills 目录改为扫描 .md 文件（原代码扫描 .txt）
  [L3] 启动按钮放在侧边栏，不再悬浮在列块外面
  [L4] 用 session_state 缓存结果，交互后不丢失
  [L5] 并发专家调用 + 顺序对齐（reports_map 模式）
  [L6] 雷达图分数从 agents.extract_scores() 提取，不再硬编码
"""

import streamlit as st
import glob, os, re, datetime
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.engine import fetch_stock_info, AShareDataEngine
from core.agents import LongEyeOrchestrator

# ── 页面配置 ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="龙眼 — A股智能研判终端",
    page_icon="🐉",
    layout="wide",
)

# ── CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .verdict-box {
      background: #0d0d0d; color: #FFD700;
      padding: 22px; border-left: 5px solid #CC0000;
      border-radius: 10px; line-height: 1.75;
  }
  .expert-header {
      color: #888; font-size: 0.78rem; font-style: italic;
      border-bottom: 1px solid #222; padding-bottom: 4px; margin-bottom: 8px;
  }
  .info-bar {
      background: #111; border-left: 4px solid #CC0000;
      border-radius: 6px; padding: 10px 16px; margin-bottom: 12px;
  }
</style>
""", unsafe_allow_html=True)

# ── Session State ────────────────────────────────────────────────────
for k, v in [
    ("report_data", None),
    ("active_ticker", ""),
]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── 系统初始化 ────────────────────────────────────────────────────────
@st.cache_resource
def load_system():
    engine = AShareDataEngine()
    orch   = LongEyeOrchestrator()
    return engine, orch

engine, orchestrator = load_system()

# ── 工具函数 ─────────────────────────────────────────────────────────

def _fmt_chg(val):
    try:
        return f"{float(val):+.2f}%"
    except Exception:
        return "—"

def render_radar(scores: list, labels: list) -> go.Figure:
    cats = labels[:6] if len(labels) >= 6 else (labels + ["—"] * 6)[:6]
    s6   = (scores + [50] * 6)[:6]
    fig  = go.Figure(go.Scatterpolar(
        r=s6 + [s6[0]],
        theta=cats + [cats[0]],
        fill="toself",
        fillcolor="rgba(204,0,0,0.35)",
        line=dict(color="#CC0000", width=2),
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], color="#777"),
            gridshape="circular",
            bgcolor="#0d0d0d",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        margin=dict(l=40, r=40, t=30, b=30),
        height=360,
    )
    return fig

# ════════════════════════════════════════════════════════════════════
#  侧边栏（[L1] 所有控件移到这里）
# ════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(
        '<p style="font-size:1.6rem;font-weight:900;color:#CC0000;margin:0;">🐉 龙眼研判</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p style="color:#FF8C00;font-size:0.78rem;font-style:italic;margin:0;">'
        '虎之眼 Eye of Tiger 金融内核</p>',
        unsafe_allow_html=True,
    )
    st.divider()

    # ── 股票代码输入 ─────────────────────────────────────────────────
    st.subheader("📊 个股研判")
    ticker_input = st.text_input(
        "股票代码",
        value=st.session_state["active_ticker"],
        placeholder="如 600519 / 000001",
        label_visibility="collapsed",
    )

    # ── [L2] 扫描 .md 技能文件 ──────────────────────────────────────
    st.subheader("🧠 审计专家团队")
    SKILLS_DIR  = "skills"
    skill_files = sorted(glob.glob(os.path.join(SKILLS_DIR, "0[1-6]*.md")))

    if not skill_files:
        st.warning(f"未找到 skills/ 目录下的 .md 专家文件")
        skill_files = []

    skill_labels  = [os.path.basename(f)[3:-3] for f in skill_files]  # 去掉 "01_" 前缀和 ".md"
    active_skills = [
        skill_files[i]
        for i, label in enumerate(skill_labels)
        if st.checkbox(label, value=True, key=f"sk_{skill_files[i]}")
    ]

    st.divider()

    # ── [L3] 启动按钮在侧边栏 ────────────────────────────────────────
    run_btn = st.button(
        "🚀 启动穿透审计",
        type="primary",
        use_container_width=True,
        disabled=not ticker_input.strip(),
    )
    st.caption("⚠️ 仅供学习研究，不构成投资建议")

# ════════════════════════════════════════════════════════════════════
#  主区域头部
# ════════════════════════════════════════════════════════════════════
st.markdown(
    '<h1 style="color:#CC0000;margin-bottom:4px;">🐉 龙眼 — A股智能研判终端</h1>',
    unsafe_allow_html=True,
)
st.markdown(
    '<p style="color:#888;font-size:0.85rem;margin-top:0;">'
    '虎之眼 (Eye of Tiger) 金融内核 · 阿里云百炼大模型驱动 · '
    '多智能体并行研判</p>',
    unsafe_allow_html=True,
)

# 当前标的提示
active = ticker_input.strip()
if active:
    st.info(f"📍 当前标的：**{active}** — 在左侧配置专家后点击「启动穿透审计」")
else:
    st.info("👈 请在左侧输入股票代码，选择专家团队，点击启动审计")

# ════════════════════════════════════════════════════════════════════
#  审计执行
# ════════════════════════════════════════════════════════════════════
if run_btn and active:
    # 代码格式校验
    code = re.sub(r"\D", "", active)[:6]
    if len(code) != 6:
        st.error("请输入正确的 6 位股票代码！")
        st.stop()

    with st.status(f"🔍 虎之眼正在穿透审计 {code}...", expanded=True) as status:

        # 1. 获取股票数据
        st.write("📡 接入行情数据源...")
        stock_data = fetch_stock_info(code)
        if not stock_data or stock_data.get("最新价", "N/A") == "N/A":
            st.error(f"⚠️ 无法获取 {code} 的行情数据，请检查代码或稍后重试。")
            st.stop()

        company  = stock_data.get("股票名称", code)
        price    = stock_data.get("最新价",   "N/A")
        chg      = stock_data.get("涨跌幅",   "N/A")
        industry = stock_data.get("行业",     "N/A")
        profit_r = stock_data.get("获利比例 (CYQ)", "N/A")

        context_summary = (
            f"{company}({code}): 最新价¥{price}, "
            f"涨跌幅{_fmt_chg(chg)}, 行业:{industry}, "
            f"获利盘:{profit_r}"
        )
        st.write(f"✅ 行情就绪 | {company} ¥{price} ({_fmt_chg(chg)})")

        # 2. [L5] 并行专家研判（dict 收集，顺序对齐）
        t_names     = [os.path.basename(s)[3:-3] for s in active_skills]
        reports_map = {}

        st.write(f"🧠 启动 {len(active_skills)} 位专家并行审计...")
        if active_skills:
            with ThreadPoolExecutor(max_workers=max(len(active_skills), 1)) as exe:
                futs = {
                    exe.submit(orchestrator.consult_skill, s, code, context_summary): s
                    for s in active_skills
                }
                for fut in as_completed(futs):
                    sk    = futs[fut]
                    label = os.path.basename(sk)[3:-3]
                    try:
                        reports_map[sk] = fut.result()
                        st.write(f"  ✅ {label} 完成")
                    except Exception as e:
                        reports_map[sk] = f"⚠️ 专家 {label} 出错: {e}"
                        st.write(f"  ❌ {label} 出错")

        # 严格按提交顺序排列，与 t_names 一一对应
        reports = [reports_map.get(s, "⚠️ 无报告") for s in active_skills]

        # 3. CIO 综合裁决
        st.write("👑 CIO 正在合成综合裁决...")
        verdict = orchestrator.synthesize_cio(code, reports, context_summary)

        # 4. [L6] 从 CIO 报告提取真实分数
        scores = orchestrator.extract_scores(verdict)

        status.update(label="✅ 研判完毕", state="complete", expanded=False)

    # [L4] 缓存结果到 session_state
    st.session_state["active_ticker"] = code
    st.session_state["report_data"]   = {
        "code":       code,
        "company":    company,
        "price":      price,
        "chg":        chg,
        "industry":   industry,
        "profit_r":   profit_r,
        "stock_data": stock_data,
        "reports":    reports,
        "verdict":    verdict,
        "t_names":    t_names,
        "scores":     scores,
        "ts":         datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

# ════════════════════════════════════════════════════════════════════
#  结果渲染（[L4] 从 session_state 读取，不随交互消失）
# ════════════════════════════════════════════════════════════════════
data = st.session_state.get("report_data")
if data:
    st.divider()

    # ── 顶部指标行 ──────────────────────────────────────────────────
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("公司",    data["company"])
    m2.metric("价格",    f"¥{data['price']}", _fmt_chg(data["chg"]))
    m3.metric("行业",    data["industry"])
    m4.metric("获利盘",  data["profit_r"])
    m5.metric("研判时间", data["ts"][11:16])   # 只显示时分

    # ── CIO 裁决 + 雷达图 ───────────────────────────────────────────
    left, right = st.columns([3, 2])
    with left:
        st.subheader("👑 CIO 综合裁决")
        st.markdown(
            f'<div class="verdict-box">{data["verdict"]}</div>',
            unsafe_allow_html=True,
        )
    with right:
        st.subheader("📊 虎之眼维度评分")
        labels = data["t_names"][:6] if len(data["t_names"]) >= 6 else (
            ["价值", "技术", "行业", "资金", "成长", "风控"]
        )
        st.plotly_chart(
            render_radar(data["scores"], labels),
            use_container_width=True,
        )

    # ── 专家分项报告 Tabs ────────────────────────────────────────────
    st.divider()
    if data["t_names"] and data["reports"]:
        tabs = st.tabs(data["t_names"])
        for i, tab in enumerate(tabs):
            with tab:
                st.markdown(
                    f'<p class="expert-header">'
                    f'🐯 虎之眼 · {data["t_names"][i]} 专项报告 · {data["ts"]}</p>',
                    unsafe_allow_html=True,
                )
                st.markdown(data["reports"][i])

elif not run_btn:
    # 落地欢迎页（无历史结果时显示）
    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.info("**📊 个股研判**\n\n左侧输入6位股票代码，选择专家团队，启动全维度审计")
    c2.info("**🧠 多专家并行**\n\n价值/技术/宏观/资金/成长/风控六大维度同步分析")
    c3.info("**📊 雷达图评分**\n\nCIO综合裁决 + 六维度量化评分可视化")
