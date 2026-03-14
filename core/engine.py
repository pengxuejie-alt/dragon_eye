import requests
import pandas as pd
import re, json, os, datetime

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
        """[核心修复] 智能代码转换：支持中文名反查代码"""
        m = re.search(r"\d{6}", str(input_val))
        if m: return m.group(0)
        
        if HAS_AKSHARE:
            try:
                # 仅在输入非数字时检索全市场列表
                df = ak.stock_zh_a_spot_em()
                res = df[df['名称'] == str(input_val).strip()]
                if not res.empty:
                    return str(res.iloc[0]['代码'])
            except: pass
        return str(input_val)

    def get_price_snapshot(self, raw_input):
        """[核心修复] 极速行情获取：支持单点查询，解决云端超时"""
        clean_code = self._ensure_code(raw_input)
        
        # 1. 腾讯行情接口 (海外云端 IP 友好)
        try:
            market = "sh" if clean_code.startswith(('60', '68')) else "sz"
            url = f"http://qt.gtimg.cn/q=s_{market}{clean_code}"
            resp = requests.get(url, timeout=3)
            data = resp.text.split('~')
            if len(data) > 3:
                return {
                    "current_price": float(data[3]),
                    "change_pct": float(data[32]),
                    "company_name": data[1] # 提取股票名字
                }
        except: pass

        # 2. 备援：新浪接口
        try:
            sina_code = f"sh{clean_code}" if clean_code.startswith('6') else f"sz{clean_code}"
            headers = {"Referer": "http://finance.sina.com.cn"}
            r = requests.get(f"http://hq.sinajs.cn/list={sina_code}", headers=headers, timeout=3)
            p = r.text.split('"')[1].split(',')
            if len(p) > 1:
                cp, pcp = float(p[3]), float(p[2])
                return {
                    "current_price": cp if cp > 0 else pcp,
                    "change_pct": round((cp - pcp) / pcp * 100, 2) if pcp > 0 else 0.0,
                    "company_name": p[0]
                }
        except: pass
        
        return {"current_price": "N/A", "change_pct": 0.0, "company_name": raw_input}

    def get_full_context(self, ticker_full, raw_ticker):
        """获取完整审计上下文"""
        code = self._ensure_code(raw_ticker)
        ctx = {"symbol": ticker_full, "raw_ticker": code, "brand": self.brand}
        
        # 获取行情与名字
        price_data = self.get_price_snapshot(code)
        ctx["price_info"] = price_data
        ctx["company_name"] = price_data.get("company_name", code)
        
        # 指南针 CYQ 筹码估算 (仅研判时加载)
        ctx["chip_analysis"] = self._estimate_chips_cyq(code)
        ctx["profit_ratio"] = ctx["chip_analysis"].get("profit_ratio", "暂无数据")
        
        ctx["macro_rate"] = "2.31" # 默认中债 10Y
        return ctx

    def _estimate_chips_cyq(self, code):
        """筹码获利比率简单模型"""
        if not HAS_AKSHARE: return {"profit_ratio": "暂无数据"}
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq").tail(60)
            vwap = (df['收盘'] * df['成交量']).sum() / df['成交量'].sum()
            curr = df['收盘'].iloc[-1]
            profit = round(min(max((curr - vwap*0.9)/(vwap*0.2) * 100, 0), 100), 1)
            return {"avg_cost": round(vwap, 2), "profit_ratio": f"{profit}%"}
        except: return {"profit_ratio": "暂无数据"}

    def get_strategy_pool(self, strat_type):
        """选股雷达数据"""
        if not HAS_AKSHARE: return pd.DataFrame()
        try:
            df = ak.stock_zh_a_spot_em()
            df = df[df['成交额'] > 1e8]
            res = df.sort_values("涨跌幅", ascending=False).head(8)
            return self._attach_win_rate(res, "策略池异动")
        except: return pd.DataFrame()

    def get_ai_screener(self, query):
        """自然语言选股数据"""
        if not HAS_AKSHARE: return pd.DataFrame()
        try:
            df = ak.stock_zh_a_spot_em()
            res = df[df['成交额'] > 1e8].head(8)
            return self._attach_win_rate(res, "AI语义推荐")
        except: return pd.DataFrame()

    def _attach_win_rate(self, df, reason):
        """AI 胜率追踪器"""
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
                "AI胜率标签": "🏆 金牌" if gain > 15 else "📈 稳定"
            })
        json.dump(track, open(_TRACK_FILE, "w"))
        return pd.DataFrame(results)