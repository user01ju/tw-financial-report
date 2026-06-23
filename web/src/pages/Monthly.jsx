import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { getLatestMonthly } from "../lib/data.js";
import { fmtPct, fmtMoneyK, signClass } from "../lib/format.js";

// 數值欄：YoY / 短期3m / 長期12m / 累計YTD / MoM（皆套紅漲綠跌）
const COLS = [
  { key: "yoy", t: "YoY" },
  { key: "mrev_yoy_3m", t: "短期3m" },
  { key: "mrev_yoy_12m", t: "長期12m" },
  { key: "mrev_yoy_ytd", t: "累計YTD" },
  { key: "mom", t: "MoM" },
];

export default function Monthly() {
  const nav = useNavigate();
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState(null);
  const [q, setQ] = useState("");
  const [ind, setInd] = useState("");
  const [minYoy, setMinYoy] = useState("");
  const [turnPos, setTurnPos] = useState(false);
  const [highOnly, setHighOnly] = useState(false);
  const [sort, setSort] = useState({ k: "yoy", dir: -1 });

  useEffect(() => {
    getLatestMonthly()
      .then((d) => setRows(Object.entries(d).map(([code, v]) => ({ code, ...v }))))
      .catch((e) => setErr(String(e)));
  }, []);

  const sectorsByParent = useMemo(() => {
    if (!rows) return {};
    const m = {};
    rows.forEach((r) => {
      if (r.sector) (m[r.sector_parent || "其他"] ||= new Set()).add(r.sector);
    });
    return Object.fromEntries(Object.entries(m).map(([p, s]) => [p, [...s].sort()]));
  }, [rows]);
  const latestMonth = useMemo(
    () => (rows ? rows.map((r) => r.month).sort().at(-1) : ""),
    [rows]
  );

  const view = useMemo(() => {
    if (!rows) return [];
    const qq = q.trim();
    const my = minYoy === "" ? null : +minYoy;
    let out = rows.filter((r) => {
      if (ind && r.sector !== ind) return false;
      if (qq && !r.code.includes(qq) && !(r.name || "").includes(qq)) return false;
      if (my != null && !(r.yoy >= my)) return false;
      if (turnPos && r.mrev_turn !== 1) return false;
      if (highOnly && !r.mrev_high_all) return false;
      return true;
    });
    const { k, dir } = sort;
    out.sort((a, b) => {
      const x = a[k], y = b[k];
      if (x == null) return 1;
      if (y == null) return -1;
      if (typeof x === "string") return x.localeCompare(y) * dir;
      return (x - y) * dir;
    });
    return out;
  }, [rows, q, ind, minYoy, turnPos, highOnly, sort]);

  const shown = view.slice(0, 250);
  const th = (k, label, cls) => (
    <th key={k} className={cls} onClick={() => setSort((s) => ({ k, dir: s.k === k ? -s.dir : -1 }))}>
      {label}
      {sort.k === k && <span className="arrow">{sort.dir < 0 ? "▾" : "▴"}</span>}
    </th>
  );

  if (err) return <div className="page errbox">載入失敗：{err}</div>;

  return (
    <div className="page">
      <div className="eyebrow">月營收橫斷面 · {latestMonth || "—"}</div>
      <h1>月營收熱力</h1>
      <p className="lede">
        最新月營收與年增。<b>短期3m</b>／<b>長期12m</b> 為近 3／12 月 YoY 均值（看動能強弱與加速），
        <b>累計YTD</b> 平滑單月雜訊（春節失真用這個）。<span className="up">紅成長</span>、<span className="down">綠衰退</span>。
      </p>

      <div className="controls">
        <div className="field">
          <label>搜尋 代號 / 名稱</label>
          <input type="text" value={q} onChange={(e) => setQ(e.target.value)} placeholder="2330 / 台積電" />
        </div>
        <div className="field">
          <label>子類股 (CMoney)</label>
          <select value={ind} onChange={(e) => setInd(e.target.value)}>
            <option value="">全部</option>
            {Object.entries(sectorsByParent).map(([p, arr]) => (
              <optgroup key={p} label={p}>
                {arr.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>
        <div className="field range">
          <label>YoY ≥</label>
          <input type="number" value={minYoy} onChange={(e) => setMinYoy(e.target.value)} placeholder="0" />
        </div>
        <label className="toggle">
          <input type="checkbox" checked={turnPos} onChange={(e) => setTurnPos(e.target.checked)} />
          YoY 剛轉正
        </label>
        <label className="toggle">
          <input type="checkbox" checked={highOnly} onChange={(e) => setHighOnly(e.target.checked)} />
          營收創新高
        </label>
        <div className="count">
          符合 <b>{view.length}</b> 檔{view.length > 250 && <> · 顯示前 250</>}
        </div>
      </div>

      {!rows ? (
        <div className="loading">載入中…</div>
      ) : (
        <motion.div
          className="tablewrap"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: "easeOut" }}
        >
          <table className="data">
            <thead>
              <tr>
                {th("code", "代號", "l")}
                {th("name", "名稱", "l")}
                {th("month", "月份")}
                {th("revenue", "當月營收")}
                {COLS.map((c) => th(c.key, c.t))}
                {th("mrev_streak", "連續月")}
                <th className="l">訊號</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.code} onClick={() => nav(`/c/${r.code}`)}>
                  <td className="l"><span className="code">{r.code}</span></td>
                  <td className="l">
                    <span className="cname">{r.name}</span>{" "}
                    <span className="cind">{r.sector || r.industry}</span>
                  </td>
                  <td className="num" style={{ color: "var(--ink-dim)" }}>{r.month}</td>
                  <td className="num">{fmtMoneyK(r.revenue)}</td>
                  {COLS.map((c) => (
                    <td key={c.key} className={`num ${signClass(r[c.key])}`}>{fmtPct(r[c.key])}</td>
                  ))}
                  <td className="num">{r.mrev_streak ?? "—"}</td>
                  <td className="l">
                    {r.mrev_turn === 1 && <span className="sig up">轉正↗</span>}
                    {r.mrev_turn === -1 && <span className="sig down">轉負↘</span>}
                    {r.mrev_high_all && <span className="sig hi">★創高</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </motion.div>
      )}
    </div>
  );
}
