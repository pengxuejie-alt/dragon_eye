# 🐉 龙眼 A股深度研判系统

> 基于 **Anthropic Financial Services Plugin** 架构 + 鹰眼美股系统设计理念
> 专为A股市场打造的多智能体并行研判平台

---

## 🏗️ 系统架构

```
龙眼系统 (仿 Anthropic financial-services-plugins 架构)
│
├── skills/                    ← Plugin Skills 层（可热插拔的专家协议）
│   ├── 01_价值审计.md         ← 财务健康度 + 盈利质量审计（A股CAS版）
│   ├── 02_技术量化.md         ← 均线/量价/筹码分析（T+1制度适配）
│   ├── 03_政策宏观.md         ← 产业政策 + LPR + 北向资金分析
│   ├── 04_资金博弈.md         ← 龙虎榜 + 游资/机构/散户博弈
│   ├── 05_成长质量.md         ← PEG + TAM + 规模效应分析
│   └── 06_风险控制.md         ← A股特有风险红旗清单 + 止损模型
│
├── core/
│   ├── engine.py             ← Data Engine（AKShare + 东方财富 + FRED）
│   └── agents.py             ← LongEyeOrchestrator（Gemini驱动）
│
├── app.py                    ← Streamlit 主界面
├── requirements.txt
└── .streamlit/secrets.toml   ← API Keys（不提交到Git）
```

## 🔑 架构对标关系

| 龙眼组件 | Anthropic Plugin 对应 |
|---------|----------------------|
| `skills/*.md` | `equity-research/skills/*/SKILL.md` |
| `core/engine.py` | `financial-analysis` 核心数据连接器 |
| `LongEyeOrchestrator.consult_skill()` | Sub-agent 调用逻辑 |
| `synthesize_cio()` | `/earnings` 命令的 CIO 合成层 |
| Streamlit UI | Claude Cowork 前端 |

## 🚀 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API Keys
mkdir .streamlit
cat > .streamlit/secrets.toml << EOF
GEMINI_KEY = "your-gemini-api-key"
FRED_KEY = "your-fred-api-key"  # 可选，用于美国国债利率对比
EOF

# 3. 启动
streamlit run app.py
```

## 📊 A股专属特性

相比鹰眼美股系统，龙眼专门适配了：

1. **制度差异**：T+1、涨跌停板(±10%/±20%)、退市制度
2. **数据源**：AKShare（免费）+ 东方财富API（无需Key）
3. **宏观基准**：中国10年期国债 + LPR替代美债
4. **特色因子**：北向资金、龙虎榜、股权质押率、商誉风险
5. **政策维度**：产业政策轮动、监管风险、两会政策窗口

## ⚠️ 免责声明

本系统仅供学习研究，不构成投资建议。A股市场风险高，请谨慎决策。
