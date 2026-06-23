# -*- coding: utf-8 -*-
"""基本面指標：橋接 TWSE(中文欄名) + FinMind(type 碼) → canonical，再算 ratio/TTM/YoY。

輸入:
  data/income_statement/<code>.json   TWSE 損益(中文欄名, 近期)
  data/balance_sheet/<code>.json      TWSE 資產(中文欄名, 近期)
  data/finmind/income_statement/<code>.json  FinMind 損益(type 碼, 歷史)
  data/finmind/balance_sheet/<code>.json
  data/monthly_revenue/<code>.json    月營收(已合併雙來源)
輸出:
  data/fundamentals/<code>.json       { quarterly:{...}, monthly:{...} }
  data/fundamentals/_latest.json      全市場最新季橫斷面(排行/篩選用)

用法:
  python metrics.py                 # 全部
  python metrics.py 2330 2317       # 指定股
"""
import json
import os
import sys

import config

# canonical 欄 -> 來源欄名候選(取第一個有值的)。TWSE 優先用官方期間，FinMind 補歷史。
INCOME_MAP = {
    "revenue": (["Revenue"], ["營業收入"]),
    "cogs": (["CostOfGoodsSold"], ["營業成本"]),
    "gross_profit": (["GrossProfit"], ["營業毛利（毛損）淨額", "營業毛利（毛損）"]),
    "operating_expenses": (["OperatingExpenses"], ["營業費用"]),
    "operating_income": (["OperatingIncome"], ["營業利益（損失）"]),
    "pretax_income": (["PreTaxIncome"], ["稅前淨利（淨損）"]),
    "net_income": (["IncomeAfterTaxes"], ["本期淨利（淨損）"]),
    "eps": (["EPS"], ["基本每股盈餘（元）"]),
}
BALANCE_MAP = {
    "total_assets": (["TotalAssets"], ["資產總額"]),
    "total_liabilities": (["Liabilities"], ["負債總額"]),
    "equity": (["Equity"], ["權益總額"]),
    "equity_parent": (["EquityAttributableToOwnersOfParent"], ["歸屬於母公司業主之權益合計"]),
    "current_assets": (["CurrentAssets"], ["流動資產"]),
    "current_liabilities": (["CurrentLiabilities"], ["流動負債"]),
}


def load(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=True)


def div(a, b):
    if a is None or b in (None, 0):
        return None
    return a / b


def pct(a, b):
    r = div(a, b)
    return None if r is None else round(r * 100, 2)


# 金額欄統一單位=仟元(TWSE 原生)；FinMind 是元需 /1000。EPS(元/股)不換算。
MONETARY = (set(INCOME_MAP) | set(BALANCE_MAP)) - {"eps"}


def extract(rec, mapping, source):
    """從單期 record 依 source(finmind/twse) 取 canonical 欄，金額統一成仟元。"""
    idx = 0 if source == "finmind" else 1
    out = {}
    for canon, candidates in mapping.items():
        for col in candidates[idx]:
            v = rec.get(col)
            if v is not None and v != "":
                if source == "finmind" and canon in MONETARY and isinstance(v, (int, float)):
                    v = v / 1000
                out[canon] = v
                break
    return out


def merge_periods(twse_file, fm_file, mapping):
    """合併兩來源 → {period: {canonical}}；同期 TWSE 官方優先。"""
    twse, fm = load(twse_file), load(fm_file)
    out = {}
    for period in set(twse) | set(fm):
        if period in twse:
            out[period] = extract(twse[period], mapping, "twse")
        else:
            out[period] = extract(fm[period], mapping, "finmind")
    return out


# ---- 季 period 運算 ----
def q_tuple(p):
    return (int(p[:4]), int(p[-1]))


def prev_year_q(p):
    return f"{int(p[:4]) - 1}Q{p[-1]}"


def prev_q(p):
    """前一個連續季 '2026Q1' -> '2025Q4'"""
    y, q = q_tuple(p)
    q -= 1
    if q == 0:
        q, y = 4, y - 1
    return f"{y}Q{q}"


def trailing4(periods, p):
    """回傳 p 及其前 3 個連續季(含)，不連續則 None。"""
    y, q = q_tuple(p)
    seq = []
    for _ in range(4):
        seq.append(f"{y}Q{q}")
        q -= 1
        if q == 0:
            q, y = 4, y - 1
    return seq if all(s in periods for s in seq) else None


