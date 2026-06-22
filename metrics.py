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
            rec["eps_yoy"] = pct_change(i.get("eps"), inc[py].get("eps"))
            rec["net_income_yoy"] = pct_change(ni, inc[py].get("net_income"))
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
    data = load(os.path.join(config.DATA_DIR, "monthly_revenue", f"{code}.json"))
    # 先統一單位成仟元：FinMind(元)/1000，TWSE 原樣
    rev_by_m = {}
    for m, r in data.items():
        v = r.get("營業收入-當月營收")
        if isinstance(v, (int, float)) and r.get("_src") == "finmind":
            v = v / 1000
        rev_by_m[m] = v
    out = {}
    for m in sorted(rev_by_m):
        rev = rev_by_m[m]
        out[m] = {
            "revenue": rev,
            "mom": pct_change(rev, rev_by_m.get(prev_month(m))),
            "yoy": pct_change(rev, rev_by_m.get(f"{int(m[:4]) - 1}{m[4:]}")),
        }
        out[m] = {k: v for k, v in out[m].items() if v is not None}
    return out


def prev_month(m):
    y, mo = int(m[:4]), int(m[5:7])
    mo -= 1
    if mo == 0:
        mo, y = 12, y - 1
    return f"{y}-{mo:02d}"


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
        mo = monthly_metrics(code)
        if not q and not mo:
            continue
        dump(
            os.path.join(config.DATA_DIR, "fundamentals", f"{code}.json"),
            {"code": code, "name": master.get(code, {}).get("name"),
             "industry": master.get(code, {}).get("industry"),
             "quarterly": q, "monthly": mo},
        )
        if q:
            lp = max(q, key=q_tuple)
            latest[code] = {"name": master.get(code, {}).get("name"),
                            "industry": master.get(code, {}).get("industry"),
                            "period": lp, **q[lp]}
        if mo:
            lm = max(mo)
            latest_monthly[code] = {"name": master.get(code, {}).get("name"),
                                    "industry": master.get(code, {}).get("industry"),
                                    "month": lm, **mo[lm]}
    dump(os.path.join(config.DATA_DIR, "fundamentals", "_latest.json"), latest)
    dump(os.path.join(config.DATA_DIR, "fundamentals", "_latest_monthly.json"), latest_monthly)
    print(f"完成 {len(codes)} 檔，季橫斷面 {len(latest)}、月橫斷面 {len(latest_monthly)} -> data/fundamentals/")


if __name__ == "__main__":
    main()
