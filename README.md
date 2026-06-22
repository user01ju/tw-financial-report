# 台灣上市櫃財報資料庫

官方免費源 (TWSE / TPEX OpenAPI) → normalize → per-company 時序 JSON，供年報/季報/月營收分析與基本面使用。

## 現況

`fetch_latest.py` 已可抓**最新一期**快照並寫入 `data/`：

- 月營收 ~1972 家、損益表/資產負債表 ~1965 家
- per-company 時序檔，重跑同期冪等覆蓋，跨期 append

```bash
pip install -r requirements.txt
python fetch_latest.py                 # 全抓
python fetch_latest.py monthly_revenue # 單抓
```

## 資料夾

```
data/companies.json            代號→名稱/產業 主檔
data/monthly_revenue/<code>.json  { "2026-05": {...} }
data/income_statement/<code>.json { "2026Q1": {...} }
data/balance_sheet/<code>.json
raw/                           每次抓取原始備份(稽核/重跑)
```

## ⚠️ OpenAPI 只有「最新一期」

TWSE/TPEX openapi 不回傳歷史。所以：

- **增量更新**：靠排程定期跑 `fetch_latest.py` 累積（從現在起的資料自動成時序）
- **歷史回補**：openapi 補不了，需另解（見下）

## 定時更新時程（財報法定公布期限）

| 項目 | 公布期限 | 建議排程 |
|---|---|---|
| 月營收 | 次月 10 日前 | 每月 11、15、20 日各跑一次（補晚交的） |
| Q1 季報 | 5/15 | 5/16、5/20、5/31 |
| 半年報 (Q2) | 8/14 | 8/15、8/20、8/31 |
| Q3 季報 | 11/14 | 11/15、11/20、11/30 |
| 年報 (Q4) | 隔年 3/31 | 4/1、4/10、4/30 |

> 金融業期限不同（半年報 8/31）。多跑幾次是因為延遲申報、更正後重編。

**排程方式（擇一）：**

1. **GitHub Actions cron**（推薦，為日後網頁鋪路）：repo 內 cron 跑 fetch → commit JSON → 自動部署到 GitHub/Cloudflare Pages。免費、雲端、不依賴本機開機。
2. **Windows 工作排程器**：本機 `schtasks` 跑 `python fetch_latest.py`，簡單但要本機常開。

## 歷史回補（FinMind，一次性）

`backfill_finmind.py` 已實作。openapi 無歷史，用 FinMind 補齊到接點。

```bash
set FINMIND_TOKEN=xxxx            # 申請免費 token：600/hr(無 token 僅 300/hr)
python backfill_finmind.py                    # 全市場，預設 2015 起
python backfill_finmind.py --start 2018-01-01
python backfill_finmind.py --codes 2330,2317  # 指定股
```

- 每檔 3 次呼叫（月營收/損益/資產），全市場 ~5900 次 → 有 token 約 10hr、無 token 約 20hr
- **可續跑**：進度存 `data/finmind/_progress.json`，Ctrl+C 後重跑自動接續；402 限額自動退避
- **月營收**併入既有 `data/monthly_revenue/`（同 TWSE 欄名，不覆蓋既有期）
- **損益/資產**為 long format，pivot 成 `{period: {type: value}}` 存 `data/finmind/`，保留來源純淨

> FinMind `type` 是英文碼（Revenue/GrossProfit/OperatingIncome/EPS…），與 TWSE 中文欄名不同；
> 由 `metrics.py`(待辦) 的 canonical mapping 橋接，不在儲存層硬湊。

### 申請 FinMind token

註冊 https://finmindtrade.com → 會員中心取得 token。**強烈建議**，否則 300/hr 全市場要跑快一天。

## 基本面指標（metrics.py）

`metrics.py` 已實作。橋接 TWSE 中文欄名 ↔ FinMind type 碼 → canonical，算季 ratio/TTM/YoY + 月營收。

```bash
python metrics.py            # 全市場
python metrics.py 2330 2317  # 指定股
```

輸出：
- `data/fundamentals/<code>.json`：`{quarterly:{period:{...}}, monthly:{month:{...}}}`
- `data/fundamentals/_latest.json`：全市場最新季橫斷面（排行/篩選一檔讀完）

已算欄位：
- **獲利能力(%)**：gross_margin、operating_margin、net_margin、roe_q/roe_ttm、roa_q/roa_ttm
- **成長性(%)**：revenue_yoy、eps_yoy、net_income_yoy（單季）；月營收 mom/yoy
- **財務結構(%)**：debt_ratio、current_ratio
- **TTM**：revenue_ttm、net_income_ttm、eps_ttm（近四季連續才算）
- 估值（PE/PB）**未做**：需另抓股價配 eps_ttm / 每股淨值

> **單位**：所有金額統一為**仟元**（TWSE 原生；FinMind 的元已 /1000）。EPS=元/股，ratio=%。
> 同期 TWSE 官方優先於 FinMind；TWSE 英文 type 碼與中文欄名由 `INCOME_MAP/BALANCE_MAP` 對應。

### 篩選範例

```python
import json
d = json.load(open("data/fundamentals/_latest.json", encoding="utf-8"))
# 高 ROE + 低負債 + 營收正成長
hits = [v for v in d.values()
        if (v.get("roe_ttm") or 0) > 15
        and (v.get("debt_ratio") or 100) < 40
        and (v.get("revenue_yoy") or -1) > 0]
hits.sort(key=lambda v: v["roe_ttm"], reverse=True)
```

## 待辦

- [ ] 產業別表單後綴驗證：`config.INDUSTRY_SUFFIXES` 目前 `ci/fh/basi/bd/ins`，已實測有資料但請對照 https://openapi.twse.com.tw/ 目錄確認無遺漏
- [x] 歷史回補腳本 `backfill_finmind.py`
- [x] `metrics.py` 基本面指標（橋接 + ratio/TTM/YoY + 月營收 + 橫斷面）
- [ ] 排程設定（GitHub Actions 建議）→ fetch_latest + metrics 串成 pipeline
- [ ] 估值指標（需抓股價）
