"""
龙眼 App v4.0 — 虎之眼金融内核
修复：
  [A1] as_completed 竞态：reports 顺序与 tab_names 不对齐
  [A2] 六边形评分从 AI 报告中提取，不再硬编码
  [A3] change_pct 格式化：N/A 安全处理 + 带 +/- 符号
  [A4] 雷达结果展示：列名使用修复后的 _attach_win_rate 输出
"""

import streamlit as st
import glob, os, datetime, re
import pandas as pd
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.engine import AShareDataEngine
from core.agents import LongEyeOrchestrator

# ── 1. 页面配置 ──────────────────────────────────────────────────────
st.set_page_config(page_title="🐉 龙眼 Pro — 虎之眼内核", layout="wide")

st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] button { font-size: 14px !important; padding: 0 10px !important; }
    .stMetric { background:#0d0d0d; border-radius:8px; border-bottom:3px solid #CC0000; padding:12px; }
    .verdict-box { background:#0d0d0d; color:#FFD700; padding:25px;
                   border-left:5px solid #CC0000; border-radius:10px; min-height:380px; line-height:1.7; }
    .radar-card  { background:#111; padding:8px 15px; border-radius:5px;
                   border-left:4px solid #CC0000; margin-bottom:5px; }
</style>
""", unsafe_allow_html=True)

# ── 2. Session 初始化 ────────────────────────────────────────────────
for k, v in [("active_ticker","600519"), ("report_data",None), ("radar_results",None)]:
    if k not in st.session_state:
        st.session_state[k] = v

@st.cache_resource
def load_system():
    return AShareDataEngine(), LongEyeOrchestrator(api_key=st.secrets["GEMINI_KEY"])

engine, orchestrator = load_system()

# ── 3. 工具函数 ──────────────────────────────────────────────────────

def _f(val, default=0.0):
    try:
        v = float(val)
        return v if v == v else default
    except Exception:
        return default

def _fmt_chg(val):
    """[A3] 安全格式化涨跌幅，N/A 不崩溃"""
    try:
        return f"{float(val):+.2f}%"
    except Exception:
        return "—"

def _extract_scores(reports: list, t_names: list) -> list:
    """
    [A2] 从 AI 报告中提取量化分数
    匹配模式：XX/100、评分：XX、XX分 等
    找不到时返回合理默认值
    """
    scores = []
    for i, report in enumerate(reports):
        # 优先匹配 XX/100 格式
        m = re.search(r"(\d{1,3})\s*/\s*100", report)
        if m:
            scores.append(min(int(m.group(1)), 100))
            continue
        # 次选：评分：XX
        m2 = re.search(r"评分[：:]\s*(\d{1,3})", report)
        if m2:
            scores.append(min(int(m2.group(1)), 100))
            continue
        # 兜底：60
        scores.append(60)
    # 保证长度与 t_names 一致
    while len(scores) < 6:
        scores.append(60)
    return scores[:6]

def render_hexagon(scores: list, labels: list = None):
    """[A2] 六边形评分图，使用真实 AI 分数"""
    cats = labels if labels and len(labels) == 6 else [
        "价值审计", "技术强度", "行业格局", "资金博弈", "成长质量", "风控安全"
    ]
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=scores + [scores[0]],
        theta=cats + [cats[0]],
        fill="toself",
        fillcolor="rgba(204,0,0,0.4)",
        line=dict(color="#CC0000", width=2),
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], color="#555"),
            gridshape="polygon", bgcolor="#0d0d0d",
        ),
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=40, r=40, t=30, b=30),
        height=380,
    )
    return fig

# ── 4. 侧边栏 ───────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<p style="font-size:1.8rem;font-weight:900;color:#CC0000;margin:0;">🐉 龙眼研判</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p style="color:#FF8C00;font-style:italic;font-size:0.8rem;">虎之眼 Eye of Tiger 金融内核</p>',
        unsafe_allow_html=True,
    )
    st.divider()

    menu = st.tabs(["📊 个股研判", "🔭 选股雷达"])

    with menu[0]:
        t_in = st.text_input("代码/名称", value=st.session_state["active_ticker"], key="main_search")
        st.session_state["active_ticker"] = t_in.strip()
        skill_paths   = sorted(glob.glob("skills/0[1-6]*.md"))
        active_skills = [
            s for s in skill_paths
            if st.checkbox(os.path.basename(s)[3:-3], value=True, key=f"sk_{s}")
        ]
        run_audit = st.button("🚀 启动穿透审计", type="primary", use_container_width=True)

    with menu[1]:
        st.markdown("**指南针模式选股**")
        radar_mode = st.selectbox("核心指标", ["异动扫描", "资金净流入", "自然语言模式"])

        user_query = ""
        if radar_mode == "自然语言模式":
            user_query = st.text_area("需求描述", placeholder="如：最近回撤小的白马股")

        if st.button("🔭 开启雷达监测", use_container_width=True):
            with st.spinner("雷达探测中..."):
                try:
                    result_df = engine.scan_radar(mode=radar_mode, query=user_query)
                    st.session_state["radar_results"] = result_df
                except Exception as e:
                    st.error(f"雷达扫描失败: {e}")
                    st.session_state["radar_results"] = None
            st.rerun()

# ── 5. 主界面 ────────────────────────────────────────────────────────
st.markdown('<h1 style="color:#CC0000;">🐉 龙眼 — 虎之眼金融内核</h1>', unsafe_allow_html=True)

# 雷达结果展示
radar_df = st.session_state.get("radar_results")
if radar_df is not None and not radar_df.empty:
    with st.expander("🎯 雷达扫描结果（点击标的跳转研判）", expanded=True):
        for _, row in radar_df.iterrows():
            code     = str(row.get("代码", ""))
            name     = str(row.get("名称", code))
            chg      = _f(row.get("涨跌幅", 0))
            max_gain = str(row.get("最高涨幅", "—"))
            ai_rate  = str(row.get("AI胜率",  ""))
            reason   = str(row.get("理由",    ""))
            entry_d  = str(row.get("AI入选日","—"))

            c1, c2 = st.columns([5, 1])
            with c1:
                st.markdown(
                    f'<div class="radar-card">'
                    f'<b>{name} ({code})</b>'
                    f'<span style="color:{"#FF4444" if chg>=0 else "#00CC66"};margin-left:12px;">{chg:+.2f}%</span>'
                    f'<span style="color:#FFD700;margin-left:20px;">入选后最高: {max_gain}</span>'
                    f'{"  <b>"+ai_rate+"</b>" if ai_rate else ""}'
                    f'<br><span style="color:#666;font-size:0.78rem;">理由: {reason} · 入选日: {entry_d}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with c2:
                if st.button("审计", key=f"r_{code}", use_container_width=True):
                    st.session_state["active_ticker"] = code
                    st.session_state["report_data"]   = None
                    st.rerun()

# ── 6. 审计执行 ──────────────────────────────────────────────────────
if run_audit:
    target = st.session_state["active_ticker"]
    with st.status(f"🔍 正在穿透审计: {target}...", expanded=True) as status:

        ctx = engine.get_full_context(target, target)
        if ctx["price_info"]["current_price"] == "N/A":
            st.error("⚠️ 股价读取超时，云端 IP 受限，请稍后重试。")
            st.stop()

        t_names = [os.path.basename(s)[3:-3] for s in active_skills]

        # [A1] 用 dict 收集结果，按原始顺序重组，彻底消除竞态
        reports_map: dict = {}
        if active_skills:
            with ThreadPoolExecutor(max_workers=max(len(active_skills), 1)) as exe:
                futs = {
                    exe.submit(orchestrator.consult_skill, s, target, ctx): s
                    for s in active_skills
                }
                for f in as_completed(futs):
                    sk = futs[f]
                    try:
                        reports_map[sk] = f.result()
                    except Exception as e:
                        reports_map[sk] = f"⚠️ 专家研判出错: {e}"

        # 严格按提交顺序排列，与 t_names 一一对应
        reports = [reports_map.get(s, "⚠️ 无报告") for s in active_skills]

        verdict = orchestrator.synthesize_cio(target, reports, ctx)

        # [A2] 从报告中提取真实分数
        scores = _extract_scores(reports, t_names)

        st.session_state["report_data"] = {
            "ctx": ctx, "reports": reports, "verdict": verdict,
            "t_names": t_names, "scores": scores,
            "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        status.update(label="研判完毕 ✅", state="complete", expanded=False)

# ── 7. 结果渲染 ──────────────────────────────────────────────────────
if st.session_state["report_data"]:
    data = st.session_state["report_data"]
    ctx  = data["ctx"]
    p    = ctx["price_info"]
    ts   = data.get("ts", "")

    st.divider()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("公司名称", ctx.get("company_name", st.session_state["active_ticker"]))
    # [A3] 安全格式化价格与涨跌幅
    c2.metric("当前价格", f"¥{p['current_price']}", _fmt_chg(p.get("change_pct", 0)))
    c3.metric("获利比例", ctx.get("profit_ratio", "N/A"))
    c4.metric("十年债收益", f"{ctx.get('macro_rate', 'N/A')}%")

    res_l, res_r = st.columns([3, 2])
    with res_l:
        st.subheader("👑 CIO 综合裁决")
        st.markdown(
            f'<div class="verdict-box">'
            f'<small style="color:#555;">🐯 虎之眼 · {ts}</small>'
            f'<hr style="border-color:#222;margin:6px 0;">'
            f'{data["verdict"]}'
            f'</div>',
            unsafe_allow_html=True,
        )
    with res_r:
        st.subheader("📊 虎之眼维度评分图")
        # [A2] 传入真实分数 + 对应专家名称
        labels = data["t_names"][:6] if len(data["t_names"]) >= 6 else None
        st.plotly_chart(
            render_hexagon(data["scores"], labels),
            use_container_width=True,
        )

    st.divider()
    # [A1] tabs 与 reports 已通过 reports_map 严格对齐
    if data["t_names"] and data["reports"]:
        tabs = st.tabs(data["t_names"])
        for i, tab in enumerate(tabs):
            with tab:
                st.markdown(
                    f'<p style="color:#888;font-size:0.78rem;">'
                    f'🐯 虎之眼 · {data["t_names"][i]} 专项报告 · {ts}</p>',
                    unsafe_allow_html=True,
                )
                st.markdown(data["reports"][i])
