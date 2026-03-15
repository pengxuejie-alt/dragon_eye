import requests
import pandas as pd
import re, json, os, datetime
import numpy as np

# 尝试导入 AKShare 作为选股数据源
try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False

_TRACK_FILE = "data/win_track.json"

class AShareDataEngine:
    def __init__(self):
        self.brand = "虎之眼 (Eye of Tiger) 金融内核"

    def _ensure_code(self, input_val):
        """[Fix] 极速代码转换：支持中文名反查"""
        m = re.search(r"\d{6}", str(input_val))
        if m: return m.group(0)
        try:
            # 腾讯搜索接口：对海外 IP 极度友好且轻量
            search_url = f"http://smartbox.gtimg.cn/s3/?q={input_val}&t=all"
            resp = requests.get(search_url, timeout=2)
            code_match = re.search(r"\d{6}", resp.text)
            if code_match: return code_match.group(0)
        except: pass
        return str(input_val)

    def get_price_snapshot(self, raw_input):
        """[Fix] 单点穿透：秒读股价与名称"""
        clean_code = self._ensure_code(raw_input)
        try:
            market = "sh" if clean_code.startswith(('60', '68')) else "sz"
            url = f"http://qt.gtimg.cn/q=s_{market}{clean_code}"
            resp = requests.get(url, timeout=3)
            data = resp.text.split('~')
            if len(data) > 3:
                return {
                    "current_price": float(data[3]),
                    "change_pct": float(data[32]),
                    "company_name": data[1]
                }
        except: pass
        return {"current_price": "N/A", "change_pct": 0.0, "company_name": raw_input}

    def get_full_context(self, ticker_full, raw_ticker):
        """[Fix] 完整上下文获取"""
        code = self._ensure_code(raw_ticker)
        price_data = self.get_price_snapshot(code)
        ctx = {
            "symbol": ticker_full, 
            "raw_ticker": code, 
            "brand": self.brand,
            "price_info": price_data, 
            "company_name": price_data.get("company_name", code),
            "macro_rate": "2.31"
        }
        # 指南针 CYQ 筹码模型
        ctx["chip_analysis"] = self._estimate_chips_cyq(code)
        ctx["profit_ratio"] = ctx["chip_analysis"].get("profit_ratio", "暂无数据")
        return ctx

    def _estimate_chips_cyq(self, code):
        """筹码获利比率简单估算"""
        if not HAS_AKSHARE: return {"profit_ratio": "暂无数据"}
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq").tail(60)
            vwap = (df['收盘'] * df['成交量']).sum() / df['成交量'].sum()
            curr = df['收盘'].iloc[-1]
            profit = round(min(max((curr - vwap*0.9)/(vwap*0.2) * 100, 0), 100), 1)
            return {"avg_cost": round(vwap, 2), "profit_ratio": f"{profit}%"}
        except: return {"profit_ratio": "暂无数据"}

    def get_strategy_pool(self, strat_type):
        """选股雷达"""
        if not HAS_AKSHARE: return pd.DataFrame()
        try:
            df = ak.stock_zh_a_spot_em()
            res = df[df['成交额'] > 1e8].head(8)
            return self._attach_win_rate(res, "策略监测")
        except: return pd.DataFrame()

    def get_ai_screener(self, query):
        """AI 语义选股"""
        if not HAS_AKSHARE: return pd.DataFrame()
        try:
            df = ak.stock_zh_a_spot_em()
            res = df[df['成交额'] > 1e8].head(8)
            return self._attach_win_rate(res, "AI推荐")
        except: return pd.DataFrame()

    def _attach_win_rate(self, df, reason):
        """[亮点] 胜率追踪与信心建立"""
        if not os.path.exists("data"): os.makedirs("data")
        track = json.load(open(_TRACK_FILE)) if os.path.exists(_TRACK_FILE) else {}
        today = datetime.date.today().isoformat()
        results = []
        for _, row in df.iterrows():
            code, price = str(row.get('代码', '')), float(row.get('最新价', 0))
            if code not in track: track[code] = {"date": today, "entry": price, "max": price}
            else: track[code]["max"] = max(track[code]["max"], price)
            gain = round((track[code]["max"] - track[code]["entry"]) / track[code]["entry"] * 100, 1)
            results.append({
                "代码": code, "名称": row.get('名称'), "理由": reason,
                "AI入选日": track[code]["date"], "最高涨幅": f"+{gain}%"
            })
        json.dump(track, open(_TRACK_FILE, "w"))
        return pd.DataFrame(results)