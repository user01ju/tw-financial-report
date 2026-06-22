# -*- coding: utf-8 -*-
"""用 FinMind 回補歷史財報。

OpenAPI 只有最新一期，歷史靠這支補齊到接點。一次性、可續跑。

用法:
    set FINMIND_TOKEN=xxxx           # 強烈建議(600/hr，無 token 僅 300/hr)
    python backfill_finmind.py                    # 全市場，從 START_DATE 起
    python backfill_finmind.py --start 2018-01-01
    python backfill_finmind.py --codes 2330,2317  # 只補指定股
    python backfill_finmind.py --force            # 忽略進度重抓

特性:
- 每檔 3 次呼叫(月營收/損益/資產)，一次抓全區間。
- 402(限額)自動 sleep 退避重試；可隨時 Ctrl+C，進度存 data/finmind/_progress.json。
- 月營收併入既有 data/monthly_revenue/(同 TWSE 欄名)；
  損益/資產為 long format，pivot 後存 data/finmind/ 保留來源純淨。
"""
import argparse
import json
import os
import sys
import time

import requests

import config

API = "https://api.finmindtrade.com/api/v4/data"
START_DATE = "2015-01-01"
TOKEN = os.environ.get("FINMIND_TOKEN", "")
BASE_SLEEP = float(os.environ.get("FINMIND_SLEEP", "6" if TOKEN else "12"))  # 秒/呼叫，貼著額度
PROGRESS = os.path.join(config.DATA_DIR, "finmind", "_progress.json")

session = requests.Session()


def api_get(dataset, data_id, start_date):
    params = {"dataset": dataset, "data_id": data_id, "start_date": start_date}
    if TOKEN:
        params["token"] = TOKEN
    while True:
        try:
            r = session.get(API, params=params, timeout=60)
        except Exception as e:
            print(f"    ! 連線錯誤 {dataset} {data_id}: {e}，30s 後重試")
            time.sleep(30)
            continue
        if r.status_code == 402:
            print("    ... 觸及額度上限，sleep 60s")
            time.sleep(60)
            continue
        if r.status_code != 200:
            print(f"    ! HTTP {r.status_code} {dataset} {data_id}")
            return []
        j = r.json()
        if j.get("status") == 402:
            print("    ... 額度上限(body)，sleep 60s")
            time.sleep(60)
            continue
        return j.get("data", []) or []


def quarter_period(date_str):
    """'2026-03-31' -> '2026Q1'"""
    y, m = date_str[:4], int(date_str[5:7])
    return f"{y}Q{(m - 1) // 3 + 1}"


def load(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=True)


def backfill_monthly(code, start):
    rows = api_get("TaiwanStockMonthRevenue", code, start)
    if not rows:
        return 0
    path = os.path.join(config.DATA_DIR, "monthly_revenue", f"{code}.json")
    data = load(path)
    for r in rows:
        period = f"{r['revenue_year']}-{int(r['revenue_month']):02d}"
        # 不覆蓋 TWSE 既有期；只補 FinMind 才有的歷史月
        if period not in data:
            data[period] = {
                "公司代號": int(code) if code.isdigit() else code,
                "營業收入-當月營收": r.get("revenue"),
                "_src": "finmind",
            }
    dump(path, data)
    return len(rows)


def backfill_statement(code, dataset, subdir, start):
    rows = api_get(dataset, code, start)
    if not rows:
        return 0
    path = os.path.join(config.DATA_DIR, "finmind", subdir, f"{code}.json")
    data = load(path)
    for r in rows:
        period = quarter_period(r["date"])
        data.setdefault(period, {"_src": "finmind"})[r["type"]] = r["value"]
    dump(path, data)
    return len(rows)


def already_done(code):
    """以實際產出檔為準判斷是否回補過(self-healing，不依賴 _progress.json)。"""
    inc = os.path.join(config.DATA_DIR, "finmind", "income_statement", f"{code}.json")
    bal = os.path.join(config.DATA_DIR, "finmind", "balance_sheet", f"{code}.json")
    return os.path.exists(inc) and os.path.exists(bal)


def universe(args):
    if args.codes:
        return [c.strip() for c in args.codes.split(",") if c.strip()]
    master = load(os.path.join(config.DATA_DIR, "companies.json"))
    if not master:
        sys.exit("找不到 data/companies.json，請先跑 fetch_latest.py 或用 --codes 指定")
    return sorted(master.keys())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=START_DATE)
    ap.add_argument("--codes", default="")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    codes = universe(args)
    # resume：progress 檔 ∪ 實際已產出檔，雙保險(progress 壞掉也不重跑)
    progress = set() if args.force else set(load(PROGRESS).get("done", []))
    todo = codes if args.force else [c for c in codes if c not in progress and not already_done(c)]
    progress |= {c for c in codes if already_done(c)}
    print(f"宇宙 {len(codes)} 檔，待補 {len(todo)} 檔，token={'有' if TOKEN else '無(300/hr)'}")

    for i, code in enumerate(todo, 1):
        t0 = time.time()
        m = backfill_monthly(code, args.start)
        time.sleep(BASE_SLEEP)
        inc = backfill_statement(code, "TaiwanStockFinancialStatements", "income_statement", args.start)
        time.sleep(BASE_SLEEP)
        bs = backfill_statement(code, "TaiwanStockBalanceSheet", "balance_sheet", args.start)
        time.sleep(BASE_SLEEP)

        progress.add(code)
        if i % 10 == 0 or i == len(todo):
            dump(PROGRESS, {"done": sorted(progress)})
        print(f"[{i}/{len(todo)}] {code} 月{m} 損益{inc} 資產{bs} ({time.time()-t0:.0f}s)")

    dump(PROGRESS, {"done": sorted(progress)})
    print("回補完成。")


if __name__ == "__main__":
    main()