def quarterly_metrics(inc, bal):
    periods = sorted(set(inc) | set(bal), key=q_tuple)
    out = {}
    for p in periods:
        i, b = inc.get(p, {}), bal.get(p, {})
        rev = i.get("revenue")
        ni = i.get("net_income")
        eq = b.get("equity")
        rec = {
            **{k: i.get(k) for k in INCOME_MAP},
            **{k: b.get(k) for k in BALANCE_MAP},
            # 單季獲利能力(%)
            "gross_margin": pct(i.get("gross_profit"), rev),
            "operating_margin": pct(i.get("operating_income"), rev),
            "net_margin": pct(ni, rev),
            # 財務結構(時點)
            "debt_ratio": pct(b.get("total_liabilities"), b.get("total_assets")),
            "current_ratio": pct(b.get("current_assets"), b.get("current_liabilities")),
            "roe_q": pct(ni, eq),
            "roa_q": pct(ni, b.get("total_assets")),
        }
        # YoY(單季)
        py = prev_year_q(p)
        if py in inc:
            rec["revenue_yoy"] = pct_change(rev, inc[py].get("revenue"))
            rec["operating_income_yoy"] = pct_change(i.get("operating_income"), inc[py].get("operating_income"))
            rec["eps_yoy"] = pct_change(i.get("eps"), inc[py].get("eps"))
            rec["net_income_yoy"] = pct_change(ni, inc[py].get("net_income"))
        # 成長加速度(本季 YoY - 前季 YoY)：抓「加速中」的成長
        pq = prev_q(p)
        if pq in out:
            for f in ("revenue_yoy", "operating_income_yoy"):
                cur, prev = rec.get(f), out[pq].get(f)
                if cur is not None and prev is not None:
                    rec[f + "_accel"] = round(cur - prev, 2)
        # TTM(近四季)
        t4 = trailing4(set(periods), p)
        if t4:
            ni_ttm = sum_or_none(inc.get(q, {}).get("net_income") for q in t4)
            rec["revenue_ttm"] = sum_or_none(inc.get(q, {}).get("revenue") for q in t4)
            rec["net_income_ttm"] = ni_ttm
            eps_ttm = sum_or_none(inc.get(q, {}).get("eps") for q in t4)
            rec["eps_ttm"] = round(eps_ttm, 2) if eps_ttm is not None else None
            rec["roe_ttm"] = pct(ni_ttm, eq)  # TTM 淨利 / 期末權益
            rec["roa_ttm"] = pct(ni_ttm, b.get("total_assets"))
        out[p] = {k: v for k, v in rec.items() if v is not None}
    return out


def pct_change(now, before):
    if now is None or before in (None, 0):
        return None
    return round((now - before) / abs(before) * 100, 2)


def sum_or_none(vals):
    vals = list(vals)
    if any(v is None for v in vals):
        return None
    return sum(vals)


def monthly_metrics(code):
    """回傳 (per-month 序列, summary 動能/轉折/新高摘要)。"""
    data = load(os.path.join(config.DATA_DIR, "monthly_revenue", f"{code}.json"))
    # 先統一單位成仟元：FinMind(元)/1000，TWSE 原樣
    rev_by_m = {}
    for m, r in data.items():
        v = r.get("營業收入-當月營收")
        if isinstance(v, (int, float)) and r.get("_src") == "finmind":
            v = v / 1000
        rev_by_m[m] = v
    months = sorted(rev_by_m)
    yoys = [pct_change(rev_by_m[m], rev_by_m.get(f"{int(m[:4]) - 1}{m[4:]}")) for m in months]
    out = {}
    for i, m in enumerate(months):
        rev = rev_by_m[m]
        y3, y12 = avg_window(yoys, i + 1, 3), avg_window(yoys, i + 1, 12)  # 滾動短/長期動能
        rec = {
            "revenue": rev,
            "mom": pct_change(rev, rev_by_m.get(prev_month(m))),
            "yoy": yoys[i],
            "yoy_3m": round(y3, 2) if y3 is not None else None,
            "yoy_12m": round(y12, 2) if y12 is not None else None,
        }
        out[m] = {k: v for k, v in rec.items() if v is not None}
    return out, monthly_summary(rev_by_m, dict(zip(months, yoys)), months)


def avg_window(yoys, end, n):
    """yoys[end-n:end] 非 None 的平均(end 為 exclusive 索引)。"""
    if end <= 0:
        return None
    w = [y for y in yoys[max(0, end - n):end] if y is not None]
    return sum(w) / len(w) if w else None


