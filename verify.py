# -*- coding: utf-8 -*-
"""資料正確性驗證 — VERIFICATION.md 的 Tier A / Tier B 實作。

  python verify.py --tier a     # 零外部呼叫，掛在 update.yml 的 metrics 之後、commit 之前
  python verify.py --tier b     # 交叉源不變量（含少量外部呼叫），走獨立的 verify.yml 每日排程
  python verify.py --tier all   # 兩層都跑（預設）

exit code: 0=全過/只有 SKIP，1=至少一條 FAIL，2=無 FAIL 但有 WARN。CI 只把 1 當失敗。

分層說明：Tier A 必須零網路且快（<10 秒）。Tier B 的五條裡只有
`price-return-vs-sector-gainer` 會打外部 API，其餘四條是「跨資料源不變量」
（損益表 vs 月營收、TTM vs 單季…），本機檔案就能算，但要全市場逐檔掃、
且語意上屬於 VERIFICATION.md 的 Tier B 清單，因此一併放這層。

只用標準庫（requirements.txt 只有 requests，這裡刻意不依賴它）。
"""
import argparse
import csv
import datetime
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
FUND = os.path.join(DATA, "fundamentals")

# ---------------------------------------------------------------- 門檻常數
# 每個門檻都附「為什麼是這個值」，紅了才判斷得出是資料壞還是門檻太緊。

# _meta.updated_at 落後上限（日曆天）。update.yml 每天 09:00 UTC 跑（含週末與國定
# 假日），metrics.py 每次執行都重寫 updated_at，所以這條**不需要交易日校正**——
# 非交易日一樣會有新的 updated_at。3 天 = 容許連兩次排程被 GitHub 丟掉。
FRESHNESS_MAX_DAYS = 3

# mg_score 全市場中位數合理區間。8 個因子各自做百分位(0-100)再加權平均，
# 百分位本身近似均勻分佈 → 加權平均的中位數必然逼近 50。偏離就是 rank 邏輯壞了。
# ±5 的餘裕留給「部分因子缺值使加權分母不同」造成的不對稱。實測 2026-08-01 = 49.1。
# 注意：這是「rank 徹底壞掉」的粗篩。2026-08-01 修的同值 tie bug 只讓 mg_score
# 平均動 0.76 分（median 位移 <1），**這條擋不住它** → 真正的 tie 回歸封印是
# 下面的 mg-score-recompute（獨立重算，會逐檔對得上）。
MG_MEDIAN_LO, MG_MEDIAN_HI = 45.0, 55.0
MG_RECOMPUTE_TOL = 0.05  # metrics 存的是 round(…, 1)，容許半個 last digit

# prices.json 每檔最新 key 應是本月或上月。停牌/下市股會永遠卡在舊月份（2026-08-01
# 實測 59/2043 = 2.9%），天天 WARN 只會造成告警疲勞 → 5% 以內視為正常殘留、
# 只把數字印出來；超過 5% 代表停更範圍在擴大；新鮮比例掉到 80% 以下就是 fetch_prices 整批壞了。
PRICE_STALE_WARN_FRAC = 0.05
PRICE_FRESH_MIN_FRAC = 0.80

PRICE_RETURN_TOL = 0.01  # _price_returns.json 存 round(…, 2)，重算應完全一致

# 季營收 vs Σ該季三個月月營收。月營收是自結值、季報是會計師核閱（合併範圍/沖銷
# 可能不同），3% 是 VERIFICATION.md 訂的容忍度。實測 2026-08-01：1923 檔中
# 26 檔(1.35%)超標，前段全是金融保險業（損益表「營業收入」定義本來就不同）。
QM_TOL_PCT = 3.0
QM_OUTLIER_WARN_FRAC = 0.03   # 超標比例 >3% = 比現況(1.35%)明顯惡化
QM_OUTLIER_FAIL_FRAC = 0.10   # >10% = 系統性壞掉

# 累計 YTD 污染的簽名是「季營收遠**大於**該季三個月合計」（Q2≈2倍、Q3≈3倍、Q4≈4倍）。
# 實測全市場正向偏離上限只有 +6.5%（排除月營收為負的怪股後），所以 +25% 門檻
# 既有巨大餘裕又能 100% 攔下 t187ap06 累計污染重現。這是本 repo 最有價值的一條。
QM_LEAK_PCT = 25.0

EPS_TTM_TOL = 0.02   # eps_ttm = round(Σ4 單季 EPS, 2)，只留捨入誤差
YOY_TOL_PP = 0.02    # revenue_yoy 是 round(…, 2) 的百分點

# decumulate() 湊不出前季累計時會丟棄該期。目前實測 0 期被丟；開始大量丟就是
# 來源缺期或 merge 邏輯壞了。
DROPPED_PERIOD_FAIL_FRAC = 0.01

