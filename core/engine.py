"""
龙眼数据引擎 (AShareDataEngine)
数据源: AKShare (免费) + 东方财富 API + FRED 宏观数据
架构参考: Anthropic financial-services-plugins / financial-analysis core plugin
"""

import requests
import datetime
import json

try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False

try:
    import streamlit as st
    def get_secret(key, default=None):
        try:
            return st.secrets.get(key, default)
        except Exception:
            return default
except Exception:
    def get_secret(key, default=None):
        return default


class AShareDataEngine:
    """
    A股数据引擎
    Plugin 架构：本引擎充当 financial-analysis 核心插件的数据连接器角色
    负责统一抽象所有外部数据源，向上层 Agent 提供标准化的 context dict
    """

    # ── 东方财富 API 端点 (免费，无需 KEY) ──
    EF_BASE = "https://push2.eastmoney.com/api/qt/stock/get"
    EF_FINANCIAL = "https://datacenter.eastmoney.com/securities/api/data/v1/get"

    def get_full_context(self, ticker_full: str, raw_ticker: str) -> dict:
        """
        汇聚所有数据源，返回标准化上下文字典
        对标 Anthropic plugin 中的 'query plan' 执行逻辑：
        先获取价格快照，再获取基本面，最后叠加宏观指标
        """
        context = {
            "symbol": ticker_full,
            "raw_ticker": raw_ticker,
            "timestamp": datetime.datetime.now().isoformat(),
        }

        # 1. 价格快照
        context.update(self._get_price_snapshot(ticker_full, raw_ticker))

        # 2. 基本面数据
        context.update(self._get_fundamentals(ticker_full, raw_ticker))

        # 3. 宏观利率（中国10年期国债 + LPR）
        context.update(self._get_macro_rates())

        # 4. 北向资金流向（A股特有）
        context.update(self._get_north_flow())

        # 5. 行业板块数据
        context.update(self._get_sector_context(raw_ticker))

        return context

    def _get_price_snapshot(self, ticker_full: str, raw_ticker: str) -> dict:
        """东方财富实时行情快照"""
        result = {
            "price_info": {
                "current_price": "N/A",
                "change_pct": 0.0,
                "volume": "N/A",
                "turnover": "N/A",
                "high_52w": "N/A",
                "low_52w": "N/A",
                "pe_ttm": "N/A",
                "pb": "N/A",
                "total_mv": "N/A",
            },
            "company_name": raw_ticker,
            "market_cap": "N/A",
            "industry": "N/A",
        }

        try:
            # 构建东财代码格式
            code = raw_ticker.zfill(6)
            secid = f"1.{code}" if code.startswith("6") else f"0.{code}"

            params = {
                "secid": secid,
                "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f107,f116,f167,f168,f169,f170,f171",
                "invt": "2",
                "fltt": "2",
                "cb": "",
            }
            resp = requests.get(self.EF_BASE, params=params, timeout=8)
            data = resp.json().get("data", {})

            if data:
                price = data.get("f43", "N/A")
                pre_close = data.get("f60", price)
                high = data.get("f44", "N/A")
                low = data.get("f45", "N/A")
                vol = data.get("f47", "N/A")
                amt = data.get("f48", "N/A")
                name = data.get("f58", raw_ticker)
                pe = data.get("f162", "N/A")
                pb = data.get("f167", "N/A")
                mv = data.get("f116", "N/A")

                # 价格处理（东财返回值需/100）
                def fmt(v, div=100):
                    try:
                        return round(float(v) / div, 2)
                    except Exception:
                        return "N/A"

                cp = fmt(price)
                pcp = fmt(pre_close)
                chg = round((cp - pcp) / pcp * 100, 2) if isinstance(cp, float) and isinstance(pcp, float) and pcp != 0 else 0.0

                mv_val = fmt(mv, 10000)  # 转换为亿元
                mv_str = f"{mv_val}亿" if isinstance(mv_val, float) else "N/A"

                result["price_info"] = {
                    "current_price": cp,
                    "change_pct": chg,
                    "high_today": fmt(high),
                    "low_today": fmt(low),
                    "volume": f"{fmt(vol, 1)}手",
                    "pe_ttm": fmt(pe, 100),
                    "pb": fmt(pb, 100),
                }
                result["company_name"] = name
                result["market_cap"] = mv_str
        except Exception as e:
            result["price_error"] = str(e)

        # AKShare 补充数据
        if HAS_AKSHARE:
            try:
                code = raw_ticker.zfill(6)
                df = ak.stock_individual_info_em(symbol=code)
                info = dict(zip(df.iloc[:, 0], df.iloc[:, 1]))
                result["industry"] = info.get("所处行业", info.get("industry", "N/A"))
                if result["company_name"] == raw_ticker:
                    result["company_name"] = info.get("股票简称", raw_ticker)
                result["company_profile"] = {
                    "listing_date": info.get("上市时间", "N/A"),
                    "registered_capital": info.get("注册资本", "N/A"),
                    "total_shares": info.get("总股本", "N/A"),
                    "float_shares": info.get("流通股", "N/A"),
                }
            except Exception:
                pass

        return result

    def _get_fundamentals(self, ticker_full: str, raw_ticker: str) -> dict:
        """基本面财务数据（AKShare 东财数据）"""
        result = {"fundamentals": {}}

        if not HAS_AKSHARE:
            return result

        try:
            code = raw_ticker.zfill(6)

            # 资产负债表关键指标
            try:
                df_indicator = ak.stock_financial_analysis_indicator(symbol=code, start_year="2021")
                if df_indicator is not None and not df_indicator.empty:
                    latest = df_indicator.iloc[0].to_dict()
                    result["fundamentals"]["roe"] = latest.get("净资产收益率", "N/A")
                    result["fundamentals"]["gross_margin"] = latest.get("销售毛利率", "N/A")
                    result["fundamentals"]["net_margin"] = latest.get("销售净利率", "N/A")
                    result["fundamentals"]["debt_ratio"] = latest.get("资产负债率", "N/A")
                    result["fundamentals"]["current_ratio"] = latest.get("流动比率", "N/A")
            except Exception:
                pass

            # 财务摘要（最近4个季度营收/净利）
            try:
                df_profit = ak.stock_profit_sheet_by_report_em(symbol=code)
                if df_profit is not None and not df_profit.empty:
                    recent = df_profit.head(4)
                    result["fundamentals"]["revenue_trend"] = recent.get(
                        "营业总收入", recent.iloc[:, 0]
                    ).tolist() if "营业总收入" in recent.columns else []
                    result["fundamentals"]["net_profit_trend"] = recent.get(
                        "净利润", recent.iloc[:, 1]
                    ).tolist() if "净利润" in recent.columns else []
            except Exception:
                pass

        except Exception as e:
            result["fundamentals"]["error"] = str(e)

        return result

    def _get_macro_rates(self) -> dict:
        """
        中国宏观利率：10年期国债收益率 + LPR
        对标 Anthropic 宏观插件中的 DCF 折现率基准
        """
        result = {"macro_rate": "N/A", "lpr_1y": "N/A", "lpr_5y": "N/A"}

        # 尝试 AKShare 获取中国国债收益率
        if HAS_AKSHARE:
            try:
                df_bond = ak.bond_zh_us_rate(start_date="20240101")
                if df_bond is not None and not df_bond.empty:
                    latest = df_bond.iloc[-1]
                    result["macro_rate"] = round(float(latest.get("中国国债收益率10年", latest.iloc[1])), 2)
            except Exception:
                pass

            try:
                df_lpr = ak.macro_china_lpr()
                if df_lpr is not None and not df_lpr.empty:
                    latest_lpr = df_lpr.iloc[-1]
                    result["lpr_1y"] = str(latest_lpr.get("1年期贷款市场报价利率", "N/A"))
                    result["lpr_5y"] = str(latest_lpr.get("5年期以上贷款市场报价利率", "N/A"))
            except Exception:
                pass

        # 备用：FRED 美国10年（用于对比参考）
        if result["macro_rate"] == "N/A":
            fred_key = get_secret("FRED_KEY", "")
            if fred_key:
                try:
                    url = f"https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key={fred_key}&file_type=json"
                    r = requests.get(url, timeout=5).json()
                    result["us_10y_rate"] = r["observations"][-1]["value"]
                except Exception:
                    pass

        # 硬编码兜底（近期参考值）
        if result["macro_rate"] == "N/A":
            result["macro_rate"] = "2.32"  # 2025年参考值
        if result["lpr_1y"] == "N/A":
            result["lpr_1y"] = "3.10"
        if result["lpr_5y"] == "N/A":
            result["lpr_5y"] = "3.60"

        return result

    def _get_north_flow(self) -> dict:
        """北向资金（沪深港通）净流入数据——A股核心研判因子"""
        result = {"north_flow": {"today": "N/A", "5day": "N/A", "20day": "N/A"}}

        if not HAS_AKSHARE:
            return result

        try:
            df = ak.stock_hsgt_north_net_flow_in_em(indicator="沪深港通")
            if df is not None and not df.empty:
                today_flow = float(df.iloc[-1, 1])
                flow_5d = df.iloc[-5:, 1].astype(float).sum()
                flow_20d = df.iloc[-20:, 1].astype(float).sum()
                result["north_flow"] = {
                    "today": f"{today_flow:.2f}亿",
                    "5day": f"{flow_5d:.2f}亿",
                    "20day": f"{flow_20d:.2f}亿",
                    "direction": "净流入" if today_flow > 0 else "净流出",
                }
        except Exception as e:
            result["north_flow"]["error"] = str(e)

        return result

    def _get_sector_context(self, raw_ticker: str) -> dict:
        """行业板块强弱对比（A股特有：概念板块 + 行业涨跌）"""
        result = {"sector_rank": "N/A", "concept_boards": []}

        if not HAS_AKSHARE:
            return result

        try:
            code = raw_ticker.zfill(6)
            df_concept = ak.stock_board_concept_name_em()
            # 简化：仅返回所属概念板块数量
            result["concept_boards_count"] = len(df_concept) if df_concept is not None else "N/A"
        except Exception:
            pass

        return result
