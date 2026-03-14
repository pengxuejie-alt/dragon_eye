"""
龙眼多智能体编排器 (LongEyeOrchestrator)
架构参考: Anthropic financial-services-plugins
- consult_skill()  → 对标 skills/*.md 的专家 Agent 调用
- synthesize_cio() → 对标 equity-research/commands/earnings.md 的 CIO 合成
- create_pdf()     → 对标 DOCX/PDF output 生成层
"""

import re
import os
import datetime

import google.generativeai as genai

try:
    from fpdf import FPDF
    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False


# ─── A股专属系统提示词（注入到每个 Agent）──────────────────────────────
A_SHARE_BASE_CONTEXT = """
你是专注于A股市场的资深研究员。在分析时必须遵守以下A股特有规则：

【监管与制度】
- A股实行T+1交易制度（当日买入次日才能卖出）
- 涨跌停板：主板±10%，科创板/创业板±20%，ST股±5%
- 北向资金（沪深港通）是重要的外资风向标
- 定期报告披露义务：季报、半年报、年报

【A股市场特性】
- 散户占比高（约70%），情绪波动影响显著
- 政策市特征强：监管政策、产业政策直接影响估值
- 流动性分层明显：大盘蓝筹 vs 中小票
- 特殊制度：涨跌停、ST/*ST、退市整理板

【估值框架】
- DCF折现率参考：中国10年期国债收益率（约2.3%）+ 风险溢价
- A股估值参考：全A PE中位数、行业PE分位数
- 重要性排序：ROE质量 > 营收增速 > 绝对估值

分析时请用简体中文，数据单位使用人民币（¥/亿元/万元）。
"""


