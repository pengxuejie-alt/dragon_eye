"""
虎之眼 Agents 内核 v12.0 — 阿里云百炼适配版
[修复] 国内 ECS 无法连接 Gemini 的问题
[技术] 采用 OpenAI 兼容模式调用通义千问大模型
"""
from openai import OpenAI
import streamlit as st
import os

class LongEyeOrchestrator:
    def __init__(self, api_key=None):
        # 从 Streamlit Secrets 获取百炼配置
        self.client = OpenAI(
            api_key=st.secrets["DASHSCOPE_API_KEY"],
            base_url=st.secrets["DASHSCOPE_BASE_URL"]
        )
        self.model = "qwen-max" # 阿里云百炼旗舰模型

    def consult_skill(self, skill_path, ticker, context):
        """调用专项审计专家"""
        with open(skill_path, 'r', encoding='utf-8') as f:
            protocol = f.read()
        
        prompt = f"你现在是龙眼系统的专项专家。请根据以下审计协议对 {ticker} 进行深度研判：\n{protocol}\n\n上下文数据：{context}"
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content

    def synthesize_cio(self, ticker, reports, context):
        """CIO 综合裁决逻辑，输出包含六边形评分"""
        combined_reports = "\n\n".join(reports)
        prompt = (
            f"你现在是虎之眼系统的 CIO。请综合以下专家报告对 {ticker} 给出最终裁决。\n"
            f"要求：\n1. 言简意赅，直击痛点。\n"
            f"2. 必须在报告末尾按此格式给出 6 个维度的 0-100 评分：评分: [价值, 技术, 行业, 资金, 成长, 风控]\n"
            f"例如：评分: [85, 70, 90, 65, 80, 95]\n\n"
            f"专家报告汇总：\n{combined_reports}\n\n基础数据：{context}"
        )
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content