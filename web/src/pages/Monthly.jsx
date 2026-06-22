import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { getLatestMonthly } from "../lib/data.js";
import { fmtPct, fmtMoneyK, signClass } from "../lib/format.js";

export default function Monthly() {
  const nav = useNavigate();
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState(null);
  const [q, setQ] = useState("");
  const [ind, setInd] = useState("");
  const [minYoy, setMinYoy] = useState("");
  const [sort, setSort] = useState({ k: "yoy", dir: -1 });

  useEffect(() => {
    getLatestMonthly()
      .then((d) => setRows(Object.entries(d).map(([code, v]) => ({ code, ...v }))))
      .catch((e) => setErr(String(e)));
  }, []);

  const industries = useMemo(
    () => (rows ? [...new Set(rows.map((r) => r.industry).filter(Boolean))].sort() : []),
    [rows]
  );
  const latestMonth = useMemo(
    () => (rows ? rows.map((r) => r.month).sort().at(-1) : ""),
    [rows]
  );

  const view = useMemo(() => {
    if (!rows) return [];
    const qq = q.trim();
    const my = minYoy === "" ? null : +minYoy;
    let out = rows.filter((r) => {
      if (ind && r.industry !== ind) return false;
      if (qq && !r.code.includes(qq) && !(r.name || "").includes(qq)) return false;
      if (my != null && !(r.yoy >= my)) return false;
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
  }, [rows, q, ind, minYoy, sort]);

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
        各公司最新月營收與年增（YoY）、月增（MoM）。預設按 YoY 由高到低，
        <span className="up"> 紅為成長</span>、<span className="down">綠為衰退</span>。
      </p>

      <div className="controls">
        <div className="field">
          <label>搜尋 代號 / 名稱</label>
          <input type="text" value={q} onChange={(e) => setQ(e.target.value)} placeholder="2330 / 台積電" />
        </div>
        <div className="field">
          <label>產業別</label>
          <select value={ind} onChange={(e) => setInd(e.target.value)}>
            <option value="">全部</option>
            {industries.map((i) => (
              <option key={i} value={i}>{i}</option>
            ))}
          </select>
        </div>
        <div className="field range">
          <label>YoY ≥</label>
          <input type="number" value={minYoy} onChange={(e) => setMinYoy(e.target.value)} placeholder="0" />
        </div>
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
                {th("yoy", "YoY")}
                {th("mom", "MoM")}
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.code} onClick={() => nav(`/c/${r.code}`)}>
                  <td className="l"><span className="code">{r.code}</span></td>
                  <td className="l">
                    <span className="cname">{r.name}</span>{" "}
                    <span className="cind">{r.industry}</span>
                  </td>
                  <td className="num" style={{ color: "var(--ink-dim)" }}>{r.month}</td>
                  <td className="num">{fmtMoneyK(r.revenue)}</td>
                  <td className={`num ${signClass(r.yoy)}`}>{fmtPct(r.yoy)}</td>
                  <td className={`num ${signClass(r.mom)}`}>{fmtPct(r.mom)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </motion.div>
      )}
    </div>
  );
}
