"""
龙眼数据引擎 v4.0 — 虎之眼 (Eye of Tiger) 金融内核
修复：
  [F1] scan_radar: 删除不存在的"主力净流入"，改用真实列名
  [F2] _attach_win_rate: 列名自适应 + 文件读写安全关闭
  [F3] get_price_snapshot: data[32]越界 → 改用 data[4]，加长度保护
  [F4] _estimate_chips_cyq: 分母零保护
  [F5] 所有 json 操作改用 with 语句
"""

import requests
import pandas as pd
import re, json, os, datetime

try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False

_TRACK_FILE = "data/win_track.json"

_COL_MAP = {
    "代码":    ["代码", "stock_code"],
    "名称":    ["名称", "stock_name"],
    "最新价":  ["最新价", "current_price"],
    "涨跌幅":  ["涨跌幅", "change_pct", "pct_chg"],
    "成交额":  ["成交额", "amount"],
    "换手率":  ["换手率", "turnover_rate"],
    "PE":      ["动态市盈率", "市盈率-动态", "pe", "PE"],
    "振幅":    ["振幅", "amplitude"],
    "60日涨跌幅": ["60日涨跌幅", "涨跌幅60"],
}


def _safe_float(val, default=0.0):
    try:
        v = float(val)
        return v if v == v else default
    except Exception:
        return default


