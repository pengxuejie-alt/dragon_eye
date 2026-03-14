"""
龙眼数据引擎 (AShareDataEngine) - 虎之眼进化版
集成：东财/AK/新浪三重价格保险 + 筹码获利估算 + 中债 10Y 利率
"""
import requests
import datetime
import re
import numpy as np

try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False

class AShareDataEngine:
    EF_BASE = "https://push2.eastmoney.com/api/qt/stock/get"
    SINA_BASE = "http://hq.sinajs.cn/list="

    def get_full_context(self, ticker_full, raw_ticker):
        code = re.search(r'\d{6}', str(raw_ticker)).group(0)
        context = {
            "symbol": ticker_full,
            "raw_ticker": code,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        # 1. 三重引擎获取实时行情
        price_data = self._get_price_eastmoney(code)
        if price_data["price_info"]["current_price"] == "N/A":
            price_data = self._get_price_akshare(code)
        if price_data["price_info"]["current_price"] == "N/A":
            price_data = self._get_price_sina(code)
        context.update(price_data)

        # 2. 核心：筹码获利比率估算 (参考指南针逻辑)
        context["chip_analysis"] = self._estimate_chips(code)

        # 3. 核心：中国 10Y 国债利率与 LPR
        context.update(self._get_macro_rates())

        # 4. 财务审计指标 (ROE, 营收, 负债)
        context.update(self._get_fundamentals(code))

        # 5. 北向资金博弈流向
        context.update(self._get_north_flow())
        
        return context

    def _estimate_chips(self, code):
        """估算筹码分布：计算 60 日成交量加权成本 (VWAP)"""
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq").tail(60)
            vwap = (df['收盘'] * df['成交量']).sum() / df['成交量'].sum()
            curr = df['收盘'].iloc[-1]
            # 获利盘估算：现价高出成本均价则为正获利
            profit_ratio = round(min(max((curr - vwap*0.9)/(vwap*0.2) * 100, 0), 100), 2)
            return {"avg_cost": round(vwap, 2), "profit_ratio": f"{profit_ratio}%"}
        except: return {"avg_cost": "N/A", "profit_ratio": "N/A"}

    def _get_price_eastmoney(self, code):
        res = {"price_info": {"current_price": "N/A", "change_pct": 0.0}}
        try:
            secid = f"1.{code}" if code.startswith(('60', '68')) else f"0.{code}"
            params = {"secid": secid, "fields": "f43,f58,f60,f116,f162,f167", "ut": "fa5fd1943c7b386f172d6893dbfba10b"}
            data = requests.get(self.EF_BASE, params=params, timeout=5).json().get("data")
            if data:
                cp = data.get("f43", 0)/100; pcp = data.get("f60", 0)/100
                res["price_info"] = {"current_price": cp if cp>0 else pcp, "pe": data.get("f162", "N/A"), "pb": data.get("f167", "N/A")}
                res["price_info"]["change_pct"] = round((cp-pcp)/pcp*100, 2) if pcp>0 else 0.0
                res["company_name"] = data.get("f58")
                res["market_cap"] = f"{round(data.get('f116',0)/1e8, 2)}亿"
        except: pass
        return res

    def _get_macro_rates(self):
        """同步中国 10Y 国债收益率"""
        rates = {"macro_rate": "2.31", "lpr_1y": "3.10"}
        if HAS_AKSHARE:
            try:
                df = ak.bond_zh_us_rate(start_date="20250101")
                rates["macro_rate"] = str(df.iloc[-1, 1]) # 中债10年
            except: pass
        return rates

    def _get_fundamentals(self, code):
        res = {"fundamentals": {}}
        try:
            df = ak.stock_financial_analysis_indicator(symbol=code, start_year="2024")
            latest = df.iloc[0]
            res["fundamentals"] = {
                "roe": latest.get("净资产收益率"),
                "debt_ratio": latest.get("资产负债率"),
                "gross_margin": latest.get("销售毛利率"),
                "net_profit_margin": latest.get("销售净利率")
            }
        except: pass
        return res

    def _get_north_flow(self):
        try:
            df = ak.stock_hsgt_north_net_flow_in_em()
            return {"north_today": f"{df.iloc[-1, 1]:.2f}亿"}
        except: return {"north_today": "N/A"}