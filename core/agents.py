"""
龙眼多智能体编排器 v2.0 — 虎之眼 (Eye of Tiger) 内核
======================================================
升级：
1. 每份报告页眉强制注入品牌声明
2. context_summary 透传 macro_rate / profit_ratio / atr / turnover
3. 读取 00_系统编排.md 作为 CIO 核心指令（虎之眼逻辑）
4. 一票否决机制在 synthesize_cio 中落地
"""

import re
import os
import datetime
import glob

import google.generativeai as genai

try:
    from fpdf import FPDF
    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False

# ─── A股 + 虎之眼基础提示词 ───────────────────────────────────────────────
A_SHARE_BASE_CONTEXT = """
你是专注于A股市场的资深研究员，运行在"虎之眼 (Eye of Tiger) 金融内核"上。

【监管与制度】
- A股实行T+1交易制度（当日买入次日才能卖出）
- 涨跌停板：主板±10%，科创板/创业板±20%，ST股±5%
- 北向资金（沪深港通）是重要的外资风向标

【A股市场特性】
- 散户占比高（约70%），情绪波动影响显著
- 政策市特征强：监管政策、产业政策直接影响估值
- 流动性分层明显：大盘蓝筹 vs 中小票
- 指南针 CYQ 获利盘模型是筹码审计的重要参考

【估值框架】
- DCF折现率参考：中国10年期国债收益率 + 风险溢价（4-6%）
- A股估值参考：全A PE中位数、行业PE分位数

【品牌要求】
每份输出报告必须在开头标注：
> 🐉 本研判由龙眼系统执行，基于虎之眼 (Eye of Tiger) 金融内核

分析时请用简体中文，数据单位使用人民币（¥/亿元）。
"""


def _load_orchestrator_instruction() -> str:
    """读取 00_系统编排.md 作为 CIO 总指挥协议"""
    paths = ["skills/00_系统编排.md", "00_系统编排.md"]
    for p in paths:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return f.read()
    return ""  # 兜底


