import requests
import pandas as pd
import re, json, os, datetime
import numpy as np

# 尝试导入 AKShare 作为选股雷达的数据源
try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False

_TRACK_FILE = "data/win_track.json"

class AShareDataEngine:
    def __init__(self):
        self.brand = "虎之眼 (Eye of Tiger) 金融内核"

    # ── [修复] 极速多源行情引擎 (解决云端 IP 屏蔽) ──
    def get_price_snapshot(self, code):
        """三重保底：腾讯(极速) -> 新浪(备援) -> AK(全量)"""
        m = re.search(r"\d{6}", str(code))
        if not m: return {"current_price": "N/A", "change_pct": 0.0}
        clean_code = m.group(0)
        
        # 1. 腾讯行情接口 (对云端最友好，无需 Referer)
        try:
            full_code = f"s_sh{clean_code}" if clean_code.startswith(('60', '68')) else f"s_sz{clean_code}"
            url = f"http://qt.gtimg.cn/q={full_code}"
            resp = requests.get(url, timeout=3)
            data = resp.text.split('~')
            if len(data) > 3:
                return {
                    "current_price": float(data[3]),
                    "change_pct": float(data[32]),
                    "company_name": data[1]
                }
        except: pass

        # 2. 备援：新浪接口 (带 Referer 校验)
        try:
            url = f"http://hq.sinajs.cn/list={('sh' if clean_code.startswith('6') else 'sz')}{clean_code}"
            headers = {"Referer": "http://finance.sina.com.cn"}
            r = requests.get(url, headers=headers, timeout=3)
            p = r.text.split('"')[1].split(',')
            if len(p) > 3:
                cp, pcp = float(p[3]), float(p[2])
                return {"current_price": cp if cp>0 else pcp, "change_pct": round((cp-pcp)/pcp*100,2) if pcp>0 else 0.0}
        except: pass
        return {"current_price": "N/A", "change_pct": 0.0}

    # ── 获取完整研判上下文 ──
    def get_full_context(self, ticker_full, raw_ticker):
        code_match = re.search(r"\d{6}", str(raw_ticker))
        code = code_match.group(0) if code_match else raw_ticker
        ctx = {"symbol": ticker_full, "raw_ticker": code, "brand": self.brand}
        
        # 行情快照 (解决读不出股价的 Bug)
        ctx["price_info"] = self.get_price_snapshot(code)
        
        # 指南针 CYQ 筹码模型估算
        ctx["chip_analysis"] = self._estimate_chips_cyq(code)
        ctx["profit_ratio"] = ctx["chip_analysis"].get("profit_ratio", "暂无数据")
        
        # 宏观利率 (中债 10Y)
        ctx["macro_rate"] = "2.31"
        if HAS_AKSHARE:
            try:
                df = ak.bond_zh_us_rate(start_date="20250101")
                ctx["macro_rate"] = str(df.iloc[-1, 1])
            except: pass
        return ctx

    def _estimate_chips_cyq(self, code):
        """筹码获利比率简单估算模型"""
        if not HAS_AKSHARE: return {"profit_ratio": "暂无数据"}
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq").tail(60)
            vwap = (df['收盘'] * df['成交量']).sum() / df['成交量'].sum()
            curr = df['收盘'].iloc[-1]
            profit = round(min(max((curr - vwap*0.9)/(vwap*0.2) * 100, 0), 100), 1)
            return {"avg_cost": round(vwap, 2), "profit_ratio": f"{profit}%"}
        except: return {"profit_ratio": "暂无数据"}

    # ── 指南针式选股池与胜率追踪 ──
    def get_strategy_pool(self, strat_type):
        if not HAS_AKSHARE: return pd.DataFrame()
        try:
            df = ak.stock_zh_a_spot_em()
            df = df[df['成交额'] > 1e8]
            if strat_type == "涨停最强":
                res = df[df['涨跌幅'] > 9.7].sort_values("换手率")
            else:
                res = df.head(10)
            return self._attach_win_rate(res.head(8), "策略预警")
        except: return pd.DataFrame()

    def get_ai_screener(self, query):
        if not HAS_AKSHARE: return pd.DataFrame()
        try:
            df = ak.stock_zh_a_spot_em()
            if "快速上涨" in query and "回撤" in query:
                res = df[(df['涨跌幅'] > 4) & (df['振幅'] < 6)]
                reason = "锁仓拉升：振幅极小，主力筹码锁定度高。"
            else:
                res = df.sort_values("涨跌幅", ascending=False)
                reason = "资金博弈热点"
            return self._attach_win_rate(res.head(8), reason)
        except: return pd.DataFrame()

    def _attach_win_rate(self, df, reason):
        """AI 胜率追踪与信心建立"""
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
                "代码": code, "名称": row.get('名称'), "涨跌幅": row.get('涨跌幅'), "理由": reason,
                "AI入选日": track[code]["date"], "最高涨幅": f"+{gain}%",
                "胜率标签": "🏆 金牌推荐" if gain > 15 else "📈 趋势向上"
            })
        json.dump(track, open(_TRACK_FILE, "w"))
        return pd.DataFrame(results)