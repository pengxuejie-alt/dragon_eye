# ... 顶部导入与 CSS 保持不变 ...

# ── 5. 主界面渲染 ──
st.markdown('<h1 style="color:#CC0000;">🐉 龙眼 — 虎之眼金融内核</h1>', unsafe_allow_html=True)

# [修复] 选股雷达结果展示：通过 session_state 强制跳转研判
if st.session_state["radar_results"] is not None:
    with st.expander("🎯 指南针异动雷达 (点击标的启动穿透)", expanded=True):
        for _, row in st.session_state["radar_results"].iterrows():
            c1, c2 = st.columns([5, 1])
            with c1:
                st.markdown(f"""<div style="background:#111;padding:8px;border-radius:5px;border-left:4px solid #CC0000;margin-bottom:5px;">
                    <b>{row['名称']} ({row['代码']})</b> <span style="color:#FFD700;margin-left:20px;">最高涨幅: {row['最高涨幅']}</span></div>""", unsafe_allow_html=True)
            with c2:
                # 核心修复：按钮点击后修改 ID 并触发 rerun
                if st.button("研判", key=f"r_{row['代码']}", use_container_width=True):
                    st.session_state["active_ticker"] = row['代码']
                    # 关键：清除旧报告缓存，强制重新审计
                    st.session_state["report_data"] = None 
                    st.rerun()

# 审计逻辑执行
if run_audit:
    target = st.session_state["active_ticker"]
    with st.status(f"🔍 虎之眼正在穿透审计: {target}...", expanded=True) as status:
        ctx = engine.get_full_context(target, target)
        
        # 并行审计并发处理
        reports, t_names = [], [os.path.basename(s)[3:-3] for s in active_skills]
        with ThreadPoolExecutor(max_workers=len(active_skills)) as exe:
            futs = {exe.submit(orchestrator.consult_skill, s, target, ctx): s for s in active_skills}
            for f in as_completed(futs): reports.append(f.result())
            
        verdict = orchestrator.synthesize_cio(target, reports, ctx)
        
        # [亮点] 提取 AI 真实评分驱动六边形图
        # 逻辑：从 CIO 裁决文本中寻找 [Score: 85, 70...] 格式
        scores = ctx["auto_scores"] # 默认分
        score_match = re.search(r"评分[:：]\s*\[(.*?)\]", verdict)
        if score_match:
            try:
                scores = [int(s.strip()) for s in score_match.group(1).split(',')]
            except: pass

        st.session_state["report_data"] = {"ctx": ctx, "reports": reports, "verdict": verdict, "t_names": t_names, "scores": scores}
        status.update(label="研判完毕 ✅", state="complete")

# ── 6. 最终成果展示：六边形能力图 ──
if st.session_state["report_data"]:
    # ... 此处渲染 plotly_chart(render_hexagon(data["scores"])) ...