# Tier B 外部呼叫（sector_gainer）：共 3 次 GET、每次之間 sleep，抽樣 ≤3 檔。
SG_RAW_BASE = "https://raw.githubusercontent.com/user01ju/sector_gainer/main/"
SAMPLE_MAX = 3
SLEEP_SECONDS = 1.0
HTTP_TIMEOUT = 30
SG_LIQUID_POOL = 60      # 先取當日成交額前 60 大，再依日期輪抽 3 檔（避免冷門股停牌雜訊）
SG_CLOSE_TOL_PCT = 0.5   # 兩邊都是同一交易日的官方收盤，實測 1854 檔完全相同
SG_RETURN_TOL_PP = 0.5

# mg_score 因子權重：**刻意複寫一份**（double-entry），不 import metrics。
# 改 metrics.MG_FACTORS 時這裡會紅 → 逼你確認是有意調權重，而不是誤改。
MG_FACTORS = {
    "revenue_yoy": 0.17, "operating_income_yoy": 0.11, "eps_yoy": 0.11,
    "revenue_yoy_accel": 0.14, "mrev_yoy_accel": 0.12,
    "mrev_yoy_3m": 0.15, "mrev_streak": 0.15, "price_return_1y": 0.05,
}
MG_EXCLUDE_SECTORS = {"營建"}

TPE = datetime.timezone(datetime.timedelta(hours=8))  # 台北無 DST，用固定位移免 tzdata 相依
QUARTER_MONTHS = {1: ("01", "02", "03"), 2: ("04", "05", "06"),
                  3: ("07", "08", "09"), 4: ("10", "11", "12")}
RE_QUARTER = re.compile(r"^\d{4}Q[1-4]$")
RE_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


