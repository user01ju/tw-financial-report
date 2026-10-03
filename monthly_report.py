# -*- coding: utf-8 -*-
"""把 data/monthly_revenue/ 的某個月導成 CSV（MoM/YoY），月初早鳥用。

metrics.py 產的 _latest_monthly.json 是「每家自己的最新月」橫斷面；月初各家公告
進度不一時那個橫斷面不可比。這支固定看同一個月，缺的就是還沒公告。

用法:
    python monthly_report.py                 # 上個月
    python monthly_report.py --month 2026-07
    python monthly_report.py --codes 2330,2317
"""
import argparse
import csv
import json
import os

import config
from backfill_finmind import last_month

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "monthly_report.csv")


def load(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def prev_month(p):
    y, m = int(p[:4]), int(p[5:7])
    return f"{y}-{m-1:02d}" if m > 1 else f"{y-1}-12"


def revenue(rec):
    """統一成仟元：FinMind 存的是元，TWSE 是仟元。"""
    if not rec:
        return None
    v = rec.get("營業收入-當月營收")
    if v is None:
        return None
    return v / 1000 if rec.get("_src") == "finmind" else v


def pct(a, b):
    if a is None or b in (None, 0):
        return None
    return (a - b) / abs(b) * 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default="")
    ap.add_argument("--codes", default="")
    args = ap.parse_args()

    month = args.month or last_month()
    prev, ly = prev_month(month), f"{int(month[:4])-1}-{month[5:7]}"
    comp = load(os.path.join(config.DATA_DIR, "companies.json"))
    codes = [c.strip() for c in args.codes.split(",") if c.strip()] or sorted(comp)

    rows = []
    for code in codes:
        data = load(os.path.join(config.DATA_DIR, "monthly_revenue", f"{code}.json"))
        cur = revenue(data.get(month))
        if cur is None:
            continue
        meta = comp.get(code, {})
        rows.append([code, meta.get("name", ""), meta.get("industry", ""), round(cur),
                     pct(cur, revenue(data.get(prev))), pct(cur, revenue(data.get(ly))),
                     data[month].get("_src", "twse")])

    rows.sort(key=lambda r: r[5] if r[5] is not None else -9e9, reverse=True)
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["代號", "名稱", "產業", f"{month}營收(仟元)", "MoM%", "YoY%", "來源"])
        for r in rows:
            w.writerow(r[:4] + [f"{r[4]:.1f}" if r[4] is not None else "",
                                f"{r[5]:.1f}" if r[5] is not None else "", r[6]])

    src = {}
    for r in rows:
        src[r[6]] = src.get(r[6], 0) + 1
    print(f"{month}: {len(rows)}/{len(codes)} 檔有資料 "
          f"({', '.join(f'{k} {v}' for k, v in sorted(src.items()))})")
    print(f"-> {os.path.abspath(OUT)}")


if __name__ == "__main__":
    main()