def monthly_summary(rev_by_m, yoy_by_m, months):
    """月營收摘要：長短期 YoY(3m/12m)、累計YoY、加速、連續月、轉折、創新高。"""
    if not months:
        return {}
    yoys = [yoy_by_m[m] for m in months]  # 由舊到新
    s = {}
    n = len(yoys)
    cur3, cur12 = avg_window(yoys, n, 3), avg_window(yoys, n, 12)
    prev3, prev12 = avg_window(yoys, n - 1, 3), avg_window(yoys, n - 1, 12)
    prior3 = avg_window(yoys, n - 3, 3)  # 前一段 3 月(算加速用)
    if cur3 is not None:
        s["mrev_yoy_3m"] = round(cur3, 2)  # 短期動能
    if cur12 is not None:
        s["mrev_yoy_12m"] = round(cur12, 2)  # 長期動能
    if cur3 is not None and prior3 is not None:
        s["mrev_yoy_accel"] = round(cur3 - prior3, 2)
    # 短期突破長期：本月 3m 上穿 12m(上月還在下方)=動能轉強黃金交叉；1=剛突破 0=無
    if None not in (cur3, cur12, prev3, prev12):
        s["mrev_breakout"] = 1 if cur3 > cur12 and prev3 <= prev12 else 0
        s["mrev_3m_over_12m"] = cur3 > cur12  # 當前短期是否在長期之上(狀態)
    # 連續正成長月數
    streak = 0
    for y in reversed(yoys):
        if y is None or y <= 0:
            break
        streak += 1
    s["mrev_streak"] = streak
    # YoY 轉折(最新月 vs 前一月 YoY 號變)：1=轉正 -1=轉負 0=無
    if yoys[-1] is not None and len(yoys) >= 2 and yoys[-2] is not None:
        s["mrev_turn"] = 1 if yoys[-1] > 0 >= yoys[-2] else (-1 if yoys[-1] <= 0 < yoys[-2] else 0)
    # 累計營收 YoY(YTD)：當年初至今 vs 去年同期(只比兩年都有的月份)
    y, mm = int(months[-1][:4]), int(months[-1][5:7])
    cur = [rev_by_m[f"{y}-{k:02d}"] for k in range(1, mm + 1)
           if rev_by_m.get(f"{y}-{k:02d}") is not None and rev_by_m.get(f"{y - 1}-{k:02d}") is not None]
    pri = [rev_by_m[f"{y - 1}-{k:02d}"] for k in range(1, mm + 1)
           if rev_by_m.get(f"{y}-{k:02d}") is not None and rev_by_m.get(f"{y - 1}-{k:02d}") is not None]
    if cur and sum(pri) > 0:
        s["mrev_yoy_ytd"] = round((sum(cur) / sum(pri) - 1) * 100, 2)
    # 創新高(最新月營收)
    revs = [rev_by_m[m] for m in months if rev_by_m[m] is not None]
    last = rev_by_m[months[-1]]
    if last is not None and revs:
        s["mrev_high_all"] = last >= max(revs)
        last12 = [rev_by_m[m] for m in months[-12:] if rev_by_m[m] is not None]
        s["mrev_high_12m"] = bool(last12) and last >= max(last12)
    return s


# 動能成長綜合分數的因子與權重(跨市場百分位後加權)。四類：成長/加速/月動能/價格動能
MG_FACTORS = {
    # 成長 0.39
    "revenue_yoy": 0.17,
    "operating_income_yoy": 0.11,
    "eps_yoy": 0.11,
    # 加速 0.26
    "revenue_yoy_accel": 0.14,
    "mrev_yoy_accel": 0.12,
    # 月營收動能 0.30
    "mrev_yoy_3m": 0.15,
    "mrev_streak": 0.15,  # 連續成長月數：獎勵「持續」而非單次暴衝
    # 價格動能 0.05（僅參考，避免追高）
    "price_return_1y": 0.05,
}

# 認列型類股(營收完工/里程碑認列,單季YoY會暴衝失真)→ 不納入動能評分
MG_EXCLUDE_SECTORS = {"營建"}