class LongEyeOrchestrator:
    """
    龙眼多智能体编排器 v2.0
    ─────────────────────────────────────────────────────
    - consult_skill()  → 专家 Agent（由 01-06 Skill 驱动）
    - synthesize_cio() → CIO 裁决（由 00_系统编排.md 驱动）
    - create_pdf()     → PDF 导出层
    """

    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            "gemini-2.0-flash",
            system_instruction=A_SHARE_BASE_CONTEXT,
        )
        self._orch_instruction = _load_orchestrator_instruction()

    def _build_context_summary(self, ticker: str, context: dict) -> str:
        """
        构建标准化数据摘要，确保 macro_rate + profit_ratio 等关键字段透传
        """
        pi   = context.get("price_info", {})
        fund = context.get("fundamentals", {})
        nf   = context.get("north_flow", {})
        chip = context.get("chip_analysis", {})
        atr  = context.get("atr_analysis", {})
        turn = context.get("turnover_analysis", {})

        return f"""
## 📌 标的基本信息
- 股票代码：{context.get('raw_ticker', 'N/A')}
- 公司名称：{context.get('company_name', 'N/A')}
- 所属行业：{context.get('industry', 'N/A')}
- 总市值：{context.get('market_cap', 'N/A')}

## 📊 实时行情
| 指标 | 数值 |
|------|------|
| 当前价格 | ¥{pi.get('current_price', 'N/A')} |
| 今日涨跌 | {pi.get('change_pct', 0):+.2f}% |
| 市盈率(TTM) | {pi.get('pe_ttm', 'N/A')} |
| 市净率 | {pi.get('pb', 'N/A')} |

## 🏦 宏观环境（透传至 03_政策宏观）
| 指标 | 数值 |
|------|------|
| 中国10年期国债收益率 | **{context.get('macro_rate', 'N/A')}%** |
| LPR(1年期) | {context.get('lpr_1y', 'N/A')}% |
| LPR(5年期) | {context.get('lpr_5y', 'N/A')}% |
| 北向资金今日 | {nf.get('today', 'N/A')} ({nf.get('direction', 'N/A')}) |
| 北向资金近5日 | {nf.get('5day', 'N/A')} |
| 北向资金近20日 | {nf.get('20day', 'N/A')} |

## 💎 指南针CYQ筹码模型（透传至 04_资金博弈）
| 指标 | 数值 |
|------|------|
| 获利盘比例 | **{context.get('profit_ratio', 'N/A')}** |
| 60日VWAP主力成本 | ¥{chip.get('vwap_60', 'N/A')} |
| 20日VWAP短期成本 | ¥{chip.get('vwap_20', 'N/A')} |
| 筹码密集度 | {context.get('chip_density', 'N/A')} |
| 锁仓信号 | {chip.get('chip_lock_signal', 'N/A')} |
| 价格>60日VWAP | {'✅ 是' if chip.get('above_vwap60') else '❌ 否'} |

## 📈 换手率承接分析（透传至 04_资金博弈）
| 指标 | 数值 |
|------|------|
| 近5日均换手率 | {turn.get('avg_turnover_5d', 'N/A')} |
| 近20日均换手率 | {turn.get('avg_turnover_20d', 'N/A')} |
| 近5日价格变动 | {turn.get('price_5d_chg', 'N/A')} |
| 换手信号 | **{turn.get('turnover_signal', 'N/A')}** |

## ⚡ ATR历史波动率（透传至 06_风险控制）
| 指标 | 数值 |
|------|------|
| ATR(14) | {atr.get('atr14', 'N/A')} |
| ATR占股价比 | {atr.get('atr_pct', 'N/A')} |
| 历史分位数 | {atr.get('atr_percentile', 'N/A')} |
| 波动率判断 | **{atr.get('volatility_label', 'N/A')}** |

## 📋 基本面指标（透传至 01_价值审计）
| 指标 | 数值 |
|------|------|
| ROE | {fund.get('roe', 'N/A')} |
| 毛利率 | {fund.get('gross_margin', 'N/A')} |
| 净利率 | {fund.get('net_margin', 'N/A')} |
| 资产负债率 | {fund.get('debt_ratio', 'N/A')} |
"""

    # ══════════════════════════════════════════════════════════════════
    # 专家 Agent 调用
    # ══════════════════════════════════════════════════════════════════

    def consult_skill(self, skill_path: str, ticker: str, context: dict) -> str:
        """
        调用单个专家 Agent
        品牌声明强制在开头注入
        """
        with open(skill_path, "r", encoding="utf-8") as f:
            skill_instruction = f.read()

        context_summary = self._build_context_summary(ticker, context)
        brand = context.get("brand", "基于虎之眼 (Eye of Tiger) 金融内核")

        prompt = f"""
> 🐉 本研判由龙眼系统执行，{brand}

# 研判任务
标的：**{ticker}（{context.get('company_name', ticker)}）**

# 专业协议（严格遵守以下研判框架）
{skill_instruction}

# 实时数据上下文
{context_summary}

# 输出格式要求
1. 报告首行必须包含品牌声明："本研判由龙眼系统执行，基于虎之眼 (Eye of Tiger) 金融内核"
2. 给出明确的量化结论（分数/区间/百分比）
3. 指出A股特有风险因素
4. 结尾给出1-3条操盘建议
"""
        try:
            return self.model.generate_content(prompt).text
        except Exception as e:
            return f"> 🐉 本研判由龙眼系统执行，基于虎之眼 (Eye of Tiger) 金融内核\n\n## ⚠️ 专家研判异常\n\n{str(e)}"

    # ══════════════════════════════════════════════════════════════════
    # CIO 综合裁决（融合 00_系统编排.md 逻辑）
    # ══════════════════════════════════════════════════════════════════

    def synthesize_cio(self, ticker: str, reports: list, context: dict) -> str:
        """
        CIO 综合裁决
        - 融入 00_系统编排.md 的虎之眼过滤逻辑
        - 一票否决机制（风控高危 / 筹码大规模派发）
        - 强制判定：价值驱动 / 博弈驱动 / 政策陷阱
        """
        orch = self._orch_instruction
        company = context.get("company_name", ticker)
        price   = context.get("price_info", {}).get("current_price", "N/A")
        industry = context.get("industry", "N/A")
        chip_signal = context.get("chip_analysis", {}).get("chip_lock_signal", "N/A")
        turn_signal = context.get("turnover_analysis", {}).get("turnover_signal", "N/A")
        atr_label   = context.get("atr_analysis", {}).get("volatility_label", "N/A")

        reports_text = "\n\n---\n".join(
            f"### 专家报告 #{i+1}\n{r}" for i, r in enumerate(reports)
        )

        prompt = f"""
> 🐉 本研判由龙眼系统执行，基于虎之眼 (Eye of Tiger) 金融内核

# 首席投资官综合裁决任务
标的：**{ticker}（{company}）** | 当前价格：¥{price} | 行业：{industry}

## 系统编排指令（虎之眼内核）
{orch}

## 关键数据快照
- 筹码锁仓信号：{chip_signal}
- 换手率承接信号：{turn_signal}
- ATR波动率：{atr_label}
- 获利盘比例：{context.get('profit_ratio', 'N/A')}

## 各专家研判汇总
{reports_text}

---

## 必须严格遵守的输出格式

> 🐉 本研判由龙眼系统执行，基于虎之眼 (Eye of Tiger) 金融内核

### 🐉 龙眼综合评分：[XX/100]

**驱动类型判定**：[价值驱动 / 博弈驱动 / 政策陷阱]

**评级**：[强烈买入 / 买入 / 中性持有 / 减持 / 卖出]

> ⚠️ 如有一票否决触发，必须在此处明确说明触发原因和降级幅度

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
- 🛑 止损位：¥XX（跌破此位止损）
- ⏰ 近期催化剂：[财报日/政策窗口/解禁日期]

**A股特别提示（T+1 & 涨跌停）**：
[基于T+1制度和涨跌停机制的具体操作注意事项]
"""
        try:
            return self.model.generate_content(prompt).text
        except Exception as e:
            return f"> 🐉 本研判由龙眼系统执行，基于虎之眼 (Eye of Tiger) 金融内核\n\nCIO 裁决生成失败：{str(e)}"

    # ══════════════════════════════════════════════════════════════════
    # 工具方法
    # ══════════════════════════════════════════════════════════════════

    def extract_score(self, verdict_text: str) -> str:
        match = re.search(r"(\d{1,3})/100", verdict_text)
        if match:
            s = int(match.group(1))
            return f"🔴 {s}" if s >= 80 else f"🟡 {s}" if s >= 60 else f"🟢 {s}"
        return "—"

    def extract_signal(self, verdict_text: str) -> str:
        for sig, label in [
            ("强烈买入", "🔴 强烈买入"), ("买入", "🟠 买入"),
            ("中性持有", "🟡 持有"),    ("减持", "🔵 减持"),
            ("卖出", "🟢 卖出"),
        ]:
            if sig in verdict_text:
                return label
        return "—"

    def extract_drive_type(self, verdict_text: str) -> str:
        for t in ["价值驱动", "博弈驱动", "政策陷阱"]:
            if t in verdict_text:
                return t
        return "—"

    # ══════════════════════════════════════════════════════════════════
    # PDF 导出
    # ══════════════════════════════════════════════════════════════════

    def create_pdf(self, ticker, company_name, final_verdict, reports, tab_names, context):
        if not HAS_FPDF:
            raise ImportError("请安装 fpdf2")

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_margins(20, 20, 20)

        font_path = "MSYH.TTC"
        if os.path.exists(font_path):
            pdf.add_font("MSYH", "", font_path)
            fn = "MSYH"
        else:
            fn = "Arial"

        def sf(size):
            pdf.set_font(fn, size=size)

        # 封面
        pdf.add_page()
        sf(24)
        pdf.ln(15)
        pdf.cell(0, 18, "龙眼深度研判报告", ln=True, align="C")
        sf(14)
        pdf.cell(0, 10, f"{ticker}  {company_name}", ln=True, align="C")
        sf(10)
        pdf.cell(0, 8, f"生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True, align="C")
        pdf.cell(0, 7, "基于虎之眼 (Eye of Tiger) 金融内核", ln=True, align="C")
        pdf.ln(8)
        pi = context.get("price_info", {})
        pdf.set_fill_color(180, 0, 0)
        pdf.set_text_color(255, 215, 0)
        sf(11)
        pdf.cell(0, 11,
            f"  价格：¥{pi.get('current_price','N/A')}  "
            f"涨跌：{pi.get('change_pct',0):+.2f}%  "
            f"获利盘：{context.get('profit_ratio','N/A')}  "
            f"中债10Y：{context.get('macro_rate','N/A')}%",
            ln=True, fill=True)
        pdf.set_text_color(0, 0, 0)

        # CIO 裁决
        pdf.add_page()
        sf(14); pdf.cell(0, 10, "一、CIO 综合裁决", ln=True)
        sf(9); pdf.multi_cell(0, 6, final_verdict.replace("**","").replace("#","").replace("*",""))

        # 宏观
        pdf.add_page()
        sf(13); pdf.cell(0, 9, "二、宏观与筹码概要", ln=True)
        sf(9)
        pdf.multi_cell(0, 6, (
            f"中债10Y：{context.get('macro_rate','N/A')}%\n"
            f"LPR 1Y：{context.get('lpr_1y','N/A')}%  LPR 5Y：{context.get('lpr_5y','N/A')}%\n"
            f"获利盘：{context.get('profit_ratio','N/A')}  主力成本(60日VWAP)：¥{context.get('chip_analysis',{}).get('vwap_60','N/A')}\n"
            f"筹码密集度：{context.get('chip_density','N/A')}\n"
            f"换手信号：{context.get('turnover_analysis',{}).get('turnover_signal','N/A')}\n"
            f"ATR波动率：{context.get('atr_analysis',{}).get('volatility_label','N/A')}\n"
            f"北向资金今日：{context.get('north_flow',{}).get('today','N/A')}\n"
        ))

        # 专家分项
        for i, (name, rpt) in enumerate(zip(tab_names, reports)):
            pdf.add_page()
            sf(13); pdf.cell(0, 9, f"三-{i+1}、{name} 专项研判", ln=True)
            sf(8); pdf.multi_cell(0, 5.5, rpt.replace("**","").replace("#","").replace("*",""))

        # 免责声明
        pdf.add_page()
        sf(9)
        pdf.multi_cell(0, 6,
            "免责声明\n\n"
            "本报告由龙眼AI研判系统自动生成，基于虎之眼(Eye of Tiger)金融内核，"
            "仅供学习研究参考，不构成投资建议。A股市场存在较高风险，请谨慎决策。\n\n"
            "数据来源：AKShare · 东方财富 · 新浪财经 · FRED\n"
            "AI模型：Google Gemini 2.0 Flash\n\n"
            "龙眼深度研判系统 © 2025")

        return pdf.output()
