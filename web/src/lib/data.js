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
export const getValuation = () => fetchJson("valuation/_latest.json");
export const getMeta = () => fetchJson("fundamentals/_meta.json");
