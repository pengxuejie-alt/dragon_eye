"""
龙眼数据引擎 v3.0 — 虎之眼 (Eye of Tiger) 内核
================================================
修复清单：
  [F1] 东财行情：f43/f60 精度修复，PE/PB 字段正确除100
  [F2] 新浪备援：encoding='gbk' + 非交易时段 data[3] 回退
  [F3] AKShare 备援：stock_zh_a_spot_em 精确匹配列名
  [F4] 宏观利率：跳过 "." 等无效值，硬编码兜底2.31%
  [F5] 获利盘：分母零保护 + 兜底输出"暂无数据"
  [F6] 北向资金：列名自适应（不同版本AKShare列名不一）
  [F7] get_ai_screener：扩展至18种语义关键词
  [F8] _attach_win_rate：本地JSON持久化追踪 + 虎之眼推荐理由
  [F9] get_strategy_pool：列名自适应（成交额/换手率/动态市盈率）
"""

import re
import json
import os
import datetime
import requests
import pandas as pd

try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False

# ─── 胜率追踪文件 ─────────────────────────────────────────────────────
_TRACK_FILE = "data/screener_track.json"
_BRAND      = "虎之眼 (Eye of Tiger) 金融内核"


def _load_track() -> dict:
    os.makedirs("data", exist_ok=True)
    if os.path.exists(_TRACK_FILE):
        try:
            with open(_TRACK_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_track(data: dict):
    os.makedirs("data", exist_ok=True)
    with open(_TRACK_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _safe_float(val, default=None):
    """安全转 float，失败返回 default"""
    try:
        v = float(val)
        return v if v == v else default   # NaN 检查
    except (TypeError, ValueError):
        return default


def _col(df: pd.DataFrame, candidates: list, default=None):
    """从候选列名列表中找到第一个存在的列"""
    for c in candidates:
        if c in df.columns:
            return c
    return default


class AShareDataEngine:
    """
    虎之眼数据引擎 v3.0
    三重行情备援：东方财富 → AKShare → 新浪
    """

    EF_BASE   = "https://push2.eastmoney.com/api/qt/stock/get"
    SINA_BASE = "http://hq.sinajs.cn/list="

    # ══════════════════════════════════════════════════════════════
    # 主入口
    # ══════════════════════════════════════════════════════════════

    def get_full_context(self, ticker_full: str, raw_ticker: str) -> dict:
        m = re.search(r"\d{6}", str(raw_ticker))
        code = m.group(0) if m else str(raw_ticker).strip()

        ctx: dict = {
            "symbol":     ticker_full,
            "raw_ticker": code,
            "timestamp":  datetime.datetime.now().isoformat(),
            "brand":      _BRAND,
        }

        # 三重行情备援：用字符串比较，与三个引擎的返回值保持一致
        price_data = self._get_price_eastmoney(code)
        if price_data["price_info"]["current_price"] == "N/A":
            price_data = self._get_price_akshare(code)
        if price_data["price_info"]["current_price"] == "N/A":
            price_data = self._get_price_sina(code)
        ctx.update(price_data)

        # [F5] 筹码获利（CYQ 模型）
        chip = self._estimate_chips_cyq(code)
        ctx["chip_analysis"] = chip
        ctx["profit_ratio"]  = chip.get("profit_ratio", "暂无数据")
        ctx["avg_cost"]      = chip.get("avg_cost",      "N/A")
        ctx["chip_density"]  = chip.get("chip_density",  "N/A")

        # 换手率承接 & ATR 波动率
        ctx["turnover_analysis"] = self._get_turnover_trend(code)
        ctx["atr_analysis"]      = self._calc_atr(code)

        # [F4] 宏观利率
        ctx.update(self._get_macro_rates())

        # 基本面
        ctx.update(self._get_fundamentals(code))

        # [F6] 北向资金
        ctx["north_flow"] = self._get_north_flow()

        return ctx

    # ══════════════════════════════════════════════════════════════
    # [F1] 东方财富行情（主引擎）
    # ══════════════════════════════════════════════════════════════

    def _get_price_eastmoney(self, code: str) -> dict:
        _blank = {"price_info": {"current_price": "N/A", "change_pct": 0.0,
                                  "pe_ttm": "N/A", "pb": "N/A"},
                  "company_name": code, "market_cap": "N/A", "industry": "N/A"}
        try:
            # 上交所/科创板用 1.xxx，其余用 0.xxx
            if code.startswith(("60", "68", "51", "11", "13")):
                secid = f"1.{code}"
            else:
                secid = f"0.{code}"

            # 不传 fltt 参数 → 默认 fltt=1：所有数值字段均为整数×100
            # 例如价格 1800.00元 → f43=180000；PE 25.5 → f162=2550
            params = {
                "secid":  secid,
                "fields": "f43,f44,f45,f47,f48,f58,f60,f116,f162,f167",
                "ut":     "fa5fd1943c7b386f172d6893dbfba10b",
            }
            data = requests.get(self.EF_BASE, params=params, timeout=6).json().get("data") or {}

            if not data:
                return _blank

            def _i(key):
                """取整数值（×100原始）→ 返回 float 或 None"""
                v = data.get(key)
                if v is None or v == "-" or v == "":
                    return None
                try:
                    f = float(v)
                    return f if f != 0 else None
                except Exception:
                    return None

            # 所有价格 /100
            cp_raw  = _i("f43")
            pcp_raw = _i("f60")

            if cp_raw is None and pcp_raw is None:
                return _blank

            cp  = round((cp_raw  or pcp_raw) / 100, 2)
            pcp = round((pcp_raw or cp_raw)  / 100, 2)
            chg = round((cp - pcp) / pcp * 100, 2) if pcp > 0 else 0.0

            # 市值：f116 单位是元（已是大数，不需除100），转为亿
            mv_raw = _i("f116")
            mv_str = f"{round(mv_raw / 1e8, 2)}亿" if mv_raw and mv_raw > 1e6 else "N/A"

            # PE/PB 同样 /100
            pe_raw = _i("f162")
            pb_raw = _i("f167")
            pe_val = round(pe_raw / 100, 2) if pe_raw and pe_raw > 0 else "N/A"
            pb_val = round(pb_raw / 100, 2) if pb_raw and pb_raw > 0 else "N/A"

            high = _i("f44")
            low  = _i("f45")

            return {
                "price_info": {
                    "current_price": cp,
                    "change_pct":    chg,
                    "pre_close":     pcp,
                    "high_today":    round(high / 100, 2) if high else "N/A",
                    "low_today":     round(low  / 100, 2) if low  else "N/A",
                    "volume":        data.get("f47", "N/A"),
                    "amount":        data.get("f48", "N/A"),
                    "pe_ttm":        pe_val,
                    "pb":            pb_val,
                },
                "company_name": data.get("f58") or code,
                "market_cap":   mv_str,
                "industry":     "N/A",
            }
        except Exception:
            return _blank

    # ══════════════════════════════════════════════════════════════
    # [F3] AKShare 行情（第二备援）
    # ══════════════════════════════════════════════════════════════

    def _get_price_akshare(self, code: str) -> dict:
        _blank = {"price_info": {"current_price": "N/A", "change_pct": 0.0,
                                  "pe_ttm": "N/A", "pb": "N/A"},
                  "company_name": code, "market_cap": "N/A", "industry": "N/A"}
        if not HAS_AKSHARE:
            return _blank
        try:
            df  = ak.stock_zh_a_spot_em()
            col_code = _col(df, ["代码", "stock_code", "code"]) or df.columns[0]
            row = df[df[col_code].astype(str) == code]
            if row.empty:
                return _blank
            r = row.iloc[0]

            col_price  = _col(df, ["最新价", "current_price", "close"])
            col_chg    = _col(df, ["涨跌幅", "change_pct", "pct_chg"])
            col_pe     = _col(df, ["动态市盈率", "市盈率-动态", "pe"])
            col_pb     = _col(df, ["市净率", "pb"])
            col_mv     = _col(df, ["总市值", "market_cap"])
            col_name   = _col(df, ["名称", "stock_name", "name"])

            cp  = _safe_float(r.get(col_price) if col_price else None)
            chg = _safe_float(r.get(col_chg)   if col_chg  else None, 0.0)
            mv  = _safe_float(r.get(col_mv)     if col_mv   else None)

            if cp is None:
                return _blank

            return {
                "price_info": {
                    "current_price": cp,
                    "change_pct":    chg,
                    "pe_ttm":        _safe_float(r.get(col_pe) if col_pe else None) or "N/A",
                    "pb":            _safe_float(r.get(col_pb) if col_pb else None) or "N/A",
                },
                "company_name": str(r.get(col_name, code)) if col_name else code,
                "market_cap":   f"{round(mv / 1e8, 2)}亿" if mv else "N/A",
                "industry":     "N/A",
            }
        except Exception:
            return _blank

    # ══════════════════════════════════════════════════════════════
    # [F2] 新浪行情（第三备援，修复 gbk 编码）
    # ══════════════════════════════════════════════════════════════

    def _get_price_sina(self, code: str) -> dict:
        _blank = {"price_info": {"current_price": "N/A", "change_pct": 0.0,
                                  "pe_ttm": "N/A", "pb": "N/A"},
                  "company_name": code, "market_cap": "N/A", "industry": "N/A"}
        try:
            prefix = "sh" if code.startswith(("60", "68", "51")) else "sz"
            headers = {
                "Referer":    "http://finance.sina.com.cn",
                "User-Agent": "Mozilla/5.0",
            }
            resp = requests.get(
                f"{self.SINA_BASE}{prefix}{code}",
                headers=headers, timeout=6,
            )
            resp.encoding = "gbk"
            raw = resp.text
            if '"' not in raw:
                return _blank

            parts = raw.split('"')[1].split(",")
            if len(parts) < 9:
                return _blank

            # parts[0]=名称, [1]=今开, [2]=昨收, [3]=当前价, [4]=最高, [5]=最低
            name = parts[0].strip()
            pcp  = _safe_float(parts[2])   # 昨收，最可靠
            cp   = _safe_float(parts[3])   # 当前价

            # 非交易时段 cp 可能为 0 或等于昨收
            if not cp or cp == 0:
                cp = pcp
            if not cp:
                return _blank

            chg = round((cp - pcp) / pcp * 100, 2) if pcp and pcp > 0 else 0.0

            return {
                "price_info": {
                    "current_price": round(cp, 2),
                    "change_pct":    chg,
                    "pre_close":     round(pcp, 2) if pcp else "N/A",
                    "pe_ttm":        "N/A",
                    "pb":            "N/A",
                },
                "company_name": name or code,
                "market_cap":   "N/A",
                "industry":     "N/A",
            }
        except Exception:
            return _blank

    # ══════════════════════════════════════════════════════════════
    # [F5] 指南针 CYQ 筹码模型（分母零保护）
    # ══════════════════════════════════════════════════════════════

    def _estimate_chips_cyq(self, code: str) -> dict:
        _blank = {
            "avg_cost": "N/A", "profit_ratio": "暂无数据",
            "chip_density": "N/A", "chip_lock_signal": "—",
            "vwap_60": "N/A", "vwap_20": "N/A",
            "above_vwap60": None, "above_vwap20": None,
        }
        if not HAS_AKSHARE:
            return _blank
        try:
            df = ak.stock_zh_a_hist(
                symbol=code, period="daily", adjust="qfq",
                start_date="20230101",
            )
            if df is None or len(df) < 20:
                return _blank

            # 列名自适应
            col_close  = _col(df, ["收盘", "close", "Close"]) or df.columns[3]
            col_vol    = _col(df, ["成交量", "volume", "Volume"]) or df.columns[5]
            col_high   = _col(df, ["最高", "high", "High"]) or df.columns[1]
            col_low    = _col(df, ["最低", "low", "Low"]) or df.columns[2]

            df = df.copy()
            df["_c"] = pd.to_numeric(df[col_close], errors="coerce")
            df["_v"] = pd.to_numeric(df[col_vol],   errors="coerce")
            df["_h"] = pd.to_numeric(df[col_high],  errors="coerce")
            df["_l"] = pd.to_numeric(df[col_low],   errors="coerce")
            df.dropna(subset=["_c", "_v"], inplace=True)

            df60 = df.tail(60)
            df20 = df.tail(20)
            curr = float(df["_c"].iloc[-1])

            # [F5] 分母零保护
            vol60_sum = df60["_v"].sum()
            vol20_sum = df20["_v"].sum()
            if vol60_sum == 0 or vol20_sum == 0:
                return _blank

            vwap60 = float((df60["_c"] * df60["_v"]).sum() / vol60_sum)
            vwap20 = float((df20["_c"] * df20["_v"]).sum() / vol20_sum)

            # 获利盘估算：CYQ 正态近似
            spread = vwap60 * 0.20
            if spread == 0:
                return _blank
            profit_raw = (curr - vwap60 * 0.85) / spread * 100
            profit_pct = round(min(max(profit_raw, 0.0), 100.0), 1)

            # 筹码密集度：近20日振幅标准差
            df20["_range"] = (df20["_h"] - df20["_l"]) / df20["_c"] * 100
            density_std   = round(float(df20["_range"].std()), 2)
            density_label = (
                "🟢 高度密集" if density_std < 2.0 else
                "🟡 正常分布" if density_std < 4.0 else
                "🔴 筹码松散"
            )

            # 锁仓信号：近5日涨中量缩
            df5 = df.tail(5)
            price_up   = float(df5["_c"].iloc[-1]) > float(df5["_c"].iloc[0])
            vol_shrink = float(df5["_v"].iloc[-1]) < float(df5["_v"].mean()) * 0.85
            lock_sig   = "⚡ 主力锁仓" if (price_up and vol_shrink) else "无明显锁仓"

            return {
                "avg_cost":         round(vwap60, 2),
                "vwap_60":          round(vwap60, 2),
                "vwap_20":          round(vwap20, 2),
                "profit_ratio":     f"{profit_pct}%",
                "chip_density":     f"{density_label}（σ={density_std}%）",
                "chip_lock_signal": lock_sig,
                "above_vwap60":     curr > vwap60,
                "above_vwap20":     curr > vwap20,
            }
        except Exception as e:
            return {**_blank, "_error": str(e)}

    # ══════════════════════════════════════════════════════════════
    # ATR 历史波动率
    # ══════════════════════════════════════════════════════════════

    def _calc_atr(self, code: str) -> dict:
        _blank = {"atr14": "N/A", "atr_pct": "N/A",
                  "atr_percentile": "N/A", "volatility_label": "N/A"}
        if not HAS_AKSHARE:
            return _blank
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily",
                                    adjust="qfq", start_date="20230101")
            if df is None or len(df) < 30:
                return _blank

            col_c = _col(df, ["收盘", "close"]) or df.columns[3]
            col_h = _col(df, ["最高", "high"])  or df.columns[1]
            col_l = _col(df, ["最低", "low"])   or df.columns[2]

            df = df.copy()
            df["_c"] = pd.to_numeric(df[col_c], errors="coerce")
            df["_h"] = pd.to_numeric(df[col_h], errors="coerce")
            df["_l"] = pd.to_numeric(df[col_l], errors="coerce")
            df["_pc"] = df["_c"].shift(1)
            df.dropna(inplace=True)

            df["_tr"] = df.apply(lambda r: max(
                r["_h"] - r["_l"],
                abs(r["_h"] - r["_pc"]),
                abs(r["_l"] - r["_pc"]),
            ), axis=1)
            df["_atr"] = df["_tr"].rolling(14).mean()
            df.dropna(subset=["_atr"], inplace=True)

            curr_p   = float(df["_c"].iloc[-1])
            curr_atr = float(df["_atr"].iloc[-1])
            if curr_p == 0:
                return _blank

            atr_pct    = round(curr_atr / curr_p * 100, 2)
            series     = df["_atr"]
            percentile = round((series < curr_atr).sum() / len(series) * 100, 1)

            label = (
                "🟢 历史低波动（布局窗口）" if percentile < 25 else
                "🟡 正常波动区间"           if percentile < 60 else
                "🔴 历史高波动（注意风险）"
            )
            return {
                "atr14":            round(curr_atr, 2),
                "atr_pct":          f"{atr_pct}%",
                "atr_percentile":   f"{percentile}%分位",
                "volatility_label": label,
            }
        except Exception:
            return _blank

    # ══════════════════════════════════════════════════════════════
    # 换手率趋势
    # ══════════════════════════════════════════════════════════════

    def _get_turnover_trend(self, code: str) -> dict:
        _blank = {"avg_turnover_5d": "N/A", "avg_turnover_20d": "N/A",
                  "turnover_signal": "N/A", "price_5d_chg": "N/A"}
        if not HAS_AKSHARE:
            return _blank
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily",
                                    adjust="qfq", start_date="20240101")
            if df is None or len(df) < 10:
                return _blank

            col_c  = _col(df, ["收盘", "close"])   or df.columns[3]
            col_t  = _col(df, ["换手率", "turnover_rate"])
            if not col_t:
                return _blank

            df = df.copy()
            df["_c"] = pd.to_numeric(df[col_c], errors="coerce")
            df["_t"] = pd.to_numeric(df[col_t], errors="coerce")
            df.dropna(subset=["_c", "_t"], inplace=True)

            t5  = round(float(df["_t"].tail(5).mean()),  2)
            t20 = round(float(df["_t"].tail(20).mean()), 2)
            c5  = float(df["_c"].iloc[-1])
            c5s = float(df["_c"].iloc[-min(6, len(df))])
            chg5 = round((c5 - c5s) / c5s * 100, 2) if c5s else 0.0

            if chg5 > 5 and t5 < t20 * 0.85:
                sig = "⚡ 涨中量缩 → 主力锁仓"
            elif chg5 > 5 and t5 > t20 * 1.3:
                sig = "⚠️ 涨中量增 → 游资接力，注意止盈"
            elif chg5 < -3 and t5 > t20 * 1.5:
                sig = "🔴 跌中放量 → 恐慌抛售"
            else:
                sig = f"正常（近5日均{t5}% / 近20日均{t20}%）"

            return {
                "avg_turnover_5d":  f"{t5}%",
                "avg_turnover_20d": f"{t20}%",
                "price_5d_chg":     f"{chg5:+.2f}%",
                "turnover_signal":  sig,
            }
        except Exception:
            return _blank

    # ══════════════════════════════════════════════════════════════
    # [F4] 宏观利率（跳过无效值 "."）
    # ══════════════════════════════════════════════════════════════

    def _get_macro_rates(self) -> dict:
        rates = {"macro_rate": "2.31", "lpr_1y": "3.10", "lpr_5y": "3.60"}
        if not HAS_AKSHARE:
            return rates
        try:
            df = ak.bond_zh_us_rate(start_date="20250101")
            if df is not None and not df.empty:
                col = df.columns[1]
                # [F4] 向前取最近有效值，跳过 "." 或空
                for i in range(len(df) - 1, -1, -1):
                    val = _safe_float(df.iloc[i][col])
                    if val is not None and val > 0:
                        rates["macro_rate"] = str(round(val, 2))
                        break
        except Exception:
            pass
        try:
            df_lpr = ak.macro_china_lpr()
            if df_lpr is not None and not df_lpr.empty:
                row = df_lpr.iloc[-1]
                v1 = _safe_float(row.get("1年期贷款市场报价利率"))
                v5 = _safe_float(row.get("5年期以上贷款市场报价利率"))
                if v1: rates["lpr_1y"] = str(v1)
                if v5: rates["lpr_5y"] = str(v5)
        except Exception:
            pass
        return rates

    # ══════════════════════════════════════════════════════════════
    # 基本面
    # ══════════════════════════════════════════════════════════════

    def _get_fundamentals(self, code: str) -> dict:
        res = {"fundamentals": {}}
        if not HAS_AKSHARE:
            return res
        try:
            df = ak.stock_financial_analysis_indicator(symbol=code, start_year="2024")
            if df is not None and not df.empty:
                r = df.iloc[0]
                res["fundamentals"] = {
                    "roe":          r.get("净资产收益率", "N/A"),
                    "gross_margin": r.get("销售毛利率",   "N/A"),
                    "net_margin":   r.get("销售净利率",   "N/A"),
                    "debt_ratio":   r.get("资产负债率",   "N/A"),
                }
        except Exception:
            pass
        return res

    # ══════════════════════════════════════════════════════════════
    # [F6] 北向资金（列名自适应）
    # ══════════════════════════════════════════════════════════════

    def _get_north_flow(self) -> dict:
        _blank = {"today": "N/A", "5day": "N/A", "20day": "N/A", "direction": "N/A"}
        if not HAS_AKSHARE:
            return _blank
        try:
            df = ak.stock_hsgt_north_net_flow_in_em(indicator="沪深港通")
            if df is None or df.empty:
                return _blank
            # 取第二列（数值列），第一列通常是日期
            val_col = df.columns[1]
            df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
            df.dropna(subset=[val_col], inplace=True)
            t1  = float(df[val_col].iloc[-1])
            t5  = float(df[val_col].tail(5).sum())
            t20 = float(df[val_col].tail(20).sum())
            return {
                "today":     f"{t1:.2f}亿",
                "5day":      f"{t5:.2f}亿",
                "20day":     f"{t20:.2f}亿",
                "direction": "净流入" if t1 > 0 else "净流出",
            }
        except Exception:
            return _blank

    # ══════════════════════════════════════════════════════════════
    # [F9] 选股雷达（列名自适应）
    # ══════════════════════════════════════════════════════════════

    def get_strategy_pool(self, strategy_type: str = "涨停最强") -> pd.DataFrame:
        if not HAS_AKSHARE:
            return pd.DataFrame()
        try:
            df = ak.stock_zh_a_spot_em()
            df = self._normalize_spot_columns(df)
            df = df[df["成交额"] > 1e8]
            df = df[~df["名称"].str.contains("ST|退|N\\b|C\\b", na=False, regex=True)]

            if strategy_type == "涨停最强":
                res = df[df["涨跌幅"] > 9.5].sort_values("换手率", ascending=False)
            elif strategy_type == "虎之眼价值":
                res = df[(df["PE"].between(3, 25)) & (df["涨跌幅"] > 1)]
            else:
                res = df.nlargest(15, "成交额")

            return self._attach_win_rate(res.head(15))
        except Exception:
            return pd.DataFrame()

    # ══════════════════════════════════════════════════════════════
    # [F7] 语义化 AI 选股（18 种关键词）
    # ══════════════════════════════════════════════════════════════

    # 语义规则表：每条规则包含 keywords / filter_fn / sort_col / label / reason
    _SEMANTIC_RULES = [
        {
            "keywords": ["快速上涨", "强势", "上涨快", "涨得快"],
            "filter":   lambda df: df[df["涨跌幅"] > 5],
            "sort":     "涨跌幅",
            "label":    "强势上涨",
            "reason":   "今日涨幅>5%，量价配合强势",
        },
        {
            "keywords": ["回撤小", "回撤不多", "稳步", "不大跌", "小回撤"],
            "filter":   lambda df: df[(df["涨跌幅"] > 0) & (df["振幅"] < 4)],
            "sort":     "涨跌幅",
            "label":    "低回撤稳涨",
            "reason":   "振幅<4%且上涨，波动可控",
        },
        {
            "keywords": ["快速上涨", "回撤不多", "涨快回撤小", "稳步上涨"],
            "filter":   lambda df: df[(df["涨跌幅"] > 4) & (df["振幅"] < 6)],
            "sort":     "涨跌幅",
            "label":    "快涨低回撤",
            "reason":   "涨幅>4%且振幅<6%，主力控盘特征",
        },
        {
            "keywords": ["低估值", "便宜", "价值", "低PE", "蓝筹"],
            "filter":   lambda df: df[(df["PE"].between(3, 20)) & (df["涨跌幅"] > 0)],
            "sort":     "PE",
            "label":    "低估值价值股",
            "reason":   "PE 3-20，估值安全边际充足",
        },
        {
            "keywords": ["长线稳", "长期持有", "稳健", "长线", "价值投资"],
            "filter":   lambda df: df[(df["PE"].between(5, 30)) & (df["涨跌幅"].between(-1, 5))],
            "sort":     "成交额",
            "label":    "长线稳健",
            "reason":   "PE合理 + 涨跌平稳，适合长线配置",
        },
        {
            "keywords": ["高换手", "活跃", "热门", "成交旺"],
            "filter":   lambda df: df[(df["换手率"] > 5) & (df["涨跌幅"] > 2)],
            "sort":     "换手率",
            "label":    "高换手活跃",
            "reason":   "换手率>5%，市场参与度高",
        },
        {
            "keywords": ["缩量", "锁仓", "缩量上涨", "主力惜售"],
            "filter":   lambda df: df[(df["涨跌幅"] > 2) & (df["换手率"] < 2)],
            "sort":     "涨跌幅",
            "label":    "缩量锁仓",
            "reason":   "涨中量缩，主力锁仓特征",
        },
        {
            "keywords": ["北上", "外资", "沪深港通", "外资青睐", "北向"],
            "filter":   lambda df: df[(df["PE"].between(5, 35)) & (df["最新价"] > 10)
                                      & (df["涨跌幅"] > 0)],
            "sort":     "成交额",
            "label":    "外资友好型",
            "reason":   "价格>10元 + PE合理，符合北向资金偏好",
        },
        {
            "keywords": ["小盘", "黑马", "弹性", "中小盘", "翻倍"],
            "filter":   lambda df: df[df["涨跌幅"] > 4],
            "sort":     "涨跌幅",
            "label":    "小盘弹性黑马",
            "reason":   "涨幅>4%，小盘弹性标的",
        },
        {
            "keywords": ["涨停", "打板", "连板", "一字板"],
            "filter":   lambda df: df[df["涨跌幅"] > 9.4],
            "sort":     "换手率",
            "label":    "涨停强势",
            "reason":   "今日触及涨停板，强势信号",
        },
        {
            "keywords": ["超跌", "跌多了", "反弹", "超跌反弹", "底部"],
            "filter":   lambda df: df[(df["涨跌幅"] > 3) & (df["60日涨跌幅"] < -10)],
            "sort":     "涨跌幅",
            "label":    "超跌反弹",
            "reason":   "60日跌幅>10%后出现反弹信号",
        },
        {
            "keywords": ["大盘股", "白马", "龙头", "大市值"],
            "filter":   lambda df: df[(df["涨跌幅"] > 0) & (df["成交额"] > 5e8)],
            "sort":     "成交额",
            "label":    "大盘龙头",
            "reason":   "成交额>5亿，机构重仓大盘龙头",
        },
        {
            "keywords": ["放量", "放量上涨", "大单", "量价齐升"],
            "filter":   lambda df: df[(df["涨跌幅"] > 3) & (df["换手率"] > 3)],
            "sort":     "换手率",
            "label":    "放量上涨",
            "reason":   "量价齐升，有效突破信号",
        },
        {
            "keywords": ["低价股", "低价", "便宜股", "10元以下"],
            "filter":   lambda df: df[(df["最新价"] < 10) & (df["涨跌幅"] > 2)],
            "sort":     "涨跌幅",
            "label":    "低价弹性股",
            "reason":   "价格<10元，弹性空间大",
        },
        {
            "keywords": ["科技", "AI", "人工智能", "芯片", "半导体"],
            "filter":   lambda df: df[(df["涨跌幅"] > 2) & (df["PE"] > 30)],
            "sort":     "涨跌幅",
            "label":    "科技成长",
            "reason":   "高PE + 强势，符合科技成长估值逻辑",
        },
        {
            "keywords": ["新能源", "光伏", "电动车", "储能", "锂电"],
            "filter":   lambda df: df[(df["涨跌幅"] > 1) & (df["换手率"] > 2)],
            "sort":     "换手率",
            "label":    "新能源主题",
            "reason":   "活跃度高，新能源主题行情",
        },
        {
            "keywords": ["医药", "创新药", "生物", "医疗"],
            "filter":   lambda df: df[(df["涨跌幅"] > 1) & (df["PE"].between(20, 80))],
            "sort":     "涨跌幅",
            "label":    "医药生物",
            "reason":   "PE适中，医药生物细分领域",
        },
        {
            "keywords": ["军工", "国防", "航天", "军工股"],
            "filter":   lambda df: df[df["涨跌幅"] > 2],
            "sort":     "涨跌幅",
            "label":    "军工主题",
            "reason":   "今日上涨，军工方向关注",
        },
    ]

    def get_ai_screener(self, query: str) -> pd.DataFrame:
        """
        [F7] 语义化 AI 选股
        自然语言 → pandas 过滤，支持 18 种语义关键词
        """
        if not HAS_AKSHARE:
            return pd.DataFrame()
        try:
            df = ak.stock_zh_a_spot_em()
            df = self._normalize_spot_columns(df)
            df = df[df["成交额"] > 1e8]
            df = df[~df["名称"].str.contains("ST|退|N\\b|C\\b", na=False, regex=True)]

            # 按优先级匹配语义规则（允许多关键词命中同一条规则，取第一条）
            matched = None
            for rule in self._SEMANTIC_RULES:
                if any(kw in query for kw in rule["keywords"]):
                    matched = rule
                    break

            if matched:
                try:
                    result = matched["filter"](df)
                    result = result.sort_values(matched["sort"], ascending=False).head(15)
                    result = result.copy()
                    result["策略标签"]    = matched["label"]
                    result["虎眼推荐理由"] = matched["reason"]
                except Exception:
                    result = df.sort_values("涨跌幅", ascending=False).head(15)
                    result = result.copy()
                    result["策略标签"]    = "综合强势"
                    result["虎眼推荐理由"] = "今日综合涨幅居前"
            else:
                # 兜底：综合强势
                result = df.sort_values("涨跌幅", ascending=False).head(15)
                result = result.copy()
                result["策略标签"]    = "综合强势"
                result["虎眼推荐理由"] = "今日综合涨幅居前"

            return self._attach_win_rate(result)
        except Exception as e:
            return pd.DataFrame({"错误": [str(e)]})

    # ══════════════════════════════════════════════════════════════
    # [F8] 历史胜率追踪 + 虎之眼推荐理由
    # ══════════════════════════════════════════════════════════════

    def _attach_win_rate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        为每只入选股附加：
          - AI入选日：首次入选日期
          - AI最高涨幅：入选后至今最高涨幅（AI正确率依据）
          - AI胜率标签：🏆/✅/📈/➖ 四级展示
          - 虎眼推荐理由：来自语义规则或默认生成
        """
        if df.empty or "代码" not in df.columns:
            return df

        track    = _load_track()
        today    = datetime.date.today().isoformat()
        updated  = False

        ai_dates, ai_gains, ai_labels = [], [], []

        for _, row in df.iterrows():
            code  = str(row.get("代码", ""))
            price = _safe_float(row.get("最新价", 0), 0.0)

            if code not in track:
                track[code] = {
                    "first_date":  today,
                    "entry_price": price,
                    "max_price":   price,
                    "entry_name":  str(row.get("名称", code)),
                }
                updated = True
            else:
                if price > 0 and price > (track[code].get("max_price") or 0):
                    track[code]["max_price"] = price
                    updated = True

            rec         = track[code]
            entry_price = _safe_float(rec.get("entry_price"), price) or price
            max_price   = _safe_float(rec.get("max_price"),   price) or price
            first_date  = rec.get("first_date", today)

            max_gain = round((max_price - entry_price) / entry_price * 100, 1) if entry_price > 0 else 0.0
            win_label = (
                f"🏆 +{max_gain}%" if max_gain >= 20 else
                f"✅ +{max_gain}%" if max_gain >= 10 else
                f"📈 +{max_gain}%" if max_gain >= 3  else
                f"➖ {max_gain}%"
            )

            ai_dates.append(first_date)
            ai_gains.append(f"+{max_gain}%" if max_gain >= 0 else f"{max_gain}%")
            ai_labels.append(win_label)

        if updated:
            _save_track(track)

        df = df.copy()
        df["AI入选日"]   = ai_dates
        df["AI最高涨幅"] = ai_gains
        df["AI胜率标签"] = ai_labels

        # 确保推荐理由列存在
        if "虎眼推荐理由" not in df.columns:
            df["虎眼推荐理由"] = "虎之眼综合筛选"

        return df

    # ══════════════════════════════════════════════════════════════
    # 工具：统一现货行情列名
    # ══════════════════════════════════════════════════════════════

    def _normalize_spot_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """将 AKShare stock_zh_a_spot_em 的列名标准化，兼容不同版本"""
        rename_map = {}
        for src, dst in [
            (["最新价", "current_price", "close"],                  "最新价"),
            (["涨跌幅", "change_pct", "pct_chg"],                  "涨跌幅"),
            (["成交额", "amount", "turnover"],                      "成交额"),
            (["换手率", "turnover_rate"],                           "换手率"),
            (["动态市盈率", "市盈率-动态", "pe", "PE"],             "PE"),
            (["市净率", "pb", "PB"],                               "PB"),
            (["振幅", "amplitude"],                                 "振幅"),
            (["60日涨跌幅", "涨跌幅60"],                           "60日涨跌幅"),
            (["代码", "stock_code", "code"],                       "代码"),
            (["名称", "stock_name", "name"],                       "名称"),
        ]:
            for s in src:
                if s in df.columns and dst not in df.columns:
                    rename_map[s] = dst
                    break

        df = df.rename(columns=rename_map)

        # 数值化
        for col in ["涨跌幅", "成交额", "换手率", "PE", "PB", "振幅", "60日涨跌幅", "最新价"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # 补充缺失列，避免 filter lambda 崩溃
        for col in ["振幅", "60日涨跌幅", "PE", "PB", "换手率"]:
            if col not in df.columns:
                df[col] = float("nan")

        return df
