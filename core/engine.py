"""
龙眼数据引擎 (AShareDataEngine)
核心改进：增强了对 A 股代码的识别逻辑与东财 API 的数据清洗
"""

import requests
import datetime
import json
import re

try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False

class AShareDataEngine:
    EF_BASE = "https://push2.eastmoney.com/api/qt/stock/get"

    def get_full_context(self, ticker_full: str, raw_ticker: str) -> dict:
        """
        汇聚所有数据源，返回标准化上下文字典
        """
        context = {
            "symbol": ticker_full,
            "raw_ticker": raw_ticker,
            "timestamp": datetime.datetime.now().isoformat(),
        }

        # 1. 价格快照（含鲁棒性解析）
        context.update(self._get_price_snapshot(ticker_full, raw_ticker))

        # 2. 基本面数据 (AKShare)
        context.update(self._get_fundamentals(ticker_full, raw_ticker))

        # 3. 宏观利率 (中国10年期国债 + LPR)
        context.update(self._get_macro_rates())

        # 4. 北向资金流向
        context.update(self._get_north_flow())

        return context

    def _get_price_snapshot(self, ticker_full: str, raw_ticker: str) -> dict:
        """从东方财富获取实时/休市行情"""
        result = {
            "price_info": {
                "current_price": "N/A",
                "change_pct": 0.0,
                "pe_ttm": "N/A",
                "pb": "N/A",
            },
            "company_name": raw_ticker,
            "market_cap": "N/A",
            "industry": "N/A",
        }

        try:
            # 提取 6 位纯数字
            code_match = re.search(r'\d{6}', raw_ticker)
            code = code_match.group(0) if code_match else raw_ticker.zfill(6)

            # 判定 A 股市场前缀
            # 1.60xxxx (沪), 0.00xxxx (深), 0.30xxxx (创), 0.43xxxx (北), 1.68xxxx (科)
            if code.startswith(('60', '68', '90')):
                secid = f"1.{code}"
            else:
                secid = f"0.{code}"

            params = {
                "secid": secid,
                "fields": "f43,f58,f60,f116,f162,f167,f117", 
                "ut": "fa5fd1943c7b386f172d6893dbfba10b", # 固定 Token
            }
            
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(self.EF_BASE, params=params, headers=headers, timeout=5)
            data = resp.json().get("data")

            if data:
                # 定义内部清洗函数：东财数值通常需 /100
                def clean(val, divisor=100):
                    if val == "-" or val is None:
                        return "N/A"
                    try:
                        return round(float(val) / divisor, 2)
                    except:
                        return "N/A"

                cp = clean(data.get("f43"))  # 现价
                pcp = clean(data.get("f60")) # 昨收
                
                # 计算涨跌幅 (即使休市，也能通过昨收计算)
                chg = 0.0
                if isinstance(cp, (int, float)) and isinstance(pcp, (int, float)) and pcp > 0:
                    chg = round((cp - pcp) / pcp * 100, 2)

                # 市值处理：f116 是总市值，单位通常是元
                mv_raw = data.get("f116")
                mv_str = f"{round(float(mv_raw)/100000000, 2)}亿" if mv_raw and mv_raw != "-" else "N/A"

                result["price_info"] = {
                    "current_price": cp,
                    "change_pct": chg,
                    "pe_ttm": clean(data.get("f162")), # PE(动态)
                    "pb": clean(data.get("f167")),     # PB
                }
                result["company_name"] = data.get("f58", raw_ticker)
                result["market_cap"] = mv_str

        except Exception as e:
            result["price_error"] = str(e)

        # 辅助补充：如果东财没读到行业，用 AKShare 补刀
        if HAS_AKSHARE and result["industry"] == "N/A":
            try:
                df = ak.stock_individual_info_em(symbol=code)
                info = dict(zip(df.iloc[:, 0], df.iloc[:, 1]))
                result["industry"] = info.get("所处行业", "N/A")
            except:
                pass

        return result

    def _get_fundamentals(self, ticker_full: str, raw_ticker: str) -> dict:
        """获取基本面指标"""
        res = {"fundamentals": {"roe": "N/A", "gross_margin": "N/A", "debt_ratio": "N/A"}}
        if not HAS_AKSHARE: return res
        try:
            code = re.search(r'\d{6}', raw_ticker).group(0)
            df = ak.stock_financial_analysis_indicator(symbol=code, start_year="2024")
            if not df.empty:
                latest = df.iloc[0]
                res["fundamentals"] = {
                    "roe": f"{latest.get('净资产收益率', 'N/A')}%",
                    "gross_margin": f"{latest.get('销售毛利率', 'N/A')}%",
                    "debt_ratio": f"{latest.get('资产负债率', 'N/A')}%",
                }
        except: pass
        return res

    def _get_macro_rates(self) -> dict:
        """获取 LPR 和 10Y 国债"""
        # 默认值
        rates = {"macro_rate": "2.31", "lpr_1y": "3.10", "lpr_5y": "3.60"}
        if HAS_AKSHARE:
            try:
                df_bond = ak.bond_zh_us_rate(start_date="20250101")
                if not df_bond.empty:
                    rates["macro_rate"] = str(df_bond.iloc[-1, 1])
                df_lpr = ak.macro_china_lpr()
                if not df_lpr.empty:
                    rates["lpr_1y"] = str(df_lpr.iloc[-1, 1])
                    rates["lpr_5y"] = str(df_lpr.iloc[-1, 2])
            except: pass
        return rates

    def _get_north_flow(self) -> dict:
        """获取北向资金"""
        flow = {"north_flow": {"today": "N/A", "direction": "N/A"}}
        if HAS_AKSHARE:
            try:
                df = ak.stock_hsgt_north_net_flow_in_em(indicator="沪深港通")
                val = float(df.iloc[-1, 1])
                flow["north_flow"] = {
                    "today": f"{val:.2f}亿",
                    "direction": "净流入" if val > 0 else "净流出",
                    "5day": f"{df.iloc[-5:, 1].sum():.2f}亿"
                }
            except: pass
        return flow