def _load_track() -> dict:
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(_TRACK_FILE):
        return {}
    try:
        with open(_TRACK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_track(data: dict):
    os.makedirs("data", exist_ok=True)
    try:
        with open(_TRACK_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class AShareDataEngine:
    def __init__(self):
        self.brand = "虎之眼 (Eye of Tiger) 金融内核"

    # ── 代码解析 ────────────────────────────────────────────────────

    def _ensure_code(self, input_val: str) -> str:
        m = re.search(r"\d{6}", str(input_val))
        if m:
            return m.group(0)
        try:
            resp = requests.get(
                f"http://smartbox.gtimg.cn/s3/?q={input_val}&t=all", timeout=2
            )
            cm = re.search(r"\d{6}", resp.text)
            if cm:
                return cm.group(0)
        except Exception:
            pass
        return str(input_val).strip()

    # ── [F3] 股价快照 ───────────────────────────────────────────────

    def get_price_snapshot(self, raw_input: str) -> dict:
        """
        腾讯 qt.gtimg 实时行情
        响应示例: v_s_sh600519="贵州茅台~600519~1800.00~23.50~1.32~..."
        [F3] 原代码用 data[32] 越界 → 改为 data[4] (涨跌幅)，并做长度检查
        """
        code   = self._ensure_code(raw_input)
        market = "sh" if code.startswith(("60", "68", "51")) else "sz"
        _blank = {"current_price": "N/A", "change_pct": 0.0,
                  "company_name": code, "pe_ttm": "N/A", "pb": "N/A",
                  "market_cap": "N/A"}
        try:
            url  = f"http://qt.gtimg.cn/q=s_{market}{code}"
            resp = requests.get(url, timeout=4)
            resp.encoding = "gbk"
            raw  = resp.text
            if '"' not in raw:
                raise ValueError("empty response")
            inner = raw.split('"')[1]
            parts = inner.split("~")
            # [F3] 最少需要 5 个字段才能取到涨跌幅
            if len(parts) < 5:
                raise ValueError(f"short response: {len(parts)} fields")
            name  = parts[1].strip() if len(parts) > 1 else code
            price = _safe_float(parts[3]) if len(parts) > 3 else 0.0
            chg   = _safe_float(parts[4]) if len(parts) > 4 else 0.0  # [F3] 改为 index 4
            if price <= 0:
                raise ValueError("price=0")
            return {
                "current_price": round(price, 2),
                "change_pct":    round(chg,  2),
                "company_name":  name or code,
                "pe_ttm": "N/A", "pb": "N/A", "market_cap": "N/A",
            }
        except Exception:
            pass
        # 备援：东方财富
        return self._get_price_ef(code)

    def _get_price_ef(self, code: str) -> dict:
        """东方财富备援（fltt=1，所有字段 /100）"""
        _blank = {"current_price": "N/A", "change_pct": 0.0,
                  "company_name": code, "pe_ttm": "N/A", "pb": "N/A",
                  "market_cap": "N/A"}
        try:
            secid = f"1.{code}" if code.startswith(("60", "68", "51")) else f"0.{code}"
            data  = requests.get(
                "https://push2.eastmoney.com/api/qt/stock/get",
                params={"secid": secid,
                        "fields": "f43,f58,f60,f116,f162,f167",
                        "ut": "fa5fd1943c7b386f172d6893dbfba10b"},
                timeout=5,
            ).json().get("data") or {}
            if not data:
                return _blank

            def _i(k):
                v = data.get(k)
                if v is None or v in ("-", ""):
                    return None
                try:
                    f = float(v)
                    return f if f != 0 else None
                except Exception:
                    return None

            cp_r, pcp_r = _i("f43"), _i("f60")
            if cp_r is None and pcp_r is None:
                return _blank
            cp  = round((cp_r  or pcp_r) / 100, 2)
            pcp = round((pcp_r or cp_r)  / 100, 2)
            chg = round((cp - pcp) / pcp * 100, 2) if pcp > 0 else 0.0
            pe_r, pb_r, mv_r = _i("f162"), _i("f167"), _i("f116")
            return {
                "current_price": cp,
                "change_pct":    chg,
                "company_name":  data.get("f58") or code,
                "pe_ttm":        round(pe_r / 100, 2) if pe_r and pe_r > 0 else "N/A",
                "pb":            round(pb_r / 100, 2) if pb_r and pb_r > 0 else "N/A",
                "market_cap":    f"{round(mv_r / 1e8, 2)}亿" if mv_r and mv_r > 1e6 else "N/A",
            }
        except Exception:
            return _blank

    # ── 完整上下文 ──────────────────────────────────────────────────

    def get_full_context(self, ticker_full: str, raw_ticker: str) -> dict:
        code = self._ensure_code(raw_ticker)
        snap = self.get_price_snapshot(code)
        ctx  = {
            "symbol":       ticker_full,
            "raw_ticker":   code,
            "brand":        self.brand,
            "price_info": {
                "current_price": snap.get("current_price", "N/A"),
                "change_pct":    snap.get("change_pct", 0.0),
                "pe_ttm":        snap.get("pe_ttm", "N/A"),
                "pb":            snap.get("pb", "N/A"),
            },
            "company_name": snap.get("company_name", code),
            "market_cap":   snap.get("market_cap", "N/A"),
            "industry":     "N/A",
            "macro_rate":   "2.31",
            "lpr_1y":       "3.10",
            "lpr_5y":       "3.60",
            "north_flow":   {"today": "N/A", "5day": "N/A",
                             "20day": "N/A", "direction": "N/A"},
            "fundamentals": {},
        }
        chip = self._estimate_chips_cyq(code)
        ctx["chip_analysis"] = chip
        ctx["profit_ratio"]  = chip.get("profit_ratio", "暂无数据")
        ctx["avg_cost"]      = chip.get("avg_cost", "N/A")
        ctx.update(self._get_macro_rates())
        return ctx

    # ── [F4] 筹码模型 ───────────────────────────────────────────────

    def _estimate_chips_cyq(self, code: str) -> dict:
        _blank = {"profit_ratio": "暂无数据", "avg_cost": "N/A",
                  "vwap_60": "N/A", "chip_lock_signal": "—"}
        if not HAS_AKSHARE:
            return _blank
        try:
            df = ak.stock_zh_a_hist(
                symbol=code, period="daily", adjust="qfq", start_date="20230101"
            )
            if df is None or len(df) < 20:
                return _blank
            cc = next((c for c in ["收盘", "close", "Close"] if c in df.columns), None)
            cv = next((c for c in ["成交量", "volume", "Volume"] if c in df.columns), None)
            if not cc or not cv:
                return _blank
            df = df.copy()
            df["_c"] = pd.to_numeric(df[cc], errors="coerce")
            df["_v"] = pd.to_numeric(df[cv], errors="coerce")
            df.dropna(subset=["_c", "_v"], inplace=True)
            df60    = df.tail(60)
            vol_sum = df60["_v"].sum()
            if vol_sum == 0:                          # [F4] 分母零保护
                return _blank
            vwap60  = float((df60["_c"] * df60["_v"]).sum() / vol_sum)
            curr    = float(df["_c"].iloc[-1])
            spread  = vwap60 * 0.20
            if spread == 0:
                return _blank
            profit  = round(min(max((curr - vwap60 * 0.85) / spread * 100, 0), 100), 1)
            df5     = df.tail(5)
            lock    = (float(df5["_c"].iloc[-1]) > float(df5["_c"].iloc[0])
                       and float(df5["_v"].iloc[-1]) < float(df5["_v"].mean()) * 0.85)
            return {
                "avg_cost":         round(vwap60, 2),
                "vwap_60":          round(vwap60, 2),
                "profit_ratio":     f"{profit}%",
                "chip_lock_signal": "⚡ 主力锁仓" if lock else "无明显锁仓",
                "above_vwap60":     curr > vwap60,
            }
        except Exception:
            return _blank

    # ── 宏观利率 ────────────────────────────────────────────────────

    def _get_macro_rates(self) -> dict:
        rates = {"macro_rate": "2.31", "lpr_1y": "3.10", "lpr_5y": "3.60"}
        if not HAS_AKSHARE:
            return rates
        try:
            df = ak.bond_zh_us_rate(start_date="20250101")
            if df is not None and not df.empty:
                col = df.columns[1]
                for i in range(len(df) - 1, -1, -1):
                    v = _safe_float(df.iloc[i][col], None)
                    if v and v > 0:
                        rates["macro_rate"] = str(round(v, 2))
                        break
        except Exception:
            pass
        return rates

    # ── [F1] 选股雷达 ───────────────────────────────────────────────

    def scan_radar(self, mode: str = "异动扫描", query: str = "") -> pd.DataFrame:
        """
        [F1] 彻底删除不存在的"主力净流入"列
             改用 stock_zh_a_spot_em 真实可用的列
        """
        if not HAS_AKSHARE:
            return pd.DataFrame()
        try:
            df = ak.stock_zh_a_spot_em()
        except Exception:
            return pd.DataFrame()

        df = self._normalize_spot(df)
        # 基础过滤
        df = df[pd.to_numeric(df["成交额"], errors="coerce").fillna(0) > 1e8]
        df = df[~df["名称"].str.contains("ST|退|\\*", na=False, regex=True)]
        df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce").fillna(0)
        df["换手率"] = pd.to_numeric(df["换手率"], errors="coerce").fillna(0)

        if mode == "资金净流入":
            # [F1] 用成交额×涨跌幅正值估算资金净流入（代替不存在的列）
            df["_flow"] = (
                pd.to_numeric(df["成交额"], errors="coerce").fillna(0)
                * df["涨跌幅"].clip(lower=0)
            )
            res    = df.nlargest(12, "_flow")
            reason = "活跃资金（成交额×涨幅）居前"

        elif mode == "自然语言模式" and query.strip():
            res, reason = self._semantic_filter(df, query)

        else:  # 异动扫描
            df["_score"] = df["涨跌幅"] * 0.6 + df["换手率"] * 0.4
            res    = df.nlargest(12, "_score")
            reason = "今日异动强势"

        return self._attach_win_rate(res, reason)

    def _semantic_filter(self, df: pd.DataFrame, query: str):
        rules = [
            (["回撤小", "稳", "稳健", "白马", "长线"],
             lambda d: d[(d["涨跌幅"] > 0) & (d["振幅"].fillna(99) < 4)].sort_values("涨跌幅", ascending=False),
             "低回撤稳健"),
            (["涨停", "打板", "连板"],
             lambda d: d[d["涨跌幅"] > 9.4].sort_values("换手率", ascending=False),
             "涨停强势"),
            (["低估", "低PE", "价值", "蓝筹"],
             lambda d: d[(d["PE"].between(3, 20)) & (d["涨跌幅"] > 0)].sort_values("PE"),
             "低估值价值"),
            (["缩量", "锁仓"],
             lambda d: d[(d["涨跌幅"] > 2) & (d["换手率"] < 2)].sort_values("涨跌幅", ascending=False),
             "缩量锁仓"),
            (["放量", "量价", "爆量"],
             lambda d: d[(d["涨跌幅"] > 3) & (d["换手率"] > 5)].sort_values("换手率", ascending=False),
             "放量突破"),
            (["超跌", "反弹"],
             lambda d: d[d["涨跌幅"] > 3].sort_values("涨跌幅", ascending=False),
             "强势反弹"),
        ]
        for keywords, fn, label in rules:
            if any(kw in query for kw in keywords):
                try:
                    result = fn(df)
                    if not result.empty:
                        return result, label
                except Exception:
                    pass
        return df.sort_values("涨跌幅", ascending=False), "综合强势"

    def _normalize_spot(self, df: pd.DataFrame) -> pd.DataFrame:
        """列名标准化"""
        rename = {}
        for dst, srcs in _COL_MAP.items():
            for s in srcs:
                if s in df.columns and dst not in df.columns:
                    rename[s] = dst
                    break
        df = df.rename(columns=rename)
        for col in ["PE", "振幅", "60日涨跌幅", "换手率", "成交额", "最新价"]:
            if col not in df.columns:
                df[col] = float("nan")
            else:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    # ── [F2] 胜率追踪 ───────────────────────────────────────────────

    def _attach_win_rate(self, df: pd.DataFrame, reason: str) -> pd.DataFrame:
        """[F2] 列名自适应 + with 语句安全文件操作"""
        if df is None or df.empty:
            return pd.DataFrame()

        code_col  = next((c for c in ["代码"] if c in df.columns), None)
        name_col  = next((c for c in ["名称"] if c in df.columns), None)
        price_col = next((c for c in ["最新价", "current_price"] if c in df.columns), None)

        if not code_col:
            return pd.DataFrame()

        track   = _load_track()
        today   = datetime.date.today().isoformat()
        results = []

        for _, row in df.head(12).iterrows():
            code  = str(row.get(code_col, "")).strip()
            name  = str(row.get(name_col, code)) if name_col else code
            price = _safe_float(row.get(price_col, 0) if price_col else 0)
            chg   = _safe_float(row.get("涨跌幅", 0))
            if not code:
                continue
            if code not in track:
                track[code] = {"date": today, "entry": price, "max": price}
            elif price > 0 and price > track[code].get("max", 0):
                track[code]["max"] = price

            entry = _safe_float(track[code].get("entry", price), price) or price
            max_p = _safe_float(track[code].get("max",   price), price)
            gain  = round((max_p - entry) / entry * 100, 1) if entry > 0 else 0.0

            results.append({
                "代码":     code,
                "名称":     name,
                "最新价":   price,
                "涨跌幅":   chg,
                "理由":     reason,
                "AI入选日": track[code]["date"],
                "最高涨幅": f"+{gain}%" if gain >= 0 else f"{gain}%",
                "AI胜率":   (
                    f"🏆 +{gain}%" if gain >= 20 else
                    f"✅ +{gain}%" if gain >= 10 else
                    f"📈 +{gain}%" if gain >= 3  else
                    f"➖ {gain}%"
                ),
            })

        _save_track(track)
        return pd.DataFrame(results)
