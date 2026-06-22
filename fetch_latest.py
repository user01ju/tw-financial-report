# -*- coding: utf-8 -*-
"""抓 TWSE/TPEX OpenAPI 最新快照，normalize 後 merge 進 per-company 時序 JSON。

用法:
    python fetch_latest.py                 # 抓全部 (月營收+損益+資產負債)
    python fetch_latest.py monthly_revenue # 只抓某一類

特性:
- 數字字串轉 int/float，空字串轉 None。
- 民國年自動轉西元；period 統一成 "2026-05" / "2026Q1"。
- 每次原始回應備份到 raw/，方便稽核或重跑。
- per-company 檔以 period 為 key，重跑同期會覆蓋(冪等)。
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests

import config

session = requests.Session()
session.headers.update({"User-Agent": "fin-report-bot/1.0"})


def fetch_json(url, retries=3):
    for i in range(retries):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 404:
                return None  # 不存在的產業別後綴，跳過
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else None
        except Exception as e:
            if i == retries - 1:
                print(f"  ! 放棄 {url}: {e}")
                return None
            time.sleep(2 * (i + 1))


def to_number(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if s in ("", "-", "--", "N/A"):
        return None
    try:
        return int(s) if re.fullmatch(r"-?\d+", s) else float(s)
    except ValueError:
        return s  # 非數字欄位(名稱/產業/備註)原樣保留


def roc_month_to_period(yyymm):
    """民國 '11505' -> '2026-05'"""
    s = str(yyymm).strip()
    year = int(s[:-2]) + 1911
    return f"{year}-{s[-2:]}"


def roc_year_q_to_period(year, q):
    """年度 '115' + 季別 '1' -> '2026Q1'"""
    return f"{int(year) + 1911}Q{int(q)}"


# 官方各表 meta 欄位名不一致(TWSE中文 / TPEX季報英文)，統一對應
ALIASES = {
    "公司代號": ("公司代號", "SecuritiesCompanyCode", "Code"),
    "公司名稱": ("公司名稱", "CompanyName"),
    "產業別": ("產業別",),
    "年度": ("年度", "Year"),
    "季別": ("季別", "Season"),
    "資料年月": ("資料年月",),
}


# 「產表時間」類欄位：每次出表會變、非真實資料，丟棄以免每日假 diff
DROP_FIELDS = {"出表日期", "Date", "create_time"}


def pick(rec, canonical):
    for k in ALIASES[canonical]:
        if k in rec and str(rec[k]).strip():
            return rec[k]
    return None


def normalize_record(rec, period_kind):
    """回傳 (代號, period, record)；period 缺失回傳 None 讓上層跳過。"""
    code = pick(rec, "公司代號")
    if code is None:
        return None
    if period_kind == "month":
        ym = pick(rec, "資料年月")
        if ym is None:
            return None
        period = roc_month_to_period(ym)
    else:
        y, q = pick(rec, "年度"), pick(rec, "季別")
        if y is None or q is None:
            return None
        period = roc_year_q_to_period(y, q)
    # 輸出：英文 meta key 一律改回中文 canonical，財報科目原樣保留
    # 濾掉「產表時間」類欄位：它們每次出表會變但不是真實資料，留著會造成每日假 diff
    rename = {alias: canon for canon, aliases in ALIASES.items() for alias in aliases}
    out = {
        rename.get(k, k): to_number(v)
        for k, v in rec.items()
        if k not in DROP_FIELDS
    }
    return str(code).strip(), period, out


def load(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=True)


def run_dataset(name):
    spec = config.DATASETS[name]
    out_dir = os.path.join(config.DATA_DIR, name)
    companies = {}  # 順手更新主檔
    by_company = {}  # 代號 -> {period: record}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    for url in spec["urls"]:
        records = fetch_json(url)
        if not records:
            continue
        print(f"  {url.split('/')[-1]}: {len(records)} 筆")
        # 原始備份
        dump(os.path.join(config.RAW_DIR, name, f"{url.split('/')[-1]}_{stamp}.json"), records)
        for rec in records:
            parsed = normalize_record(rec, spec["period_kind"])
            if parsed is None:
                continue
            code, period, norm = parsed
            by_company.setdefault(code, {})[period] = norm
            companies[code] = {
                "name": pick(rec, "公司名稱"),
                "industry": pick(rec, "產業別"),
            }

    # merge 進既有時序檔
    for code, periods in by_company.items():
        path = os.path.join(out_dir, f"{code}.json")
        existing = load(path)
        existing.update(periods)
        dump(path, existing)
    print(f"  -> 寫入 {len(by_company)} 家公司")
    return companies


def update_master(all_companies):
    path = os.path.join(config.DATA_DIR, "companies.json")
    master = load(path)
    for code, info in all_companies.items():
        master.setdefault(code, {}).update({k: v for k, v in info.items() if v})
    dump(path, master)


def main():
    targets = sys.argv[1:] or list(config.DATASETS)
    all_companies = {}
    for name in targets:
        print(f"[{name}]")
        all_companies.update(run_dataset(name))
    update_master(all_companies)
    print("完成。")


if __name__ == "__main__":
    main()
