# -*- coding: utf-8 -*-
"""每日抓 TWSE/TPEX 收盤,更新月底收盤序列 data/prices/<code>.json。

1 年歷史由 seed_prices.py(sector_gainer)一次性建立;此後本檔每日維護當月,
不再依賴 sector_gainer。當月值每天被最新收盤覆蓋 → 月底即該月收盤。

順便產 data/markets.json({code: "TWSE"|"TPEX"}):兩個端點本來就分上市/上櫃,
只有這裡知道歸屬。前端推 TradingView watchlist 需要 EX:CODE 前綴。
"""
import datetime
import json
import os
import re

import requests

import config

SOURCES = [
    ("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", "Code", "ClosingPrice", "TWSE"),
    ("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes", "SecuritiesCompanyCode", "Close", "TPEX"),
]


def num(v):
    s = str(v).strip().replace(",", "")
    try:
        f = float(s)
        return f if f > 0 else None
    except ValueError:
        return None


def fetch_closes():
    """回傳 ({code: 收盤}, {code: 市場})。"""
    closes, markets = {}, {}
    for url, ck, pk, mk in SOURCES:
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
                closes[code] = c
                markets[code] = mk
                n += 1
        print(f"{url.split('/')[-1]}: {n} 檔")
    return closes, markets


def write_markets(markets):
    """市場歸屬只增不減:當日沒成交的股票不該從對照表消失。"""
    if not markets:
        return
    p = os.path.join(config.DATA_DIR, "markets.json")
    old = {}
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            old = json.load(f)
    old.update(markets)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(old, f, ensure_ascii=False, indent=0, sort_keys=True)
    print(f"markets.json: {len(old)} 檔")


def main():
    ym = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)).strftime("%Y-%m")
    closes, markets = fetch_closes()
    write_markets(markets)
    d = os.path.join(config.DATA_DIR, "prices")
    os.makedirs(d, exist_ok=True)
    for code, c in closes.items():
        p = os.path.join(d, f"{code}.json")
        s = {}
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                s = json.load(f)
        s[ym] = c
        with open(p, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"更新 {ym} 收盤 {len(closes)} 檔")


if __name__ == "__main__":
    main()
