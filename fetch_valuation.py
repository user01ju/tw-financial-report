# -*- coding: utf-8 -*-
"""抓每日估值快照(本益比/股價淨值比/殖利率)。官方直接公布，不用自己算。

來源:
  上市 TWSE: exchangeReport/BWIBBU_ALL  (Code/PEratio/PBratio/DividendYield)
  上櫃 TPEX: tpex_mainboard_peratio_analysis (英文欄名不同)
輸出:
  data/valuation/_latest.json  { code: {pe, pb, yield, date} }
"""
import json
import os

import requests

import config

URLS = [
    "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL",
    "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis",
]
# 兩來源欄名對應 -> canonical
ALIAS = {
    "code": ("Code", "SecuritiesCompanyCode"),
    "pe": ("PEratio", "PriceEarningRatio"),
    "pb": ("PBratio", "PriceBookRatio"),
    "yield": ("DividendYield", "YieldRatio"),
    "date": ("Date",),
}


def num(v):
    s = str(v).strip()
    if s in ("", "-", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def roc_date(s):
    s = str(s).strip()
    if len(s) < 7:
        return None
    return f"{int(s[:3]) + 1911}-{s[3:5]}-{s[5:7]}"


def pick(rec, key):
    for k in ALIAS[key]:
        if k in rec and str(rec[k]).strip():
            return rec[k]
    return None


def main():
    out = {}
    for url in URLS:
        try:
            rows = requests.get(url, timeout=30).json()
        except Exception as e:
            print(f"! {url}: {e}")
            continue
        n = 0
        for r in rows:
            code = pick(r, "code")
            if not code:
                continue
            out[str(code).strip()] = {
                "pe": num(pick(r, "pe")),
                "pb": num(pick(r, "pb")),
                "yield": num(pick(r, "yield")),
                "date": roc_date(pick(r, "date")),
            }
            n += 1
        print(f"{url.split('/')[-1]}: {n} 筆")
    path = os.path.join(config.DATA_DIR, "valuation", "_latest.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"-> {len(out)} 檔 estimate -> {path}")


if __name__ == "__main__":
    main()
