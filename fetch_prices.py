# -*- coding: utf-8 -*-
"""每日抓 TWSE/TPEX 收盤,更新月底收盤序列 data/prices/<code>.json。

1 年歷史由 seed_prices.py(sector_gainer)一次性建立;此後本檔每日維護當月,
不再依賴 sector_gainer。當月值每天被最新收盤覆蓋 → 月底即該月收盤。
"""
import datetime
import json
import os
import re

import requests

import config

SOURCES = [
    ("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", "Code", "ClosingPrice"),
    ("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes", "SecuritiesCompanyCode", "Close"),
]


def num(v):
    s = str(v).strip().replace(",", "")
    try:
        f = float(s)
        return f if f > 0 else None
    except ValueError:
        return None


def roc_ym(v):
    """ROC 日期 '1150731' -> '2026-07'；格式不符回 None。"""
    s = str(v).strip()
    if not re.fullmatch(r"\d{7}", s):
        return None
    return f"{int(s[:3]) + 1911}-{s[3:5]}"


def main():
    # 月份一律以回應的 Date 欄為準:月初遇假日時端點回的是上月底收盤,用當下日期會把它
    # 寫進新月份(首個交易日才自我修正,期間 price_return_1y 用錯月)。Date 解不出才退回今天。
    today_ym = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)).strftime("%Y-%m")
    closes = {}  # code -> (ym, close)
    for url, ck, pk in SOURCES:
        try:
            rows = requests.get(url, timeout=30).json()
        except Exception as e:
            print(f"! {url}: {e}")
            continue
        n = 0
        for r in rows:
            code = str(r.get(ck, "")).strip()
            c = num(r.get(pk))
            if c is not None and re.fullmatch(r"\d{4}", code):  # 只收 4 位數個股/ETF
                closes[code] = (roc_ym(r.get("Date")) or today_ym, c)
                n += 1
        ym = roc_ym(rows[0].get("Date")) if rows else None
        print(f"{url.split('/')[-1]}: {n} 檔 ({ym or 'Date 無法解析,退回 ' + today_ym})")
    d = os.path.join(config.DATA_DIR, "prices")
    os.makedirs(d, exist_ok=True)
    for code, (ym, c) in closes.items():
        p = os.path.join(d, f"{code}.json")
        s = {}
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                s = json.load(f)
        s[ym] = c
        with open(p, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"更新收盤 {len(closes)} 檔 ({sorted({ym for ym, _ in closes.values()})})")


if __name__ == "__main__":
    main()
