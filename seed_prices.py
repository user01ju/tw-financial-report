# -*- coding: utf-8 -*-
"""一次性：從 sector_gainer 既有日線 seed 月底收盤 -> data/prices/<code>.json。

之後由 fetch_prices.py(TWSE/TPEX 每日)維護當月,不再依賴 sector_gainer。
本機跑,產出 commit 進 repo(Action runner 沒有 sector_gainer)。
"""
import csv
import glob
import json
import os
from collections import defaultdict

import config

SRC = os.path.join("..", "sector_gainer", "data", "daily")


def main():
    prices = defaultdict(dict)
    files = sorted(glob.glob(os.path.join(SRC, "*.csv")))
    if not files:
        raise SystemExit(f"找不到 sector_gainer 日線: {SRC}")
    for fp in files:
        ym = os.path.basename(fp)[:7]  # YYYY-MM
        with open(fp, encoding="utf-8", errors="ignore", newline="") as f:
            for row in csv.DictReader(f):
                code = (row.get("id") or "").strip()
                close = (row.get("close") or "").strip().replace(",", "")
                if not code or not close:
                    continue
                try:
                    prices[code][ym] = float(close)  # 同月後寫覆蓋 → 月底收盤
                except ValueError:
                    pass
    out_dir = os.path.join(config.DATA_DIR, "prices")
    os.makedirs(out_dir, exist_ok=True)
    for code, series in prices.items():
        with open(os.path.join(out_dir, f"{code}.json"), "w", encoding="utf-8") as f:
            json.dump(series, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"seed {len(prices)} 檔,月數範圍 {files[0][-14:-4]} ~ {files[-1][-14:-4]}")


if __name__ == "__main__":
    main()