# ---------------------------------------------------------------- 共用工具
def load(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def q_key(p):
    return (int(p[:4]), int(p[-1]))


def shift_month(ym, delta):
    y, m = int(ym[:4]), int(ym[5:7])
    i = y * 12 + (m - 1) + delta
    return f"{i // 12}-{i % 12 + 1:02d}"


def now_tpe():
    return datetime.datetime.now(TPE)


def is_weekend(d):
    """交易日退化路徑：本 repo 沒有任何日粒度的日期序列（prices.json 是月粒度），
    無法像 twse_website(market_calendar) 或 sector_gainer(market_index.csv) 那樣
    推出真正的交易日。所以只做「週末保守 SKIP」，國定假日不判斷。
    目前沒有任何一條檢查真的需要日粒度落後天數（見 FRESHNESS_MAX_DAYS 註解），
    這個 helper 只在月初尚未開盤的邊界情況用來降級。"""
    return d.weekday() >= 5


_scan_cache = None
NEED_MONTHLY = True  # main() 依 --tier 設定；Tier A 用不到月營收，跳過可省 1/3 檔案讀取


def scan():
    """單趟掃描所有 per-code 檔，只留小量彙總。

    data/fundamentals 有 94MB，**不能**把解析結果整份留在記憶體，因此在同一次
    迴圈裡把 Tier A 與 Tier B 需要的統計一次算完（省掉重複 IO）。"""
    global _scan_cache
    if _scan_cache is not None:
        return _scan_cache

    today = now_tpe().date()
    cur_q = f"{today.year}Q{(today.month - 1) // 3 + 1}"
    cur_m = f"{today.year}-{today.month:02d}"
    latest = load(os.path.join(FUND, "_latest.json")) or {}

    r = {
        "codes": [], "key_errors": [], "future_periods": [],
        "decum_checked": 0, "decum_skipped": 0, "decum_violations": [],
        "dropped": [], "inc_periods": 0,
        "qm": [], "qm_missing": 0,
        "eps_checked": 0, "eps_bad": [],
        "yoy_checked": 0, "yoy_bad": [],
    }
    codes = sorted(f[:-5] for f in os.listdir(FUND)
                   if f.endswith(".json") and not f.startswith("_"))
    r["codes"] = codes

    for code in codes:
        fd = load(os.path.join(FUND, f"{code}.json")) or {}
        q = fd.get("quarterly") or {}
        mo = fd.get("monthly") or {}

        # --- 期別鍵格式 / 未來期別 ---
        # 「無重複」由 JSON object 天然保證（同名鍵不可能並存），故只驗格式與時序。
        for p in q:
            if not RE_QUARTER.match(p):
                r["key_errors"].append((code, "quarterly", p))
            elif p > cur_q:  # 字串比較對 YYYYQn 等價於時序比較
                r["future_periods"].append((code, p))
        for m in mo:
            if not RE_MONTH.match(m):
                r["key_errors"].append((code, "monthly", m))
            elif m > cur_m:
                r["future_periods"].append((code, m))

        # --- decumulate 正確性：TWSE 原始累計值 == Σ 同年各單季（去累計後） ---
        inc = load(os.path.join(DATA, "income_statement", f"{code}.json")) or {}
        for p, rec in inc.items():
            if not RE_QUARTER.match(p):
                continue
            r["inc_periods"] += 1
            if p not in q:
                r["dropped"].append((code, p))
                continue
            if p.endswith("Q1"):
                continue  # Q1 累計即單季，無可驗證的恆等式
            raw = rec.get("營業收入")
            y, nq = p[:4], int(p[-1])
            parts = [q.get(f"{y}Q{k}", {}).get("revenue") for k in range(1, nq + 1)]
            if not isinstance(raw, (int, float)) or any(x is None for x in parts):
                r["decum_skipped"] += 1
                continue
            r["decum_checked"] += 1
            s = sum(parts)
            if abs(raw) > 1 and abs(s - raw) / abs(raw) > 1e-4:
                r["decum_violations"].append((code, p, raw, s))

        if not q:
            continue
        lp = max(q, key=q_key)

        # --- 季營收 vs Σ 該季三個月月營收（只有 Tier B 要，Tier A 不讀 monthly_revenue）---
        rev = q[lp].get("revenue")
        if NEED_MONTHLY and rev is not None:
            mr = load(os.path.join(DATA, "monthly_revenue", f"{code}.json")) or {}
            y, nq = int(lp[:4]), int(lp[-1])
            vals = []
            for mm in QUARTER_MONTHS[nq]:
                rec = mr.get(f"{y}-{mm}")
                v = rec.get("營業收入-當月營收") if rec else None
                if not isinstance(v, (int, float)):
                    vals = None
                    break
                # 單位橋接：FinMind 是元、TWSE 是仟元（fundamentals 統一用仟元）
                vals.append(v / 1000 if rec.get("_src") == "finmind" else v)
            if vals is None:
                r["qm_missing"] += 1
            elif sum(vals) != 0:
                ind = (latest.get(code) or {}).get("industry") or ""
                r["qm"].append((code, lp, rev, sum(vals), ind))

        # --- eps_ttm == Σ 近 4 個單季 EPS ---
        if "eps_ttm" in q[lp]:
            y, nq = q_key(lp)
            seq = []
            for _ in range(4):
                seq.append(f"{y}Q{nq}")
                nq -= 1
                if nq == 0:
                    nq, y = 4, y - 1
            eps = [q[s].get("eps") for s in seq if s in q]
            if len(eps) == 4 and all(isinstance(e, (int, float)) for e in eps):
                r["eps_checked"] += 1
                if abs(round(sum(eps), 2) - q[lp]["eps_ttm"]) > EPS_TTM_TOL:
                    r["eps_bad"].append((code, lp, round(sum(eps), 2), q[lp]["eps_ttm"]))

        # --- revenue_yoy 從存值重算（全部期別，不只最新） ---
        for p, rec in q.items():
            if "revenue_yoy" not in rec or rec.get("revenue") is None:
                continue
            py = f"{int(p[:4]) - 1}Q{p[-1]}"
            base = q.get(py, {}).get("revenue")
            if base in (None, 0):
                continue
            r["yoy_checked"] += 1
            exp = round((rec["revenue"] - base) / abs(base) * 100, 2)
            if abs(exp - rec["revenue_yoy"]) > YOY_TOL_PP:
                r["yoy_bad"].append((code, p, exp, rec["revenue_yoy"]))

    _scan_cache = r
    return r


def average_rank_pct(vals, n):
    """同值取平均名次的百分位（0-100）。刻意複寫 metrics.average_rank_pct 的語意，
    不 import——否則 tie bug 回歸時兩邊會一起錯，等於沒驗。"""
    if n <= 1:
        return {c: 50.0 for c, _ in vals}
    out = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and vals[j + 1][1] == vals[i][1]:
            j += 1
        p = round((i + j) / 2 / (n - 1) * 100, 4)
        for c, _ in vals[i:j + 1]:
            out[c] = p
        i = j + 1
    return out


# ---------------------------------------------------------------- Tier A
def check_fundamentals_freshness():
    meta = load(os.path.join(FUND, "_meta.json"))
    if not meta or not meta.get("updated_at"):
        return "FAIL", "找不到 data/fundamentals/_meta.json 或缺 updated_at"
    ts = datetime.datetime.fromisoformat(meta["updated_at"])
    lag = (datetime.datetime.now(datetime.timezone.utc) - ts).total_seconds() / 86400
    msg = f"_meta.updated_at={meta['updated_at']}，落後 {lag:.2f} 天（門檻 {FRESHNESS_MAX_DAYS}，日曆天）"
    return ("FAIL" if lag > FRESHNESS_MAX_DAYS else "PASS"), msg


def check_monthly_revenue_freshness():
    """月營收公告期限是次月 10 日，給到 15 日的寬限（含假日順延）。
    VERIFICATION.md 沒列，但 _meta.updated_at 在 CI 裡永遠是「剛剛」（metrics 每次
    重寫），只驗它抓不到「fetch_latest 靜默停止更新月營收」。"""
    meta = load(os.path.join(FUND, "_meta.json")) or {}
    lm = meta.get("latest_month")
    if not lm:
        return "FAIL", "_meta.json 缺 latest_month"
    today = now_tpe().date()
    cur = f"{today.year}-{today.month:02d}"
    expect = shift_month(cur, -1 if today.day > 15 else -2)
    msg = f"latest_month={lm}，今天 {today} 的最低期待 {expect}"
    return ("PASS" if lm >= expect else "FAIL"), msg


def check_quarter_freshness():
    """季報申報期限 Q1=5/15、Q2=8/14、Q3=11/14、Q4(年報)=3/31，各給 10 天寬限。
    VERIFICATION.md 沒列；抓「季報整批沒進來」（例如 t187ap06 全後綴 404）。"""
    meta = load(os.path.join(FUND, "_meta.json")) or {}
    lq = meta.get("latest_quarter")
    if not lq or not RE_QUARTER.match(lq):
        return "FAIL", f"_meta.latest_quarter 異常：{lq!r}"
    today = now_tpe().date()
    # (截止日, 對應季別) 由早到晚；取今天已過截止+寬限的最後一個
    deadlines = [((3, 31), f"{today.year - 1}Q4"), ((5, 15), f"{today.year}Q1"),
                 ((8, 14), f"{today.year}Q2"), ((11, 14), f"{today.year}Q3")]
    expect = f"{today.year - 2}Q4"
    for (mm, dd), q in deadlines:
        if today > datetime.date(today.year, mm, dd) + datetime.timedelta(days=10):
            expect = q
    msg = f"latest_quarter={lq}，今天 {today} 的最低期待 {expect}（申報期限+10 天寬限）"
    return ("PASS" if q_key(lq) >= q_key(expect) else "FAIL"), msg


def check_mg_score_range():
    latest = load(os.path.join(FUND, "_latest.json")) or {}
    vals = [v["mg_score"] for v in latest.values() if isinstance(v.get("mg_score"), (int, float))]
    if not vals:
        return "FAIL", "_latest.json 沒有任何 mg_score"
    out = [v for v in vals if not (0 <= v <= 100)]
    universe = sum(1 for v in latest.values() if v.get("sector") not in MG_EXCLUDE_SECTORS)
    if out:
        return "FAIL", f"{len(out)} 檔 mg_score 超出 [0,100]，例：{out[:5]}"
    cov = len(vals) / universe if universe else 0
    msg = f"{len(vals)} 檔皆在 [0,100]（min={min(vals)} max={max(vals)}），覆蓋 {cov:.1%} 的評分宇宙"
    return ("WARN" if cov < 0.80 else "PASS"), msg


def check_mg_score_median():
    latest = load(os.path.join(FUND, "_latest.json")) or {}
    vals = [v["mg_score"] for v in latest.values() if isinstance(v.get("mg_score"), (int, float))]
    if not vals:
        return "FAIL", "_latest.json 沒有任何 mg_score"
    med = statistics.median(vals)
    msg = f"全市場 median {med:.1f}（n={len(vals)}），區間 {MG_MEDIAN_LO}–{MG_MEDIAN_HI}"
    return ("PASS" if MG_MEDIAN_LO <= med <= MG_MEDIAN_HI else "FAIL"), msg


def check_mg_score_recompute():
    """獨立重算 mg_score 並逐檔比對——2026-08-01 修的「同值 rank 依 code 排開」
    tie bug 的真正回歸封印（那個 bug 只讓 median 位移 <1，中位數區間擋不住，
    但會讓數百檔的分數逐檔對不上）。"""
    latest = load(os.path.join(FUND, "_latest.json")) or {}
    codes = [c for c in latest if latest[c].get("sector") not in MG_EXCLUDE_SECTORS]
    if not codes:
        return "FAIL", "_latest.json 空或全被 sector 排除"
    pranks = {}
    for f in MG_FACTORS:
        vals = sorted(((c, latest[c][f]) for c in codes
                       if isinstance(latest[c].get(f), (int, float))), key=lambda x: x[1])
        pranks[f] = average_rank_pct(vals, len(vals))
    bad, n = [], 0
    for c in codes:
        num = wsum = 0.0
        for f, w in MG_FACTORS.items():
            if c in pranks[f]:
                num += pranks[f][c] * w
                wsum += w
        if wsum <= 0:
            continue
        n += 1
        exp, got = round(num / wsum, 1), latest[c].get("mg_score")
        if got is None or abs(exp - got) > MG_RECOMPUTE_TOL:
            bad.append((c, exp, got))
    # 被排除的類股不該有分數
    leaked = [c for c in latest if latest[c].get("sector") in MG_EXCLUDE_SECTORS
              and latest[c].get("mg_score") is not None]
    if leaked:
        return "FAIL", f"{len(leaked)} 檔應排除類股({MG_EXCLUDE_SECTORS})卻有 mg_score：{leaked[:5]}"
    if bad:
        ex = "、".join(f"{c} 應={e} 實={g}" for c, e, g in bad[:3])
        return "FAIL", f"{len(bad)}/{n} 檔 mg_score 與獨立重算不符（容差 {MG_RECOMPUTE_TOL}）：{ex}"
    return "PASS", f"{n} 檔 mg_score 與獨立重算逐檔相符（8 因子平均名次百分位加權）"


def check_period_keys():
    r = scan()
    if r["key_errors"]:
        ex = "、".join(f"{c}/{k}={p}" for c, k, p in r["key_errors"][:5])
        return "FAIL", f"{len(r['key_errors'])} 個期別鍵格式異常：{ex}"
    if r["future_periods"]:
        ex = "、".join(f"{c}={p}" for c, p in r["future_periods"][:5])
        return "FAIL", f"{len(r['future_periods'])} 個期別落在未來：{ex}"
    return "PASS", (f"{len(r['codes'])} 檔的季/月期別鍵格式正確且無未來期別"
                    "（JSON object 天然無重複鍵）")


def check_decumulation():
    """TWSE t187ap06 是年初至今累計 → 恆等式：raw累計(Qn) == Σ fundamentals 單季(Q1..Qn)。
    2026-08-01 之前 metrics 沒去累計時，這條會在全部 89 檔 Q2 上炸開。"""
    r = scan()
    if r["decum_checked"] == 0:
        return "SKIP", (f"沒有可驗的非 Q1 TWSE 期別（skipped={r['decum_skipped']}）"
                        "——季報季初或 backfill 未跑時屬正常")
    if r["decum_violations"]:
        c, p, raw, s = r["decum_violations"][0]
        return "FAIL", (f"{len(r['decum_violations'])}/{r['decum_checked']} 期去累計恆等式不成立，"
                        f"例：{c} {p} 原始累計={raw:.0f} 但單季合計={s:.0f}"
                        "（累計 YTD 污染回歸？見 metrics.decumulate）")
    return "PASS", (f"{r['decum_checked']} 期非 Q1 損益的去累計恆等式成立"
                    f"（skipped={r['decum_skipped']}）")


def check_income_period_coverage():
    r = scan()
    n, dropped = r["inc_periods"], r["dropped"]
    if n == 0:
        return "SKIP", "data/income_statement/ 沒有任何期別"
    frac = len(dropped) / n
    msg = f"{len(dropped)}/{n} 期（{frac:.2%}）存在於 income_statement 但沒進 fundamentals"
    if frac > DROPPED_PERIOD_FAIL_FRAC:
        ex = "、".join(f"{c}/{p}" for c, p in dropped[:5])
        return "FAIL", f"{msg}，超過門檻 {DROPPED_PERIOD_FAIL_FRAC:.0%}：{ex}"
    if dropped:
        return "WARN", f"{msg}（decumulate 湊不出前季累計會丟期，少量屬正常）"
    return "PASS", msg


def check_prices_latest_key():
    prices = load(os.path.join(DATA, "prices.json"))
    if not prices:
        return "FAIL", "找不到 data/prices.json 或內容為空"
    today = now_tpe().date()
    cur = f"{today.year}-{today.month:02d}"
    ok_keys = {cur, shift_month(cur, -1)}
    stale = {c: max(s) for c, s in prices.items() if s and max(s) not in ok_keys}
    empty = [c for c, s in prices.items() if not s]
    n = len(prices)
    fresh = (n - len(stale) - len(empty)) / n
    msg = (f"{n} 檔中 {len(stale)} 檔最新 key 非 {sorted(ok_keys)}"
           f"（{len(empty)} 檔無資料），新鮮比例 {fresh:.1%}")
    ex = "、".join(f"{c}={m}" for c, m in sorted(stale.items())[:5])
    if fresh < PRICE_FRESH_MIN_FRAC:
        return "FAIL", f"{msg}，低於門檻 {PRICE_FRESH_MIN_FRAC:.0%}：{ex}"
    if 1 - fresh > PRICE_STALE_WARN_FRAC:
        return "WARN", f"{msg}，停更比例超過 {PRICE_STALE_WARN_FRAC:.0%}：{ex}"
    return "PASS", msg + (f"；停牌/下市殘留：{ex}" if ex else "")


def check_price_return_recompute():
    prices = load(os.path.join(DATA, "prices.json")) or {}
    stored = load(os.path.join(FUND, "_price_returns.json"))
    if stored is None:
        return "FAIL", "找不到 data/fundamentals/_price_returns.json"
    bad, n = [], 0
    for code, s in prices.items():
        if not s:
            continue
        lt = max(s)
        ref = f"{int(lt[:4]) - 1}-{lt[5:7]}"
        exp = round((s[lt] / s[ref] - 1) * 100, 2) if s.get(ref) else None
        got = stored.get(code)
        if exp is None and got is None:
            continue
        n += 1
        if exp is None or got is None or abs(exp - got) > PRICE_RETURN_TOL:
            bad.append((code, exp, got))
    if bad:
        ex = "、".join(f"{c} 應={e} 實={g}" for c, e, g in bad[:3])
        return "FAIL", f"{len(bad)}/{n} 檔 price_return_1y 與 prices.json 重算不符：{ex}"
    return "PASS", f"{n} 檔 price_return_1y 與 prices.json 月序列重算一致"


def check_cross_section_size():
    """_latest.json 是前端所有列表頁的資料來源；metrics 半途壞掉會讓它縮水而
    per-code 檔仍在（VERIFICATION.md 未列）。"""
    latest = load(os.path.join(FUND, "_latest.json")) or {}
    meta = load(os.path.join(FUND, "_meta.json")) or {}
    r = scan()
    n_files, n_latest = len(r["codes"]), len(latest)
    if meta.get("count") != n_latest:
        return "FAIL", f"_meta.count={meta.get('count')} 與 _latest.json 檔數 {n_latest} 不一致"
    if n_files == 0:
        return "FAIL", "data/fundamentals/ 沒有任何 per-code 檔"
    frac = n_latest / n_files
    msg = f"_latest.json {n_latest} 檔 / per-code {n_files} 檔 = {frac:.1%}"
    return ("FAIL" if frac < 0.80 else "PASS"), msg


# ---------------------------------------------------------------- Tier B
def check_quarterly_vs_monthly():
    """季營收 ≈ Σ 該季三個月月營收。金融保險業一併納入統計但通常會超標
    （損益表「營業收入」與月營收定義不同），所以用「超標比例」而非「零容忍」。"""
    r = scan()
    rows = r["qm"]
    if not rows:
        return "SKIP", "沒有可比對的（季營收 + 完整三個月月營收）樣本"
    devs = [(abs(rev - s) / abs(s) * 100, c, p, rev, s, ind) for c, p, rev, s, ind in rows]
    over = sorted((d for d in devs if d[0] > QM_TOL_PCT), reverse=True)
    frac = len(over) / len(devs)
    med = statistics.median(d[0] for d in devs)
    ex = "、".join(f"{d[1]}/{d[2]} {d[0]:.1f}%({d[5] or '?'})" for d in over[:3])
    msg = (f"{len(devs)} 檔比對，median 偏離 {med:.2f}%，超過 {QM_TOL_PCT}% 者 "
           f"{len(over)} 檔（{frac:.2%}，缺月營收 {r['qm_missing']} 檔）"
           + (f"；最大：{ex}" if ex else ""))
    if frac > QM_OUTLIER_FAIL_FRAC:
        return "FAIL", f"{msg} — 超過 FAIL 門檻 {QM_OUTLIER_FAIL_FRAC:.0%}"
    if frac > QM_OUTLIER_WARN_FRAC:
        return "WARN", f"{msg} — 超過 WARN 門檻 {QM_OUTLIER_WARN_FRAC:.0%}"
    return "PASS", msg


def check_quarterly_revenue_leak():
    """累計 YTD 污染的方向性簽名：季營收**大幅超出**該季三個月合計。
    Q2 污染 ≈ +100%、Q3 ≈ +200%。實測正向偏離全市場上限只有 +6.5%，門檻 25% 有巨大餘裕。"""
    r = scan()
    rows = [x for x in r["qm"] if x[3] > 0]  # 月營收合計為負/零的怪股跳過，百分比無意義
    if not rows:
        return "SKIP", "沒有可比對的樣本"
    leaks = sorted(((rev / s - 1) * 100, c, p, rev, s)
                   for c, p, rev, s, _ in rows if (rev / s - 1) * 100 > QM_LEAK_PCT)
    worst = max((rev / s - 1) * 100 for c, p, rev, s, _ in rows)
    if leaks:
        d, c, p, rev, s = leaks[-1]
        return "FAIL", (f"{len(leaks)}/{len(rows)} 檔季營收超出三個月合計 >{QM_LEAK_PCT}%，"
                        f"最大 {c} {p} +{d:.0f}%（季={rev:.0f} 月合計={s:.0f}）"
                        "——t187ap06 累計 YTD 污染的簽名")
    return "PASS", (f"{len(rows)} 檔中無季營收超出三個月合計 >{QM_LEAK_PCT}% 者"
                    f"（實際最大 +{worst:.2f}%）")


def check_eps_ttm():
    r = scan()
    if r["eps_checked"] == 0:
        return "SKIP", "沒有可驗的 eps_ttm（需連續 4 季 EPS）"
    if r["eps_bad"]:
        ex = "、".join(f"{c}/{p} Σ單季={e} 存值={g}" for c, p, e, g in r["eps_bad"][:3])
        return "FAIL", f"{len(r['eps_bad'])}/{r['eps_checked']} 檔 eps_ttm ≠ Σ 近 4 單季 EPS：{ex}"
    return "PASS", f"{r['eps_checked']} 檔 eps_ttm == Σ 近 4 單季 EPS（容差 {EPS_TTM_TOL}）"


def check_revenue_yoy():
    r = scan()
    if r["yoy_checked"] == 0:
        return "SKIP", "沒有可驗的 revenue_yoy"
    if r["yoy_bad"]:
        ex = "、".join(f"{c}/{p} 應={e} 實={g}" for c, p, e, g in r["yoy_bad"][:3])
        return "FAIL", f"{len(r['yoy_bad'])}/{r['yoy_checked']} 期 revenue_yoy 重算不符：{ex}"
    return "PASS", f"{r['yoy_checked']} 期 revenue_yoy 與存值重算一致（容差 {YOY_TOL_PP} pp）"


def _sg_get(path):
    req = urllib.request.Request(SG_RAW_BASE + path, headers={"User-Agent": "financial_report-verify"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        if resp.status != 200:
            raise urllib.error.HTTPError(path, resp.status, "non-200", None, None)
        return resp.read().decode("utf-8-sig")


def check_price_vs_sector_gainer():
    """prices.json 的月底收盤 vs sector_gainer 同一交易日的收盤（兩邊都是**未還原**
    權息的原始收盤，同日同價才可比）。共 3 次 GET、抽 ≤3 檔。

    交易日來源用 sector_gainer 自己的 data/market_index.csv 日期序列（spec 的
    「用既有資料檔推交易日」路徑），本 repo 沒有日粒度日期可用。

    注意：prices.json 2025 年的月份是 seed_prices.py 從 sector_gainer 種進來的
    （本 repo 2026-06-22 才建立），所以「去年同月」那一腳不是完全獨立的交叉源，
    它驗的是 seed 之後沒被改壞；本月那一腳（TWSE STOCK_DAY_ALL 抓的）才是真交叉。"""
    prices = load(os.path.join(DATA, "prices.json"))
    if not prices:
        return "FAIL", "找不到 data/prices.json"
    today = now_tpe().date()
    cur = f"{today.year}-{today.month:02d}"
    m_tgt = shift_month(cur, -1)          # 上一個完整月
    m_ref = shift_month(m_tgt, -12)

    try:
        days = [ln.split(",")[0] for ln in _sg_get("data/market_index.csv").strip().splitlines()[1:]]
        d_tgt = max((d for d in days if d.startswith(m_tgt)), default=None)
        d_ref = max((d for d in days if d.startswith(m_ref)), default=None)
        if not d_tgt or not d_ref:
            return "SKIP", (f"sector_gainer 沒有 {m_tgt} 或 {m_ref} 的交易日"
                            f"（其資料起於 {days[0] if days else '?'}）")
        time.sleep(SLEEP_SECONDS)
        rows_t = {r["id"]: r for r in csv.DictReader(_sg_get(f"data/daily/{d_tgt}.csv").splitlines())}
        time.sleep(SLEEP_SECONDS)
        rows_r = {r["id"]: r for r in csv.DictReader(_sg_get(f"data/daily/{d_ref}.csv").splitlines())}
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        return "SKIP", f"sector_gainer raw 取用失敗（對方掛掉不算我方資料錯）：{e}"

    cands = []
    for code, s in prices.items():
        r_t, r_r = rows_t.get(code), rows_r.get(code)
        if not r_t or not r_r or m_tgt not in s or m_ref not in s:
            continue
        try:
            turn, c_t, c_r = float(r_t["turnover"] or 0), float(r_t["close"]), float(r_r["close"])
            if float(r_r["turnover"] or 0) <= 0 or turn <= 0 or c_r <= 0:
                continue
        except (ValueError, KeyError):
            continue
        cands.append((turn, code, c_t, c_r, s[m_tgt], s[m_ref]))
    if not cands:
        return "SKIP", f"兩邊沒有共同可比的代號（{d_tgt} / {d_ref}）"

    # 取成交額前 SG_LIQUID_POOL 大（確定有成交、無停牌雜訊），再依 day-of-year 輪抽 3 檔：
    # 每天抽不同 3 檔，長期覆蓋面廣；同一天重跑結果可重現，紅了查得動。
    cands.sort(reverse=True)
    pool = cands[:SG_LIQUID_POOL]
    start = (today.timetuple().tm_yday * SAMPLE_MAX) % len(pool)
    sample = [pool[(start + i) % len(pool)] for i in range(min(SAMPLE_MAX, len(pool)))]

    bad, detail = [], []
    for _, code, c_t, c_r, p_t, p_r in sample:
        d1 = abs(p_t - c_t) / c_t * 100
        d2 = abs(p_r - c_r) / c_r * 100
        ret_sg, ret_fr = (c_t / c_r - 1) * 100, (p_t / p_r - 1) * 100
        detail.append(f"{code} {p_t}/{c_t}@{d_tgt} {p_r}/{c_r}@{d_ref} 報酬 {ret_fr:+.2f}/{ret_sg:+.2f}%")
        if d1 > SG_CLOSE_TOL_PCT or d2 > SG_CLOSE_TOL_PCT or abs(ret_sg - ret_fr) > SG_RETURN_TOL_PP:
            bad.append(f"{code}(收盤差 {d1:.2f}%/{d2:.2f}%，報酬差 {abs(ret_sg - ret_fr):.2f}pp)")
    if bad:
        return "FAIL", (f"抽樣 {len(sample)} 檔，{len(bad)} 檔與 sector_gainer 對不上"
                        f"（容差 收盤 {SG_CLOSE_TOL_PCT}% / 報酬 {SG_RETURN_TOL_PP}pp）：{'、'.join(bad)}")
    return "PASS", (f"抽樣 {len(sample)}/{len(cands)} 檔，月底收盤與近一年報酬皆相符 — "
                    + "；".join(detail))


# ---------------------------------------------------------------- runner
CHECKS = [
    ("a", "fundamentals-freshness", check_fundamentals_freshness),
    ("a", "monthly-revenue-freshness", check_monthly_revenue_freshness),
    ("a", "quarter-freshness", check_quarter_freshness),
    ("a", "mg-score-range", check_mg_score_range),
    ("a", "mg-score-median", check_mg_score_median),
    ("a", "mg-score-recompute", check_mg_score_recompute),
    ("a", "fundamentals-period-keys", check_period_keys),
    ("a", "decumulation-identity", check_decumulation),
    ("a", "income-period-coverage", check_income_period_coverage),
    ("a", "prices-latest-key", check_prices_latest_key),
    ("a", "price-return-recompute", check_price_return_recompute),
    ("a", "cross-section-size", check_cross_section_size),
    ("b", "quarterly-vs-monthly-revenue", check_quarterly_vs_monthly),
    ("b", "quarterly-revenue-cumulative-leak", check_quarterly_revenue_leak),
    ("b", "eps-ttm-consistency", check_eps_ttm),
    ("b", "revenue-yoy-recompute", check_revenue_yoy),
    ("b", "price-return-vs-sector-gainer", check_price_vs_sector_gainer),
]


def main():
    ap = argparse.ArgumentParser(description="財報資料驗證（見 VERIFICATION.md）")
    ap.add_argument("--tier", choices=["a", "b", "all"], default="all")
    args = ap.parse_args()
    global NEED_MONTHLY
    NEED_MONTHLY = args.tier in ("b", "all")
    for stream in (sys.stdout, sys.stderr):  # Windows 主控台預設 cp950，中文會炸
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    tally = {"PASS": 0, "FAIL": 0, "WARN": 0, "SKIP": 0}
    for tier, name, fn in CHECKS:
        if args.tier != "all" and tier != args.tier:
            continue
        try:
            status, msg = fn()
        except Exception as e:  # 單條爆掉不能拖垮其他檢查
            status, msg = "FAIL", f"檢查本身拋出例外：{type(e).__name__}: {e}"
        tally[status] = tally.get(status, 0) + 1
        print(f"[{status}] {name} — {msg}", flush=True)

    print(f"verify: {tally['PASS']} passed, {tally['FAIL']} failed, "
          f"{tally['WARN']} warned, {tally['SKIP']} skipped (tier={args.tier})")
    return 1 if tally["FAIL"] else (2 if tally["WARN"] else 0)


if __name__ == "__main__":
    sys.exit(main())
