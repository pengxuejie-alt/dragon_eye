"""
龙眼数据引擎 (AShareDataEngine)
核心修复：
1. 增强 A 股市场前缀判定 (沪/深/创/科/北)
2. 增加数据清洗安全阀，解决休市期间 "-" 字符导致的 N/A
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
        context = {
            "symbol": ticker_full,
            "raw_ticker": raw_ticker,
            "timestamp": datetime.datetime.now().isoformat(),
        }

        # 1. 价格快照
        context.update(self._get_price_snapshot(ticker_full, raw_ticker))
        # 2. 基本面 (AKShare)
        context.update(self._get_fundamentals(ticker_full, raw_ticker))
        # 3. 宏观利率
        context.update(self._get_macro_rates())
        # 4. 北向资金
        context.update(self._get_north_flow())

        return context

    def _get_price_snapshot(self, ticker_full: str, raw_ticker: str) -> dict:
        result = {
            "price_info": {"current_price": "N/A", "change_pct": 0.0, "pe_ttm": "N/A", "pb": "N/A"},
            "company_name": raw_ticker,
            "market_cap": "N/A",
            "industry": "N/A",
        }

        try:
            # 提取 6 位数字代码
            code = re.search(r'\d{6}', raw_ticker).group(0)
            
            # 严谨的市场前缀逻辑
            if code.startswith(('60', '68', '90')): # 沪市
                secid = f"1.{code}"
            elif code.startswith(('00', '30', '20', '43', '83', '87')): # 深市、创业板、北交所
                secid = f"0.{code}"
            else:
                secid = f"0.{code}"

            # f43: 现价, f60: 昨收, f116: 市值, f162: PE, f167: PB
            params = {
                "secid": secid,
                "fields": "f43,f58,f60,f116,f162,f167",
                "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            }
            
            resp = requests.get(self.EF_BASE, params=params, timeout=5)
            data = resp.json().get("data")

            if data:
                def safe_float(key, divisor=100):
                    v = data.get(key)
                    if v is None or v == "-": return "N/A"
                    try: return round(float(v) / divisor, 2)
                    except: return "N/A"

                cp = safe_float("f43")
                pcp = safe_float("f60")
                
                # 休市或停牌处理
                if cp == "N/A": cp = pcp

                chg = 0.0
                if isinstance(cp, (int, float)) and isinstance(pcp, (int, float)) and pcp > 0:
                    chg = round((cp - pcp) / pcp * 100, 2)

                mv_raw = data.get("f116")
                mv_str = f"{round(float(mv_raw)/100000000, 2)}亿" if mv_raw and mv_raw != "-" else "N/A"

                result["price_info"] = {
                    "current_price": cp,
                    "change_pct": chg,
                    "pe_ttm": safe_float("f162"),
                    "pb": safe_float("f167"),
                }
                result["company_name"] = data.get("f58", raw_ticker)
                result["market_cap"] = mv_str
        except Exception as e:
            result["price_error"] = str(e)

        if HAS_AKSHARE:
            try:
                df = ak.stock_individual_info_em(symbol=code)
                info = dict(zip(df.iloc[:, 0], df.iloc[:, 1]))
                result["industry"] = info.get("所处行业", "N/A")
            except: pass
        return result

    def _get_fundamentals(self, ticker_full: str, raw_ticker: str) -> dict:
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
        rates = {"macro_rate": "2.32", "lpr_1y": "3.10", "lpr_5y": "3.60"}
        if HAS_AKSHARE:
            try:
                df_bond = ak.bond_zh_us_rate(start_date="20250101")
                if not df_bond.empty: rates["macro_rate"] = str(df_bond.iloc[-1, 1])
                df_lpr = ak.macro_china_lpr()
                if not df_lpr.empty:
                    rates["lpr_1y"] = str(df_lpr.iloc[-1, 1])
                    rates["lpr_5y"] = str(df_lpr.iloc[-1, 2])
            except: pass
        return rates

    def _get_north_flow(self) -> dict:
        flow = {"north_flow": {"today": "N/A", "direction": "N/A"}}
        if HAS_AKSHARE:
            try:
                df = ak.stock_hsgt_north_net_flow_in_em(indicator="沪深港通")
                val = float(df.iloc[-1, 1])
                flow["north_flow"] = {"today": f"{val:.2f}亿", "direction": "流入" if val > 0 else "流出"}
            except: pass
        return flow