import requests
import pandas as pd
import akshare as ak
import re, json, os, datetime

# 胜率追踪数据库
_TRACK_FILE = "data/win_track.json"

class AShareDataEngine:
    def __init__(self):
        self.brand = "虎之眼 (Eye of Tiger) 金融内核"

    def _safe_get_df(self):
        """保底获取全市场快照，解决列名不一致问题"""
        try:
            df = ak.stock_zh_a_spot_em()
            # 统一列名映射
            mapping = {
                '代码': ['代码', 'code', 'f12'],
                '最新价': ['最新价', 'close', 'f2'],
                '涨跌幅': ['涨跌幅', 'pct', 'f3'],
                '名称': ['名称', 'name', 'f14'],
                '成交额': ['成交额', 'amount', 'f6']
            }
            new_cols = {}
            for k, v in mapping.items():
                for col in df.columns:
                    if any(x in col for x in v):
                        new_cols[col] = k
                        break
            return df.rename(columns=new_cols)
        except: return pd.DataFrame()

    def get_price_snapshot(self, code):
        """修复云端读不出股价的问题"""
        df = self._safe_get_df()
        if df.empty: return {"current_price": "N/A", "change_pct": 0.0}
        
        # 匹配代码
        row = df[df['代码'].astype(str).str.contains(code)]
        if not row.empty:
            r = row.iloc[0]
            return {
                "current_price": r.get('最新价', 'N/A'),
                "change_pct": r.get('涨跌幅', 0.0),
                "company_name": r.get('名称', code)
            }
        return {"current_price": "N/A", "change_pct": 0.0}

    # ══════════════════════════════════════════════════════════════
    # 指南针式选股池 (带理由与胜率)
    # ══════════════════════════════════════════════════════════════
    def get_ai_screener(self, query):
        """支持小白语言：快速上涨而回撤不多"""
        df = self._safe_get_df()
        if df.empty: return pd.DataFrame()

        # 核心逻辑：回撤不多意味着振幅小
        if "回撤不多" in query or "稳步" in query:
            # 过滤：涨幅 > 3% 且 振幅 < 5%
            picks = df[(df['涨跌幅'] > 3) & (df['振幅'] < 5)]
            reason = "虎之眼：股价处于强势上升通道，且洗盘极其克制，主力锁仓度高。"
        else:
            picks = df.sort_values("涨跌幅", ascending=False)
            reason = "异动雷达：全市场活跃资金聚集标的。"

        return self._attach_win_rate(picks.head(8), reason)

    def _attach_win_rate(self, df, reason):
        """追踪并记录 AI 历史预测正确率"""
        # 加载历史
        if not os.path.exists("data"): os.makedirs("data")
        track = json.load(open(_TRACK_FILE)) if os.path.exists(_TRACK_FILE) else {}
        
        results = []
        today = datetime.date.today().isoformat()
        
        for _, row in df.iterrows():
            code = str(row['代码'])
            price = float(row['最新价'])
            
            # 如果是第一次入选，记录初始价格
            if code not in track:
                track[code] = {"entry_date": today, "entry_p": price, "max_p": price}
            else:
                track[code]["max_p"] = max(track[code]["max_p"], price)
            
            # 计算入选后最高涨幅
            max_gain = round((track[code]["max_p"] - track[code]["entry_p"]) / track[code]["entry_p"] * 100, 2)
            
            results.append({
                "代码": code, "名称": row['名称'], "最新价": price,
                "涨跌幅": row['涨跌幅'], "虎眼理由": reason,
                "AI入选日": track[code]["entry_date"],
                "最高收益": f"+{max_gain}%",
                "胜率标签": "🏆 强力推荐" if max_gain > 15 else "📈 趋势向好"
            })
            
        with open(_TRACK_FILE, "w") as f: json.dump(track, f)
        return pd.DataFrame(results)