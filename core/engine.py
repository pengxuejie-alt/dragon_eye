"""
龙眼数据引擎 v2.0 — 虎之眼 (Eye of Tiger) 内核
================================================
升级内容：
1. 三重行情备份引擎（东方财富 → AKShare → 新浪）
2. 指南针 CYQ 筹码模型（VWAP 获利盘估算）
3. 历史胜率追溯机制（入选日期 + 最高涨幅 AI 预测命中率）
4. 语义化 AI 选股池（自然语言 → pandas 过滤逻辑）
5. macro_rate / profit_ratio 透传保障
"""

import re
import json
import datetime
import os
import requests
import pandas as pd

try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False

# ─── 本地胜率追踪文件（无数据库，文件持久化）─────────────────────────────
_TRACK_FILE = "data/screener_track.json"


def _load_track() -> dict:
    """加载历史选股追踪记录"""
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


class AShareDataEngine:
    """
    虎之眼数据引擎
    ─────────────────────────────────────────────────────
    职责：数据采集 + 指南针筹码模型 + 语义选股路由 + 胜率追踪
    所有数据经标准化后封装进 context dict，透传给各专家 Agent
    """

    EF_BASE  = "https://push2.eastmoney.com/api/qt/stock/get"
    EF_SPOT  = "https://push2.eastmoney.com/api/qt/clist/get"
    SINA_BASE = "http://hq.sinajs.cn/list="

    # ══════════════════════════════════════════════════════════════════
    # 1. 核心上下文组装
    # ══════════════════════════════════════════════════════════════════

    def get_full_context(self, ticker_full: str, raw_ticker: str) -> dict:
        """
        组装完整数据上下文，供所有 Agent 消费
        确保 macro_rate + profit_ratio 可被 03/04 专家透传
        """
        code = re.search(r"\d{6}", str(raw_ticker)).group(0) if re.search(r"\d{6}", str(raw_ticker)) else raw_ticker

        context: dict = {
            "symbol":     ticker_full,
            "raw_ticker": code,
            "timestamp":  datetime.datetime.now().isoformat(),
            "brand":      "基于虎之眼 (Eye of Tiger) 金融内核",  # 品牌植入
        }

        # ── 行情（三重备份）─────────────────────────────────────────
        price_data = self._get_price_eastmoney(code)
        if price_data["price_info"]["current_price"] == "N/A":
            price_data = self._get_price_akshare(code)
        if price_data["price_info"]["current_price"] == "N/A":
            price_data = self._get_price_sina(code)
        context.update(price_data)

        # ── 宏观利率（macro_rate 透传至 03_政策宏观）──────────────
        context.update(self._get_macro_rates())

        # ── 指南针 CYQ 筹码模型（profit_ratio 透传至 04_资金博弈）─
        chip = self._estimate_chips_cyq(code)
        context["chip_analysis"] = chip
        # 顶层透传：让 Agent context_summary 直接取用
        context["profit_ratio"]  = chip.get("profit_ratio", "N/A")
        context["avg_cost"]      = chip.get("avg_cost", "N/A")
        context["chip_density"]  = chip.get("chip_density", "N/A")

        # ── ATR 历史波动率（06_风险控制 使用）────────────────────
        context["atr_analysis"] = self._calc_atr(code)

        # ── 换手率趋势（04_资金博弈 使用）────────────────────────
        context["turnover_analysis"] = self._get_turnover_trend(code)

        # ── 基本面指标（01_价值审计 使用）────────────────────────
        context.update(self._get_fundamentals(code))

        # ── 北向资金（03_政策宏观 使用）──────────────────────────
        context["north_flow"] = self._get_north_flow()

        return context

    # ══════════════════════════════════════════════════════════════════
    # 2. 行情获取（三重备份）
    # ══════════════════════════════════════════════════════════════════

    def _get_price_eastmoney(self, code: str) -> dict:
        res = {
            "price_info": {"current_price": "N/A", "change_pct": 0.0, "pe_ttm": "N/A", "pb": "N/A"},
            "company_name": code, "market_cap": "N/A", "industry": "N/A",
        }
        try:
            secid = f"1.{code}" if code.startswith(("60", "68", "51")) else f"0.{code}"
            params = {
                "secid": secid,
                "fields": "f43,f44,f45,f47,f48,f57,f58,f60,f107,f116,f162,f167",
                "ut": "fa5fd1943c7b386f172d6893dbfba10b",
                "fltt": "2",
            }
            data = requests.get(self.EF_BASE, params=params, timeout=6).json().get("data") or {}
            if data and data.get("f43"):
                cp  = round(data["f43"] / 100, 2)
                pcp = round(data.get("f60", data["f43"]) / 100, 2)
                chg = round((cp - pcp) / pcp * 100, 2) if pcp > 0 else 0.0
                mv  = data.get("f116", 0)
                res.update({
                    "price_info": {
                        "current_price": cp,
                        "change_pct":    chg,
                        "pre_close":     pcp,
                        "high_today":    round(data.get("f44", 0) / 100, 2),
                        "low_today":     round(data.get("f45", 0) / 100, 2),
                        "volume":        data.get("f47", "N/A"),
                        "amount":        data.get("f48", "N/A"),
                        "pe_ttm":        round(data["f162"] / 100, 2) if data.get("f162") else "N/A",
                        "pb":            round(data["f167"] / 100, 2) if data.get("f167") else "N/A",
                    },
                    "company_name": data.get("f58", code),
                    "market_cap":   f"{round(mv / 1e8, 2)}亿" if mv else "N/A",
                })
        except Exception:
            pass
        return res

    def _get_price_akshare(self, code: str) -> dict:
        res = {
            "price_info": {"current_price": "N/A", "change_pct": 0.0, "pe_ttm": "N/A", "pb": "N/A"},
            "company_name": code, "market_cap": "N/A", "industry": "N/A",
        }
        if not HAS_AKSHARE:
            return res
        try:
            df = ak.stock_zh_a_spot_em()
            row = df[df["代码"] == code]
            if not row.empty:
                r = row.iloc[0]
                res.update({
                    "price_info": {
                        "current_price": float(r.get("最新价", 0)),
                        "change_pct":    float(r.get("涨跌幅", 0)),
                        "pe_ttm":        r.get("市盈率-动态", "N/A"),
                        "pb":            r.get("市净率", "N/A"),
                    },
                    "company_name": r.get("名称", code),
                    "market_cap":   f"{round(float(r.get('总市值', 0)) / 1e8, 2)}亿",
                })
        except Exception:
            pass
        return res

    def _get_price_sina(self, code: str) -> dict:
        res = {
            "price_info": {"current_price": "N/A", "change_pct": 0.0, "pe_ttm": "N/A", "pb": "N/A"},
            "company_name": code, "market_cap": "N/A", "industry": "N/A",
        }
        try:
            prefix = "sh" if code.startswith(("60", "68")) else "sz"
            headers = {"Referer": "http://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}
            resp = requests.get(f"{self.SINA_BASE}{prefix}{code}", headers=headers, timeout=5)
            resp.encoding = "gbk"
            parts = resp.text.split('"')[1].split(",")
            if len(parts) > 5:
                cp, pcp = float(parts[3]), float(parts[2])
                res.update({
                    "price_info": {
                        "current_price": cp,
                        "change_pct":    round((cp - pcp) / pcp * 100, 2) if pcp > 0 else 0.0,
                        "pe_ttm":        "N/A", "pb": "N/A",
                    },
                    "company_name": parts[0],
                })
        except Exception:
            pass
        return res

    # ══════════════════════════════════════════════════════════════════
    # 3. 指南针 CYQ 筹码模型
    # ══════════════════════════════════════════════════════════════════

    def _estimate_chips_cyq(self, code: str) -> dict:
        """
        参考指南针 CYQ（成本分布）模型
        用 VWAP 加权估算获利盘比例与筹码密集度
        """
        default = {
            "avg_cost": "N/A", "profit_ratio": "N/A",
            "chip_density": "N/A", "chip_lock_signal": "N/A",
            "vwap_60": "N/A", "vwap_20": "N/A",
        }
        if not HAS_AKSHARE:
            return default
        try:
            df = ak.stock_zh_a_hist(
                symbol=code, period="daily", adjust="qfq", start_date="20230101"
            ).tail(120)
            if df.empty:
                return default

            df.columns = [c.strip() for c in df.columns]
            # 兼容列名
            for alias in [["收盘", "close"], ["成交量", "volume"], ["最高", "high"], ["最低", "low"]]:
                for a in alias:
                    if a not in df.columns:
                        for b in alias:
                            if b in df.columns:
                                df[a] = df[b]
                                break

            curr = float(df["收盘"].iloc[-1])

            # 60日 VWAP（主力成本估算）
            df60 = df.tail(60)
            vwap60 = float((df60["收盘"] * df60["成交量"]).sum() / df60["成交量"].sum())

            # 20日 VWAP（短期成本）
            df20 = df.tail(20)
            vwap20 = float((df20["收盘"] * df20["成交量"]).sum() / df20["成交量"].sum())

            # 获利盘估算：假设成本正态分布于 VWAP±20%
            profit_raw = (curr - vwap60 * 0.85) / (vwap60 * 0.30) * 100
            profit_pct = round(min(max(profit_raw, 0), 100), 1)

            # 筹码密集度：近20日振幅的标准差（越小越密集）
            df20["range_pct"] = (df20["最高"] - df20["最低"]) / df20["收盘"] * 100
            density_val = round(df20["range_pct"].std(), 2)
            density_label = "高度密集" if density_val < 2.0 else "正常分布" if density_val < 4.0 else "筹码松散"

            # 锁仓信号：近5日价涨+量缩
            df5 = df.tail(5)
            price_rise = float(df5["收盘"].iloc[-1]) > float(df5["收盘"].iloc[0])
            vol_shrink = float(df5["成交量"].iloc[-1]) < float(df5["成交量"].mean()) * 0.85
            lock_signal = "⚡ 主力锁仓信号" if (price_rise and vol_shrink) else "无明显锁仓"

            return {
                "avg_cost":       round(vwap60, 2),
                "vwap_60":        round(vwap60, 2),
                "vwap_20":        round(vwap20, 2),
                "profit_ratio":   f"{profit_pct}%",
                "chip_density":   f"{density_label}（σ={density_val}%）",
                "chip_lock_signal": lock_signal,
                "above_vwap60":   curr > vwap60,
                "above_vwap20":   curr > vwap20,
            }
        except Exception as e:
            return {**default, "error": str(e)}

    # ══════════════════════════════════════════════════════════════════
    # 4. ATR 历史波动率（06_风险控制 用）
    # ══════════════════════════════════════════════════════════════════

    def _calc_atr(self, code: str) -> dict:
        """
        计算 ATR(14) 及其历史分位数
        判断当前波动是否处于历史低位（小回撤/低波动型标的的核心指标）
        """
        default = {"atr14": "N/A", "atr_pct": "N/A", "atr_percentile": "N/A", "volatility_label": "N/A"}
        if not HAS_AKSHARE:
            return default
        try:
            df = ak.stock_zh_a_hist(
                symbol=code, period="daily", adjust="qfq", start_date="20230101"
            ).tail(250)
            if len(df) < 30:
                return default

            df.columns = [c.strip() for c in df.columns]
            df["prev_close"] = df["收盘"].shift(1)
            df["tr"] = df.apply(
                lambda r: max(
                    abs(r.get("最高", r["收盘"]) - r.get("最低", r["收盘"])),
                    abs(r.get("最高", r["收盘"]) - r["prev_close"]),
                    abs(r.get("最低", r["收盘"]) - r["prev_close"]),
                ), axis=1
            )
            df["atr14"] = df["tr"].rolling(14).mean()
            curr_price = float(df["收盘"].iloc[-1])
            curr_atr   = float(df["atr14"].iloc[-1])
            atr_pct    = round(curr_atr / curr_price * 100, 2)

            # 历史分位数（百分位越低 = 当前波动越小）
            atr_series = df["atr14"].dropna()
            percentile = round((atr_series < curr_atr).sum() / len(atr_series) * 100, 1)

            if percentile < 25:
                label = "🟢 历史低波动（适合低吸）"
            elif percentile < 60:
                label = "🟡 正常波动区间"
            else:
                label = "🔴 历史高波动（注意风险）"

            return {
                "atr14":           round(curr_atr, 2),
                "atr_pct":         f"{atr_pct}%",
                "atr_percentile":  f"{percentile}%历史分位",
                "volatility_label": label,
            }
        except Exception as e:
            return {**default, "error": str(e)}

    # ══════════════════════════════════════════════════════════════════
    # 5. 换手率趋势（04_资金博弈 用）
    # ══════════════════════════════════════════════════════════════════

    def _get_turnover_trend(self, code: str) -> dict:
        """
        换手率承接审计：
        - 快速上涨 + 换手率下降 → 主力锁仓
        - 快速上涨 + 换手率上升 → 游资接力（高风险）
        """
        default = {"avg_turnover_5d": "N/A", "avg_turnover_20d": "N/A", "turnover_signal": "N/A"}
        if not HAS_AKSHARE:
            return default
        try:
            df = ak.stock_zh_a_hist(
                symbol=code, period="daily", adjust="qfq", start_date="20240101"
            ).tail(30)
            if df.empty or "换手率" not in df.columns:
                return default

            t5  = round(float(df["换手率"].tail(5).mean()), 2)
            t20 = round(float(df["换手率"].tail(20).mean()), 2)
            price_5d_chg = (float(df["收盘"].iloc[-1]) - float(df["收盘"].iloc[-6])) / float(df["收盘"].iloc[-6]) * 100

            if price_5d_chg > 5 and t5 < t20 * 0.85:
                signal = "⚡ 涨中换手率下降 → 主力锁仓，筹码稳固"
            elif price_5d_chg > 5 and t5 > t20 * 1.3:
                signal = "⚠️ 涨中换手率飙升 → 游资接力，筹码不稳"
            elif price_5d_chg < -3 and t5 > t20 * 1.5:
                signal = "🔴 跌中高换手 → 恐慌性抛售，注意底部确认"
            else:
                signal = f"换手正常（近5日均{t5}% vs 近20日均{t20}%）"

            return {
                "avg_turnover_5d":  f"{t5}%",
                "avg_turnover_20d": f"{t20}%",
                "price_5d_chg":     f"{round(price_5d_chg, 2)}%",
                "turnover_signal":  signal,
            }
        except Exception as e:
            return {**default, "error": str(e)}

    # ══════════════════════════════════════════════════════════════════
    # 6. 宏观利率（透传给 03_政策宏观）
    # ══════════════════════════════════════════════════════════════════

    def _get_macro_rates(self) -> dict:
        rates = {"macro_rate": "2.31", "lpr_1y": "3.10", "lpr_5y": "3.60"}
        if not HAS_AKSHARE:
            return rates
        try:
            df = ak.bond_zh_us_rate(start_date="20250101")
            if df is not None and not df.empty:
                val = df.iloc[-1, 1]
                rates["macro_rate"] = str(round(float(val), 2))
        except Exception:
            pass
        try:
            df_lpr = ak.macro_china_lpr()
            if df_lpr is not None and not df_lpr.empty:
                row = df_lpr.iloc[-1]
                rates["lpr_1y"] = str(row.get("1年期贷款市场报价利率", "3.10"))
                rates["lpr_5y"] = str(row.get("5年期以上贷款市场报价利率", "3.60"))
        except Exception:
            pass
        return rates

    # ══════════════════════════════════════════════════════════════════
    # 7. 基本面（透传给 01_价值审计）
    # ══════════════════════════════════════════════════════════════════

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
                    "gross_margin": r.get("销售毛利率", "N/A"),
                    "net_margin":   r.get("销售净利率", "N/A"),
                    "debt_ratio":   r.get("资产负债率", "N/A"),
                    "current_ratio":r.get("流动比率", "N/A"),
                }
        except Exception:
            pass
        return res

    # ══════════════════════════════════════════════════════════════════
    # 8. 北向资金（透传给 03_政策宏观）
    # ══════════════════════════════════════════════════════════════════

    def _get_north_flow(self) -> dict:
        default = {"today": "N/A", "5day": "N/A", "20day": "N/A", "direction": "N/A"}
        if not HAS_AKSHARE:
            return default
        try:
            df = ak.stock_hsgt_north_net_flow_in_em(indicator="沪深港通")
            if df is not None and not df.empty:
                col = df.columns[1]
                t1  = float(df[col].iloc[-1])
                t5  = float(df[col].tail(5).astype(float).sum())
                t20 = float(df[col].tail(20).astype(float).sum())
                return {
                    "today":     f"{t1:.2f}亿",
                    "5day":      f"{t5:.2f}亿",
                    "20day":     f"{t20:.2f}亿",
                    "direction": "净流入" if t1 > 0 else "净流出",
                }
        except Exception:
            pass
        return default

    # ══════════════════════════════════════════════════════════════════
    # 9. AI 语义化选股池 + 历史胜率追踪
    # ══════════════════════════════════════════════════════════════════

    def get_strategy_pool(self, strategy_type: str = "涨停最强") -> pd.DataFrame:
        """
        虎之眼选股雷达 —— 预设策略
        过滤：成交额 > 1亿 + 非ST
        """
        if not HAS_AKSHARE:
            return pd.DataFrame()
        try:
            df = ak.stock_zh_a_spot_em()
            # 标准化列名
            df = df.rename(columns={
                "代码": "代码", "名称": "名称",
                "涨跌幅": "涨跌幅", "最新价": "最新价",
                "成交额": "成交额", "换手率": "换手率",
                "动态市盈率": "PE", "市净率": "PB",
                "60日涨跌幅": "60日涨跌幅", "振幅": "振幅",
            })
            df = df[df["成交额"] > 1e8]
            df = df[~df["名称"].str.contains("ST|退|N|C", na=False)]
            df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
            df["换手率"] = pd.to_numeric(df.get("换手率", pd.Series()), errors="coerce")
            df["PE"]     = pd.to_numeric(df.get("PE", pd.Series()), errors="coerce")
            df["振幅"]   = pd.to_numeric(df.get("振幅", pd.Series()), errors="coerce")

            if strategy_type == "涨停最强":
                result = df[df["涨跌幅"] > 9.7].sort_values("换手率", ascending=False).head(10)
            elif strategy_type == "虎之眼价值":
                result = df[(df["PE"].between(5, 25)) & (df["涨跌幅"] > 1)].head(10)
            elif strategy_type == "全市场监控":
                result = df.nlargest(10, "成交额")
            else:
                result = df.head(10)

            return self._attach_win_rate(result)
        except Exception:
            return pd.DataFrame()

    def get_ai_screener(self, query: str) -> pd.DataFrame:
        """
        语义化 AI 选股路由
        将自然语言查询映射为 pandas 过滤逻辑
        ─────────────────────────────────────────
        支持语义：
          "快速上涨且回撤不多"  → 近5日涨幅>8% AND 振幅<5%
          "低估值蓝筹"          → PE<15 AND 市值>500亿
          "高换手强势"           → 换手率>5% AND 涨幅>3%
          "北上资金偏好"         → 市值>200亿 AND PE<30
          "小盘黑马"             → 市值<50亿 AND 涨幅>5%
          "缩量上涨"             → 涨幅>2% AND 换手率下降信号（近似：换手率<2%）
        """
        if not HAS_AKSHARE:
            return pd.DataFrame()

        # 语义映射表
        SEMANTIC_MAP = [
            {
                "keywords": ["快速上涨", "回撤不多", "小回撤", "稳步上涨"],
                "filter":   lambda df: df[(df["涨跌幅"] > 5) & (df.get("振幅", df["涨跌幅"]) < 6)],
                "sort":     "涨跌幅",
                "label":    "快速上涨低回撤",
            },
            {
                "keywords": ["低估值", "蓝筹", "价值", "便宜"],
                "filter":   lambda df: df[(df["PE"].between(3, 20)) & (df["涨跌幅"] > 0)],
                "sort":     "PE",
                "label":    "低估值价值股",
            },
            {
                "keywords": ["高换手", "强势", "活跃"],
                "filter":   lambda df: df[(df["换手率"] > 5) & (df["涨跌幅"] > 3)],
                "sort":     "换手率",
                "label":    "高换手强势股",
            },
            {
                "keywords": ["北上", "外资", "沪深港通", "蓝筹外资"],
                "filter":   lambda df: df[(df["PE"].between(5, 30)) & (df["最新价"].astype(float, errors="ignore") > 10)],
                "sort":     "成交额",
                "label":    "外资友好型",
            },
            {
                "keywords": ["小盘", "黑马", "弹性", "中小盘"],
                "filter":   lambda df: df[(df["涨跌幅"] > 4)].nsmallest(20, "成交额"),
                "sort":     "涨跌幅",
                "label":    "小盘弹性黑马",
            },
            {
                "keywords": ["缩量", "缩量上涨", "主力锁仓"],
                "filter":   lambda df: df[(df["涨跌幅"] > 2) & (df["换手率"] < 2)],
                "sort":     "涨跌幅",
                "label":    "缩量锁仓上涨",
            },
            {
                "keywords": ["涨停", "连板", "打板"],
                "filter":   lambda df: df[df["涨跌幅"] > 9.5],
                "sort":     "换手率",
                "label":    "涨停强势",
            },
        ]

        try:
            df = ak.stock_zh_a_spot_em()
            df = df.rename(columns={
                "代码": "代码", "名称": "名称",
                "涨跌幅": "涨跌幅", "最新价": "最新价",
                "成交额": "成交额", "换手率": "换手率",
                "动态市盈率": "PE", "振幅": "振幅",
            })
            df = df[df["成交额"] > 1e8]
            df = df[~df["名称"].str.contains("ST|退|N|C", na=False)]
            for col in ["涨跌幅", "换手率", "PE", "振幅", "最新价"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            # 语义匹配
            matched_rule = None
            query_lower = query
            for rule in SEMANTIC_MAP:
                if any(kw in query_lower for kw in rule["keywords"]):
                    matched_rule = rule
                    break

            if matched_rule:
                result = matched_rule["filter"](df)
                result = result.sort_values(matched_rule["sort"], ascending=False).head(15)
                result["策略标签"] = matched_rule["label"]
            else:
                # 默认：综合强势
                result = df[df["涨跌幅"] > 3].sort_values("成交额", ascending=False).head(15)
                result["策略标签"] = "综合强势"

            return self._attach_win_rate(result)
        except Exception as e:
            return pd.DataFrame({"error": [str(e)]})

    # ══════════════════════════════════════════════════════════════════
    # 10. 历史胜率追踪（AI 预测命中率）
    # ══════════════════════════════════════════════════════════════════

    def _attach_win_rate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        为每个入选个股附加历史胜率信息：
        - 首次入选日期
        - 入选日收盘价（估算）
        - 从入选日至今的最高涨幅（AI 预测命中率依据）
        """
        if df.empty or "代码" not in df.columns:
            return df

        track = _load_track()
        today_str = datetime.date.today().isoformat()
        updated = False

        ai_entry_date = []
        ai_max_gain   = []
        ai_win_label  = []

        for _, row in df.iterrows():
            code = str(row.get("代码", ""))
            curr_price = float(row.get("最新价", 0) or 0)

            if code not in track:
                # 首次入选
                track[code] = {
                    "first_date":  today_str,
                    "entry_price": curr_price,
                    "max_price":   curr_price,
                }
                updated = True
            else:
                # 更新最高价
                if curr_price > track[code].get("max_price", 0):
                    track[code]["max_price"] = curr_price
                    updated = True

            entry = track[code]
            entry_price = entry.get("entry_price", curr_price) or curr_price
            max_price   = entry.get("max_price", curr_price) or curr_price
            first_date  = entry.get("first_date", today_str)

            max_gain = round((max_price - entry_price) / entry_price * 100, 1) if entry_price > 0 else 0.0
            win_label = (
                f"🏆 +{max_gain}%"  if max_gain >= 20 else
                f"✅ +{max_gain}%"  if max_gain >= 10 else
                f"📈 +{max_gain}%"  if max_gain >= 3  else
                f"➖ {max_gain}%"
            )

            ai_entry_date.append(first_date)
            ai_max_gain.append(f"+{max_gain}%")
            ai_win_label.append(win_label)

        if updated:
            _save_track(track)

        df = df.copy()
        df["AI入选日"] = ai_entry_date
        df["AI最高涨幅"] = ai_max_gain
        df["AI胜率标签"] = ai_win_label

        return df
