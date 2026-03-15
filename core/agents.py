"""虎之眼 Agents 内核 v12.0 — 阿里云百炼适配版[优化] 增强 Prompt 思维链 (CoT) 引导[修复] 评分提取正则容错处理"""
from openai import OpenAI
import streamlit as st
import os
import re

class LongEyeOrchestrator:
    def __init__(self, api_key=None):
        # 从 Streamlit Secrets 获取百炼配置
        # 确保 .streamlit/secrets.toml 中存在 DASHSCOPE_API_KEY 和 DASHSCOPE_BASE_URL
        self.client = OpenAI(
            api_key=st.secrets.get("DASHSCOPE_API_KEY", os.getenv("DASHSCOPE_API_KEY")),
            base_url=st.secrets.get("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        )
        # 优化：使用更快的模型 qwen-plus 替代 qwen-max
        self.model = "qwen-plus"

    def consult_skill(self, skill_path, ticker, context):
        """调用专项审计专家 - 增加 CoT 引导"""
        try:
            with open(skill_path, 'r', encoding='utf-8') as f:
                protocol = f.read()

            # 针对 Qwen-Max 优化的 System Prompt
            system_prompt = (
                "你是一名资深的 A 股金融分析师。请严格遵循下方的【审计协议】进行逻辑推理。"
                "思考步骤：1. 分析上下文数据；2. 对照协议条款；3. 给出定性结论；4. 给出定量评分。"
                "注意：不要输出多余的寒暄语，直接输出专业报告。"
            )
            prompt = f"""【审计协议】{protocol}【待审计标的】代码/名称：{ticker}【上下文数据】{context}请根据上述协议和数据，输出详细的审计报告。"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3 # 降低温度以提高逻辑稳定性
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"⚠️ 专家 {skill_path} 调用失败：{str(e)}"

    def synthesize_cio(self, ticker, reports, context):
        """CIO 综合裁决逻辑 - 强制评分格式"""
        combined_reports = "\n\n".join(reports)

        # 强化 Prompt 以确保 100% 返回指定格式
        prompt = (
            f"你是虎之眼系统的 CIO (首席投资官)。请综合以下 {len(reports)} 位专家的报告，对 {ticker} 给出最终裁决。\n\n"
            f"### 任务要求:\n"
            f"1. **深度综合**: 权衡各方观点，若存在冲突（如技术面好但基本面差），需明确指出风险点。\n"
            f"2. **风格**: 语言简练、犀利，直击痛点，避免模棱两可。\n"
            f"3. **格式强制**: 必须在报告的**最后一行**，严格按照以下格式输出 6 个维度的 0-100 整数评分，不得有任何多余字符：\n"
            f" 评分：[价值, 技术, 行业, 资金, 成长, 风控]\n"
            f" 示例：评分：[85, 70, 90, 65, 80, 95]\n\n"
            f"### 专家报告汇总:\n{combined_reports}\n\n"
            f"### 基础数据:\n{context}\n\n"
            f"请开始你的裁决："
        )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2 # 更低温度以保证格式稳定
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"⚠️ CIO 综合裁决生成失败：{str(e)}\n\n原始报告摘要：{combined_reports[:500]}..."

    def extract_scores(self, cio_report):
        """从 CIO 报告中提取评分"""
        # 修复：增强正则容错处理
        pattern = r'评分：\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]'
        match = re.search(pattern, cio_report)
        if match:
            scores = list(map(int, match.groups()))
            # 确保分数在 0-100 范围内
            scores = [max(0, min(100, s)) for s in scores]
            return scores
        else:
            # 如果未找到，返回默认值或引发异常
            print(f"警告：未能从 CIO 报告中提取到有效评分。报告内容：\n{cio_report}")
            return [50, 50, 50, 50, 50, 50] # 返回中性评分作为兜底