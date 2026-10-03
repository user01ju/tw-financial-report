# -*- coding: utf-8 -*-
"""官方 OpenAPI 端點設定。

注意：
- 這些 openapi 只回傳「最新一期」快照，沒有歷史。歷史回補另走 MOPS 彙總。
- `_ci` = 一般業。金控/銀行/證券/保險用不同表單後綴，下面列一組讓程式試抓，
  抓不到(404/空)就跳過。請對照 https://openapi.twse.com.tw/ 目錄確認正確後綴。
"""

TWSE_BASE = "https://openapi.twse.com.tw/v1/opendata"
TPEX_BASE = "https://www.tpex.org.tw/openapi/v1"

# 產業別表單後綴：一般業 / 金控 / 銀行 / 證券期貨 / 保險 / 異業
# mim(異業，2026-10-03 補)：2207 和泰車、1409 新纖、1718 中纖、2905 三商…沒抓它就只剩 FinMind 舊季，
# 在橫斷面裡永遠停在上一季。欄名不同(「收入」而非「營業收入」、無營業利益)，見 metrics.INCOME_MAP。
INDUSTRY_SUFFIXES = ("ci", "fh", "basi", "bd", "ins", "mim")

DATASETS = {
    "monthly_revenue": {
        "urls": [
            f"{TWSE_BASE}/t187ap05_L",
            f"{TPEX_BASE}/mopsfin_t187ap05_O",
        ],
        "period_kind": "month",  # 用「資料年月」(民國YYYMM)
    },
    "income_statement": {
        "urls": [f"{TWSE_BASE}/t187ap06_L_{s}" for s in INDUSTRY_SUFFIXES]
        + [f"{TPEX_BASE}/mopsfin_t187ap06_O_{s}" for s in INDUSTRY_SUFFIXES],
        "period_kind": "quarter",  # 用「年度」+「季別」
    },
    "balance_sheet": {
        "urls": [f"{TWSE_BASE}/t187ap07_L_{s}" for s in INDUSTRY_SUFFIXES]
        + [f"{TPEX_BASE}/mopsfin_t187ap07_O_{s}" for s in INDUSTRY_SUFFIXES],
        "period_kind": "quarter",
    },
}

DATA_DIR = "data"
RAW_DIR = "raw"