def add_mg_score(latest):
    """對 latest 橫斷面每個因子做百分位排名,加權成 0-100 動能成長分數。
    認列型類股(營建)排除在評分宇宙外,不佔百分位也不給分。"""
    codes = [c for c in latest if latest[c].get("sector") not in MG_EXCLUDE_SECTORS]
    pranks = {}
    for f in MG_FACTORS:
        vals = sorted(
            ((c, latest[c][f]) for c in codes if isinstance(latest[c].get(f), (int, float))),
            key=lambda x: x[1],
        )
        n = len(vals)
        pranks[f] = {c: (i / (n - 1) * 100 if n > 1 else 50.0) for i, (c, _) in enumerate(vals)}
    for c in codes:
        num = wsum = 0.0
        for f, w in MG_FACTORS.items():
            if c in pranks[f]:
                num += pranks[f][c] * w
                wsum += w
        if wsum > 0:
            latest[c]["mg_score"] = round(num / wsum, 1)


def prev_month(m):
    y, mo = int(m[:4]), int(m[5:7])
    mo -= 1
    if mo == 0:
        mo, y = 12, y - 1
    return f"{y}-{mo:02d}"


def load_sectors():
    """CMoney 子類股(互斥)：code -> {sector, sector_parent}。"""
    path = os.path.join(config.DATA_DIR, "sectors", "categories.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        cats = json.load(f)
    m = {}
    for c in cats:
        for s in c.get("stocks", []):
            m[str(s["id"])] = {"sector": c["name"], "sector_parent": c["parent"]}
    return m


def load_price_returns():
    """code -> 近一年報酬(%)。用月底收盤序列：最新月 / 12 個月前同月 - 1。"""
    d = os.path.join(config.DATA_DIR, "prices")
    out = {}
    if not os.path.isdir(d):
        return out
    for fn in os.listdir(d):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(d, fn), encoding="utf-8") as f:
            s = json.load(f)
        if not s:
            continue
        latest = max(s)
        ref = f"{int(latest[:4]) - 1}-{latest[5:7]}"
        if s.get(ref):
            out[fn[:-5]] = round((s[latest] / s[ref] - 1) * 100, 2)
    return out


def company_codes():
    codes = set()
    for sub in ("income_statement", "balance_sheet", "monthly_revenue"):
        d = os.path.join(config.DATA_DIR, sub)
        if os.path.isdir(d):
            codes |= {f[:-5] for f in os.listdir(d) if f.endswith(".json")}
        df = os.path.join(config.DATA_DIR, "finmind", sub)
        if os.path.isdir(df):
            codes |= {f[:-5] for f in os.listdir(df) if f.endswith(".json")}
    return sorted(codes)


def main():
    codes = sys.argv[1:] or company_codes()
    master = load(os.path.join(config.DATA_DIR, "companies.json"))
    sectors = load_sectors()
    price_ret = load_price_returns()
    latest = {}
    latest_monthly = {}
    for i, code in enumerate(codes, 1):
        inc = merge_periods(
            os.path.join(config.DATA_DIR, "income_statement", f"{code}.json"),
            os.path.join(config.DATA_DIR, "finmind", "income_statement", f"{code}.json"),
            INCOME_MAP,
        )
        bal = merge_periods(
            os.path.join(config.DATA_DIR, "balance_sheet", f"{code}.json"),
            os.path.join(config.DATA_DIR, "finmind", "balance_sheet", f"{code}.json"),
            BALANCE_MAP,
        )
        q = quarterly_metrics(inc, bal)
        mo, msum = monthly_metrics(code)
        if not q and not mo:
            continue
        sec = sectors.get(code, {})
        prc = price_ret.get(code)
        meta = {"name": master.get(code, {}).get("name"),
                "industry": master.get(code, {}).get("industry"),
                "sector": sec.get("sector"),
                "sector_parent": sec.get("sector_parent"),
                "price_return_1y": prc}
        dump(
            os.path.join(config.DATA_DIR, "fundamentals", f"{code}.json"),
            {"code": code, **meta, "quarterly": q, "monthly": mo},
        )
        if q:
            lp = max(q, key=q_tuple)
            latest[code] = {**meta, "period": lp, **q[lp], **msum}
        if mo:
            lm = max(mo)
            latest_monthly[code] = {**meta, "month": lm, **mo[lm], **msum}
    add_mg_score(latest)
    dump(os.path.join(config.DATA_DIR, "fundamentals", "_latest.json"), latest)
    dump(os.path.join(config.DATA_DIR, "fundamentals", "_latest_monthly.json"), latest_monthly)
    print(f"完成 {len(codes)} 檔，季橫斷面 {len(latest)}、月橫斷面 {len(latest_monthly)} -> data/fundamentals/")


if __name__ == "__main__":
    main()