class LongEyeOrchestrator:
    """
    龙眼编排器
    实现 Anthropic Financial Plugin 的"sub-agents + synthesis"模式：
    1. 各领域 Agent 独立执行（skill 文件驱动）
    2. CIO Agent 合成最终裁决
    """

    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        # 使用最新可用的 Gemini Flash 模型
        self.model = genai.GenerativeModel(
            "gemini-2.0-flash",
            system_instruction=A_SHARE_BASE_CONTEXT,
        )

    def consult_skill(self, skill_path: str, ticker: str, context: dict) -> str:
        """
        调用单个专家 Agent（对标 Anthropic plugin 的 SKILL.md 触发逻辑）
        
        flow:
        1. 读取 skill 协议文件（知识层）
        2. 构建包含上下文的 prompt
        3. 调用 Gemini，返回结构化报告
        """
        with open(skill_path, "r", encoding="utf-8") as f:
            skill_instruction = f.read()

        # 格式化上下文数据（避免传递大量无关字段）
        price_info = context.get("price_info", {})
        fundamentals = context.get("fundamentals", {})
        north_flow = context.get("north_flow", {})

        context_summary = f"""
## 标的基本信息
- 股票代码：{context.get('raw_ticker', 'N/A')}（{context.get('symbol', 'N/A')}）
- 公司名称：{context.get('company_name', 'N/A')}
- 所属行业：{context.get('industry', 'N/A')}
- 总市值：{context.get('market_cap', 'N/A')}

## 实时行情
- 当前价格：¥{price_info.get('current_price', 'N/A')}
- 今日涨跌：{price_info.get('change_pct', 0):+.2f}%
- 市盈率(TTM)：{price_info.get('pe_ttm', 'N/A')}
- 市净率：{price_info.get('pb', 'N/A')}

## 基本面指标
- ROE：{fundamentals.get('roe', 'N/A')}
- 毛利率：{fundamentals.get('gross_margin', 'N/A')}
- 净利率：{fundamentals.get('net_margin', 'N/A')}
- 资产负债率：{fundamentals.get('debt_ratio', 'N/A')}

## 宏观环境
- 中国10年期国债收益率：{context.get('macro_rate', 'N/A')}%
- LPR(1年期)：{context.get('lpr_1y', 'N/A')}%
- LPR(5年期)：{context.get('lpr_5y', 'N/A')}%

## 北向资金（沪深港通）
- 今日净流向：{north_flow.get('today', 'N/A')}
- 近5日累计：{north_flow.get('5day', 'N/A')}
- 近20日累计：{north_flow.get('20day', 'N/A')}
- 方向：{north_flow.get('direction', 'N/A')}
"""

        prompt = f"""
# 研判任务
标的：**{ticker}**

# 专业协议（请严格遵守以下研判框架）
{skill_instruction}

# 数据上下文
{context_summary}

# 输出要求
请基于以上协议和数据，输出完整的专项研判报告。
报告必须：
1. 包含明确的量化结论（分数、区间、百分比等）
2. 指出A股特有风险因素
3. 结尾给出1-3条明确的操盘建议
"""
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"## ⚠️ 专家研判异常\n\n错误信息：{str(e)}\n\n请检查 API KEY 配置或网络连接。"

    def synthesize_cio(self, ticker: str, reports: list, context: dict) -> str:
        """
        CIO 综合裁决（对标 Anthropic equity-research plugin 的 /earnings synthesis 命令）
        汇总所有专家报告，输出统一的鹰眼评分 + 操盘建议
        """
        reports_text = ""
        for i, r in enumerate(reports, 1):
            reports_text += f"\n\n---\n### 专家报告 #{i}\n{r}"

        company_name = context.get("company_name", ticker)
        price = context.get("price_info", {}).get("current_price", "N/A")
        industry = context.get("industry", "N/A")

        prompt = f"""
你是首席投资官（CIO），需要基于多位专家的研判报告，对A股标的 **{ticker}（{company_name}）** 给出最终综合裁决。

## 基本信息
- 当前价格：¥{price}
- 所属行业：{industry}

## 各专家研判汇总
{reports_text}

---

## 输出格式（必须严格遵守）

### 🐉 龙眼综合评分：[XX/100]

**评级**：[强烈买入 / 买入 / 中性持有 / 减持 / 卖出]

**核心逻辑**（3点）：
1. ...
2. ...
3. ...

**主要风险**（2点）：
1. ...
2. ...

**操盘建议**：
- 🎯 目标价区间：¥XX - ¥XX（6个月）
- 📍 建议买入区间：¥XX - ¥XX
- 🛑 止损位：¥XX（跌破XX%止损）
- ⏰ 催化剂：[近期关注事件，如财报日/政策窗口]

**A股特别提示**：
[结合T+1制度、涨跌停、板块轮动等A股特性的操作提醒]
"""
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"CIO 裁决生成失败：{str(e)}"

    def extract_score(self, verdict_text: str) -> str:
        """从 CIO 裁决文本中提取龙眼评分"""
        match = re.search(r"(\d{1,3})/100", verdict_text)
        if match:
            score = int(match.group(1))
            if score >= 80:
                return f"🔴 {score}/100"
            elif score >= 60:
                return f"🟡 {score}/100"
            else:
                return f"🟢 {score}/100"
        return "—/100"

    def extract_signal(self, verdict_text: str) -> str:
        """从 CIO 裁决文本中提取评级信号"""
        signals = ["强烈买入", "买入", "中性持有", "减持", "卖出"]
        for sig in signals:
            if sig in verdict_text:
                emoji_map = {
                    "强烈买入": "🔴 强烈买入",
                    "买入": "🟠 买入",
                    "中性持有": "🟡 中性持有",
                    "减持": "🔵 减持",
                    "卖出": "🟢 卖出",
                }
                return emoji_map.get(sig, sig)
        return "—"


    def extract_drive_type(self, verdict_text: str) -> str:
        for t in ["价值驱动", "博弈驱动", "政策陷阱"]:
            if t in verdict_text: return t
        return "—"
    def create_pdf(
        self,
        ticker: str,
        company_name: str,
        final_verdict: str,
        reports: list,
        tab_names: list,
        context: dict,
    ) -> bytes:
        """
        生成 PDF 研判报告
        对标 Anthropic financial plugin 的 DOCX/PDF output 层
        """
        if not HAS_FPDF:
            raise ImportError("fpdf2 未安装，请 pip install fpdf2")

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_margins(20, 20, 20)

        # 字体加载
        font_path = "MSYH.TTC"
        if os.path.exists(font_path):
            pdf.add_font("MSYH", "", font_path)
            font_name = "MSYH"
        else:
            font_name = "Arial"

        def set_font(size, style=""):
            pdf.set_font(font_name, style=style, size=size)

        # ── 封面页 ──
        pdf.add_page()
        set_font(28)
        pdf.ln(20)
        pdf.cell(0, 20, txt="🐉 龙眼深度研判报告", ln=True, align="C")
        set_font(16)
        pdf.cell(0, 12, txt=f"{ticker}  {company_name}", ln=True, align="C")
        set_font(11)
        pdf.cell(0, 10, txt=f"生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True, align="C")
        pdf.cell(0, 8, txt=f"所属行业：{context.get('industry', 'N/A')} | 市值：{context.get('market_cap', 'N/A')}", ln=True, align="C")
        pdf.ln(10)

        # 价格信息
        p = context.get("price_info", {})
        pdf.set_fill_color(200, 0, 0)
        pdf.set_text_color(255, 215, 0)
        set_font(12)
        pdf.cell(0, 12, txt=f"  当前价格：¥{p.get('current_price', 'N/A')}   今日涨跌：{p.get('change_pct', 0):+.2f}%   PE(TTM)：{p.get('pe_ttm', 'N/A')}", ln=True, fill=True)
        pdf.set_text_color(0, 0, 0)

        # ── CIO 裁决 ──
        pdf.add_page()
        set_font(16)
        pdf.cell(0, 12, txt="一、首席投资官综合裁决", ln=True)
        set_font(10)
        clean_verdict = final_verdict.replace("**", "").replace("##", "").replace("#", "").replace("*", "")
        pdf.multi_cell(0, 7, txt=clean_verdict)

        # ── 宏观数据摘要 ──
        pdf.add_page()
        set_font(14)
        pdf.cell(0, 10, txt="二、宏观环境概要", ln=True)
        set_font(10)
        macro_text = (
            f"中国10年期国债收益率：{context.get('macro_rate', 'N/A')}%\n"
            f"LPR(1年期)：{context.get('lpr_1y', 'N/A')}%\n"
            f"LPR(5年期)：{context.get('lpr_5y', 'N/A')}%\n"
            f"北向资金今日：{context.get('north_flow', {}).get('today', 'N/A')}\n"
            f"北向资金近5日：{context.get('north_flow', {}).get('5day', 'N/A')}\n"
            f"北向资金近20日：{context.get('north_flow', {}).get('20day', 'N/A')}\n"
        )
        pdf.multi_cell(0, 7, txt=macro_text)

        # ── 分项专家报告 ──
        for i, (name, report) in enumerate(zip(tab_names, reports)):
            pdf.add_page()
            set_font(14)
            pdf.cell(0, 10, txt=f"三-{i+1}、{name} 专项研判", ln=True)
            set_font(9)
            clean = report.replace("**", "").replace("##", "").replace("#", "").replace("*", "")
            pdf.multi_cell(0, 6, txt=clean)

        # ── 免责声明 ──
        pdf.add_page()
        set_font(10)
        disclaimer = (
            "免责声明\n\n"
            "本报告由龙眼AI研判系统自动生成，仅供学习研究参考，不构成任何投资建议。"
            "A股市场存在较高风险，投资需谨慎。过往表现不代表未来收益。"
            "请结合自身风险承受能力，在专业投资顾问指导下做出投资决策。\n\n"
            "数据来源：AKShare、东方财富、FRED等公开数据平台。\n"
            "AI模型：Google Gemini（仅用于文本分析，不构成算法交易系统）。\n\n"
            "龙眼深度研判系统 © 2025"
        )
        pdf.multi_cell(0, 7, txt=disclaimer)

        return pdf.output()
