"""
龙眼数据引擎 (AShareDataEngine)
核心修复：
1. 强制 6 位数字提取，过滤所有后缀干扰
2. 增加东财 API 的 ut 参数校验与 Headers 模拟
3. 增加休市/停牌数据的自动填充逻辑 (昨收替代现价)
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
    # 东方财富 API 基础地址
    EF_BASE = "https://push2.eastmoney.com/api/qt/stock/get"

    def get_full_context(self, ticker_full: str, raw_ticker: str) -> dict:
        context = {
            "symbol": ticker_full,
            "raw_ticker": raw_ticker,
            "timestamp": datetime.datetime.now().isoformat(),
        }

        # 1. 价格快照 (核心优先级)
        context.update(self._get_price_snapshot(ticker_full, raw_ticker))
        # 2. 基本面 (由虎之眼内核驱动)
        context.update(self._get_fundamentals(ticker_full, raw_ticker))
        # 3. 宏观利率 (基准：中国10年期国债)
        context.update(self._get_macro_rates())
        # 4. 北向资金 (博弈关键因子)
        context.update(self._get_north_flow())

        return context

    def _get_price_snapshot(self, ticker_full: str, raw_ticker: str) -> dict:
        """核心修复：穿透东财接口的鲁棒性解析"""
        result = {
            "price_info": {"current_price": "N/A", "change_pct": 0.0, "pe_ttm": "N/A", "pb": "N/A"},
            "company_name": raw_ticker,
            "market_cap": "N/A",
            "industry": "N/A",
        }

        try:
            # 1. 强制提取 6 位纯数字 (兼容 600519.SH 或 600519)
            code_match = re.search(r'\d{6}', str(raw_ticker))
            if not code_match:
                result["price_error"] = "代码格式非法"
                return result
            code = code_match.group(0)
            
            # 2. 严谨判定 A 股市场前缀 (1:沪市, 0:深/北)
            if code.startswith(('60', '68', '90')): 
                secid = f"1.{code}"
            else:
                secid = f"0.{code}"

            # f43: 现价, f58: 名称, f60: 昨收, f116: 市值, f162: PE(动), f167: PB
            params = {
                "secid": secid,
                "fields": "f43,f58,f60,f116,f162,f167",
                "ut": "fa5fd1943c7b386f172d6893dbfba10b",
                "invt": "2",
                "fltt": "2",
            }
            
            # 模拟浏览器 Headers 绕过简单拦截
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://quote.eastmoney.com/"
            }
            
            resp = requests.get(self.EF_BASE, params=params, headers=headers, timeout=8)
            resp.encoding = 'utf-8' # 强制编码
            data = resp.json().get("data")

            if data and isinstance(data, dict):
                def safe_float(key, divisor=100):
                    v = data.get(key)
                    # 识别东财休市/无效标志
                    if v is None or v == "-" or v == 0: return "N/A"
                    try: return round(float(v) / divisor, 2)
                    except: return "N/A"

                cp = safe_float("f43")   # 实时现价
                pcp = safe_float("f60")  # 昨日收盘
                
                # 休市保护：如果现价读不到或为0，用昨收填充
                if cp == "N/A": cp = pcp

                chg = 0.0
                if isinstance(cp, (int, float)) and isinstance(pcp, (int, float)) and pcp > 0:
                    chg = round((cp - pcp) / pcp * 100, 2)

                mv_raw = data.get("f116")
                mv_str = f"{round(float(mv_raw)/100000000, 2)}亿" if mv_raw and str(mv_raw) != "-" else "N/A"

                result["price_info"] = {
                    "current_price": cp,
                    "change_pct": chg,
                    "pe_ttm": safe_float("f162"),
                    "pb": safe_float("f167"),
                }
                result["company_name"] = data.get("f58", raw_ticker)
                result["market_cap"] = mv_str
            else:
                result["price_error"] = f"东财 API 未返回有效内容: {resp.text[:50]}"

        except Exception as e:
            result["price_error"] = str(e)

        # AKShare 兜底获取行业信息
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
            code = re.search(r'\d{6}', str(raw_ticker)).group(0)
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
                if not df_bond.empty:
                    rates["macro_rate"] = str(df_bond.iloc[-1, 1])
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
                flow["north_flow"] = {
                    "today": f"{val:.2f}亿",
                    "direction": "流入" if val > 0 else "流出",
                    "5day": f"{df.iloc[-5:, 1].sum():.2f}亿"
                }
            except: pass
        return flow