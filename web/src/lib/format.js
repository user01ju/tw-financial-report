// 數值格式化。財報金額單位為「仟元」。

export const fmtPct = (v, d = 2) =>
  v == null || Number.isNaN(v) ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(d)}%`;

export const fmtNum = (v, d = 2) =>
  v == null || Number.isNaN(v) ? "—" : v.toFixed(d);

export const signClass = (v) =>
  v == null || Number.isNaN(v) ? "" : v > 0 ? "up" : v < 0 ? "down" : "";

// 仟元 → 億/萬（顯示用）
export function fmtMoneyK(vK) {
  if (vK == null || Number.isNaN(vK)) return "—";
  const e = vK * 1000; // 還原成元
  const a = Math.abs(e);
  if (a >= 1e12) return (e / 1e12).toFixed(2) + " 兆";
  if (a >= 1e8) return (e / 1e8).toFixed(1) + " 億";
  if (a >= 1e4) return Math.round(e / 1e4) + " 萬";
  return Math.round(e).toLocaleString();
}

// 季 period 排序鍵 "2026Q1" -> 2026.1
export const qKey = (p) => parseInt(p.slice(0, 4)) * 10 + parseInt(p.slice(-1));
