import { useState } from "react";
import { getMarkets } from "../lib/data.js";

// 本機 tv_serve.py(tv_push repo)常駐 helper：GitHub Pages 頁面直推 TV watchlist。
// helper 沒開就 fallback 複製 + 下載 txt，手動匯入 TV。
const HELPER = "http://127.0.0.1:5177/push";
const CONFIRM_OVER = 300; // 沒篩就整市場推會覆蓋整份清單，先確認

async function push(name, symbols) {
  const ctl = new AbortController();
  const tid = setTimeout(() => ctl.abort(), 2500);
  try {
    const r = await fetch(HELPER, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, symbols }),
      signal: ctl.signal,
    });
    const j = await r.json();
    return j.ok ? { ok: true } : { ok: false, err: j.err || "?" };
  } catch {
    return { ok: false, helperDown: true };
  } finally {
    clearTimeout(tid);
  }
}

function fallback(name, symbols) {
  const txt = symbols.join(",");
  if (navigator.clipboard) navigator.clipboard.writeText(txt).catch(() => {});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([txt], { type: "text/plain" }));
  a.download = `tv_${name}.txt`;
  a.click();
  URL.revokeObjectURL(a.href);
}

export default function TvButton({ name, rows }) {
  const [msg, setMsg] = useState(null);
  const n = rows.length;

  const onClick = async () => {
    if (!n || msg === "…") return;
    if (n > CONFIRM_OVER && !confirm(`要把 ${n} 檔推到 TV「${name}」嗎？(整份覆蓋)`)) return;
    setMsg("…");
    const mk = await getMarkets().catch(() => ({}));
    const symbols = rows.map((r) => `${mk[r.code] || "TWSE"}:${r.code}`);
    const res = await push(name, symbols);
    if (res.ok) setMsg(`✓ ${n}`);
    else {
      fallback(name, symbols);
      setMsg(res.helperDown ? "helper 未開，已複製+下載" : `失敗(${res.err})，已複製+下載`);
    }
    setTimeout(() => setMsg(null), 4000);
  };

  return (
    <button className="tvbtn" onClick={onClick} disabled={!n} title={`推 TV 清單「${name}」`}>
      {msg || `⤴ TV (${n})`}
    </button>
  );
}
