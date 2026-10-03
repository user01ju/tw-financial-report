const BASE = import.meta.env.BASE_URL;
export const dataUrl = (p) => `${BASE}data/${p}`;

const cache = new Map();
export async function fetchJson(p) {
  if (cache.has(p)) return cache.get(p);
  const r = await fetch(dataUrl(p));
  if (!r.ok) throw new Error(`${p}: ${r.status}`);
  const j = await r.json();
  cache.set(p, j);
  return j;
}

export const getLatest = () => fetchJson("fundamentals/_latest.json");
export const getLatestMonthly = () => fetchJson("fundamentals/_latest_monthly.json");
export const getCompany = (code) => fetchJson(`fundamentals/${code}.json`);
// 近一年報酬天天變,不放在 per-code 檔裡(見 metrics.py)，個股頁另抓這張小表
export const getPriceReturns = () => fetchJson("fundamentals/_price_returns.json");
export const getValuation = () => fetchJson("valuation/_latest.json");
export const getMeta = () => fetchJson("fundamentals/_meta.json");
export const getMarkets = () => fetchJson("markets.json"); // {code: "TWSE"|"TPEX"}，推 TV 用

// 金融(營收/利潤率定義不同，負債比天生高) + 營建(完工認列失真)：跨產業比較時排除。
// 少數沒有 CMoney 子類股的退回用證交所產業別判斷
export const isFinOrBuild = (r) =>
  r.sector
    ? r.sector_parent === "金融" || r.sector === "營建"
    : /金融|建材營造/.test(r.industry || "");
