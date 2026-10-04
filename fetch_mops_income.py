# -*- coding: utf-8 -*-
"""MOPS 綜合損益表（t164sb04）：每家公司「本季單季」+「去年同季（重編後）」。

為什麼需要（2026-10-04 用 MOPS 抽樣 203 家對帳 fundamentals 發現）：
- TWSE OpenAPI 只給累計值，去累計時用的是 TWSE 快照裡「原始」的前季累計。公司重編前季後，
  單季就算錯（3290 東浦 2026Q2 淨利：去累計 1.24 億，MOPS 單季 735 萬）。
- YoY 的去年基期我們用 FinMind 原始舊值，但 MOPS 的去年同季是**追溯重編後**的：
  IFRS 17（2026 起保險/金控，富邦金 2025Q2 淨利原始 +103 億 → 重編 -273 億）、
  共同控制合併、配股追溯調整 EPS。舊值當基期，YoY 對這些公司是錯的。
- 單季 EPS 也是公司自己報的值，不必再用比例近似。

輸出 data/mops_income/<code>.json  {"2026Q2": {"cur": {...}, "ly": {...}}}（金額仟元，EPS 元）

用法:
    python fetch_mops_income.py                 # TWSE 已申報的最新一季、只抓已申報的公司，已有的跳過
    python fetch_mops_income.py --period 2026Q1
    python fetch_mops_income.py --codes 2330,3290 --force
    python fetch_mops_income.py --max 300       # 本次最多打幾家（CI 每天補一點用）

限速：單執行緒、每次間隔 0.5 秒。MOPS 高併發會被 TCP 層封 IP 約 8 小時
(llm_wiki: mops-api-rate-limit-tcp-block)，連續 3 次連線失敗就中止整批。
"""
import argparse
import json
import os
import re
import sys
import time

import requests

import config

URL = "https://mops.twse.com.tw/mops/api/t164sb04"
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/140.0.0.0 Safari/537.36",
    "Referer": "https://mops.twse.com.tw/mops/",
    "Origin": "https://mops.twse.com.tw",
}
SLEEP = 0.5
OUT_DIR = os.path.join(config.DATA_DIR, "mops_income")

# canonical -> MOPS 科目名候選（依序取第一個「有數值」的列；各表單格式名稱不同）
ROWS = {
    "revenue": ["營業收入合計", "收入合計", "收益合計", "淨收益", "保險收入"],  # 保險收入 = IFRS 17 保險業
    "cogs": ["營業成本合計"],
    "gross_profit": ["營業毛利（毛損）淨額", "營業毛利（毛損）"],
    "operating_expenses": ["營業費用合計"],
    "operating_income": ["營業利益（損失）", "營業利益"],
    "pretax_income": ["稅前淨利（淨損）", "繼續營業單位稅前淨利（淨損）", "繼續營業單位稅前損益",
                      "繼續營業單位稅前純益（純損）"],
    "net_income": ["本期淨利（淨損）", "本期稅後淨利（淨損）", "繼續營業單位本期純益（純損）"],
    # 淨利歸屬段落在綜合損益歸屬段落之前，「母公司業主」取第一個就是淨利那列
    "net_income_parent": ["母公司業主（淨利／損）", "母公司業主（淨利／淨損）", "母公司業主"],
    "eps": ["基本每股盈餘合計", "基本每股盈餘"],
}


def num(s):
    s = (s or "").replace(",", "").strip()
    if s in ("", "-"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    try:
        v = float(s.strip("()"))
    except ValueError:
        return None
    return -v if neg else v


def parse(report):
    rows = [(r[0].strip().replace("　", ""), num(r[1]), num(r[3])) for r in report if len(r) >= 4]
    cur, ly = {}, {}
    for canon, names in ROWS.items():
        for name in names:
            hit = next((r for r in rows if r[0] == name and (r[1] is not None or r[2] is not None)), None)
            if hit:
                if hit[1] is not None:
                    cur[canon] = hit[1]
                if hit[2] is not None:
                    ly[canon] = hit[2]
                break
    return cur, ly


def load(p):
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="")
    ap.add_argument("--codes", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--max", type=int, default=0)
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    # 以 TWSE 損益快照判斷誰已申報：季初大多數公司還沒交，別每天白打 2000 次
    inc_dir = os.path.join(config.DATA_DIR, "income_statement")
    filed = {f[:-5]: set(load(os.path.join(inc_dir, f))) for f in os.listdir(inc_dir) if f.endswith(".json")}
    period = a.period or max((p for ps in filed.values() for p in ps), default="")
    if not re.fullmatch(r"\d{4}Q[1-4]", period or ""):
        sys.exit(f"period 格式不對：{period}")
    roc, season = str(int(period[:4]) - 1911), period[-1]
    codes = [c.strip() for c in a.codes.split(",") if c.strip()] or sorted(c for c, ps in filed.items() if period in ps)
    os.makedirs(OUT_DIR, exist_ok=True)
    todo = [c for c in codes if a.force or period not in load(os.path.join(OUT_DIR, f"{c}.json"))]
    if a.max:
        todo = todo[:a.max]
    print(f"[MOPS {period}] 待抓 {len(todo)} 家（預估 {len(todo) * (SLEEP + 0.4) / 60:.0f} 分鐘）", flush=True)

    s = requests.Session()
    s.headers.update(HEADERS)
    fails = got = empty = 0
    for i, c in enumerate(todo, 1):
        j = None
        for _ in range(2):  # 單次逾時常見（大公司報表大），重試一次
            try:
                j = s.post(URL, json={"companyId": c, "dataType": "2", "year": roc, "season": season,
                                      "subsidiaryCompanyId": ""}, timeout=30).json()
                break
            except Exception as e:
                print(f"  ! {c} {type(e).__name__}", flush=True)
                time.sleep(10)
        if j is None:
            fails += 1
            if fails >= 3:
                print("連續 3 家連線失敗：可能被 MOPS 封 IP，中止（已抓的會保留）", flush=True)
                break
            continue
        fails = 0
        report = ((j.get("result") or {}).get("reportList")) or []
        cur, ly = parse(report)
        if not cur:
            empty += 1  # 尚未申報 / 查無資料
        else:
            p = os.path.join(OUT_DIR, f"{c}.json")
            d = load(p)
            d[period] = {"cur": cur, "ly": ly}
            with open(p, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1, sort_keys=True)
            got += 1
        if i % 100 == 0:
            print(f"  {i}/{len(todo)} 已存 {got}、查無 {empty}", flush=True)
        time.sleep(SLEEP)
    print(f"完成：存 {got} 家、查無 {empty} 家", flush=True)


if __name__ == "__main__":
    main()
