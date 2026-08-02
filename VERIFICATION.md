# 資料正確性驗證

> 2026-08-01 規劃、2026-08-02 實作。四專案通用框架（Tier A 每次 CI / Tier B 每日交叉源 / Tier C golden）。
> 本檔描述**現況**，不是計畫。

## 怎麼跑

```bash
python verify.py --tier a      # 零外部呼叫，<10 秒
python verify.py --tier b      # 交叉源，會打外部 API
python verify.py               # 預設 all
```

exit code：`0` 全過（或只有 SKIP）／`1` 至少一條 FAIL／`2` 沒 FAIL 但有 WARN。CI 只把 `1` 當失敗。

輸出每條一行 `[PASS|FAIL|WARN|SKIP] <check-id> — <訊息>`，訊息一律帶實際數值與門檻，紅了要能直接判斷是資料壞還是門檻訂太緊。所有檢查跑完才決定 exit code（不 fail-fast），單條拋例外只毒死自己。

## CI 掛法

- **Tier A** → `.github/workflows/update.yml`，位置在 `metrics.py` 之後、commit step 之前。FAIL 擋掉 commit：壞資料不進 repo。
- **Tier B** → `.github/workflows/verify.yml`，每日台北 21:30（UTC 13:30）獨立排程 + `workflow_dispatch`。排在本 repo 的 update（UTC 09:00）與 sector_gainer 的 daily 之後，兩邊都更新完才比對。FAIL 只讓這個 workflow 紅，不影響資料更新。

## Tier A（12 條，零外部呼叫）

| check-id | 驗什麼 |
|---|---|
| `fundamentals-freshness` | `_latest.json` meta 日期落後 ≤3 天 |
| `monthly-revenue-freshness` | 最新月營收期別符合當日最低期待 |
| `quarter-freshness` | 最新季別符合申報期限 +10 天寬限 |
| `mg-score-range` | mg_score 全在 [0,100] |
| `mg-score-median` | 全市場 median 落在 45–55 |
| `mg-score-recompute` | 逐檔重算 8 因子平均名次百分位加權 |
| `fundamentals-period-keys` | 季/月期別鍵格式正確、無未來期別 |
| `decumulation-identity` | 非 Q1 損益的去累計恆等式成立 |
| `income-period-coverage` | income_statement 的期別都有進 fundamentals |
| `prices-latest-key` | 各檔最新 key = 本月或上月 |
| `price-return-recompute` | `price_return_1y` 與 prices.json 月序列一致 |
| `cross-section-size` | `_latest.json` 檔數 vs per-code 檔數 |

`mg-score-median` 的 45–55 是 percentile 加權的數學性質，偏了就是 rank 邏輯壞——這條是 2026-08-01 修的同值 tie bug 的迴歸測試。

## Tier B（5 條，交叉源）

| check-id | 驗什麼 |
|---|---|
| `quarterly-vs-monthly-revenue` | **季營收 ≈ Σ 該季三個月月營收**（tolerance 3%，月營收是自結值） |
| `quarterly-revenue-cumulative-leak` | 季營收不得超出三個月合計 >25% |
| `eps-ttm-consistency` | `eps_ttm` = Σ 近 4 個單季 EPS |
| `revenue-yoy-recompute` | `revenue_yoy` 從存值重算比對 |
| `price-return-vs-sector-gainer` | 抽 3 檔月底收盤與近一年報酬 vs sector_gainer |

前兩條合起來封印 t187ap06 累計 YTD 污染那個 bug class（2026-08-01 用 1232 人工驗出來的那件事）——累計污染再發生時當天就紅。實測 1923 檔 median 偏離 0.00%，超過 3% 的 26 檔集中在金融保險業，那類公司本來就不該用營收比對。

`price-return-vs-sector-gainer` 注意：兩邊都必須用**未還原** close 才可比（prices.json 未還原權息）。資料走 `raw.githubusercontent.com` 抓 sector_gainer 的公開產物，不需要 sibling checkout。

外部源掛掉／超時／非 200 一律 SKIP（對方掛不是我們資料錯），只有「兩邊都拿到資料但數字對不起來」才 FAIL。抽樣上限 3 檔、呼叫間隔 ≥1 秒。

## Cross-repo

原規劃的「cross-repo 週檢獨立掛一份」**沒有實作，也不打算做**。三條互驗已分散進各 repo 的 Tier B：

- 指數對帳、exrights 超集 → sector_gainer
- 月底收盤（本 repo `data/prices.json` ↔ sector_gainer `data/daily/*.csv`）→ 本 repo 的 `price-return-vs-sector-gainer`

四個 repo 資料都公開，全走 `raw.githubusercontent`。再獨立開一份等於重複實作同一批比對，還多一份要維護。

## 沒做的

- **Tier C golden regression**：commit 縮樣 snapshot → 跑 `metrics.py` → diff `fundamentals/` 輸出。metrics 是純函數、重跑冪等，最適合 golden。這輪刻意沒做。
- **前端 smoke**：資料層 JSON 驗完後剩的風險只有前端接錯欄位。可加最小 Playwright smoke（build 後開 Screener 頁，確認 `_latest.json` mg_score 第一名的代號出現在表上，~10 行）。

## ⚠️ 未驗證的前提

整套的告警依賴「FAIL → exit 1 → workflow 紅 → GitHub 寄信」。**這條路徑還沒實測過。**GitHub 的失敗通知是綁 scheduled run 的，手動/dispatch 觸發的失敗行為未確認。不寄信的話這些檢查全是白寫的——要故意讓一條檢查失敗跑一次才驗得了。
