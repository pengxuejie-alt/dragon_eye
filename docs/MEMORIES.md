🐉 龙眼 (LongEye) 系统长期记忆文件 v1.0
一、 核心架构设定 (Immutable Architecture)
侧边栏固定结构：必须严格保持以下顺序，不得因功能增减而乱序：

📊 研判 (Stock Research)：个股全维度审计入口。

🔭 雷达 (Radar)：全市场量化异动扫描。

🧠 AI 选股 (Natural Language)：小白语义化选股入口。

UI 渲染约束：

Tab 文字显示：侧边栏 Tab 标签必须精简（如使用“🧠 AI 选股”而非“自然语言选股”），并配合 CSS 注入修复文字溢出。

六边形评分图：主界面 CIO 裁决旁必须保留基于 Plotly 的六边形能力雷达图，涵盖：价值、技术、行业、资金、成长、风控六大维度。

二、 股价读取与数据安全 (Data Engine)
单点穿透技术 (Fix for Cloud)：由于 Streamlit Cloud 海外 IP 限制，严禁在主循环中调用全量快照接口。

路由逻辑：优先使用 http://qt.gtimg.cn/q=s_ (腾讯) 进行单代码抓取，响应时间需控制在 500ms 内。

代码转换：中文名称转代码必须通过 http://smartbox.gtimg.cn/ (腾讯搜索) 极速完成，彻底修复“赣锋锂业”等中文搜索失效的 Bug。

字段对齐：必须从接口中强制提取 company_name 字段并同步至全局上下文，解决研判报告中只显示代码数字的问题。

三、 交互逻辑与状态管理 (State Management)
点击重定向修复：选股雷达与 AI 选股池中的标的点击后，必须通过 st.session_state 修改 active_ticker 并立即执行 st.rerun()，否则会导致点击无反应。

审计报告持久化：审计结果（包含 6 个维度的分项报告）必须存入 st.session_state["report_data"]，防止 Streamlit 在二次渲染时清空右侧审计内容。