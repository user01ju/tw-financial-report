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
