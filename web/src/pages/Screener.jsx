import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { getLatest } from "../lib/data.js";
import { fmtPct, fmtNum, fmtMoneyK, signClass } from "../lib/format.js";

// 欄位定義：key, 標題, 取值, 格式, 是否套漲跌色(紅漲綠跌)
const COLS = [
  { key: "roe_ttm", t: "ROE(TTM)", f: (v) => fmtPct(v) },
  { key: "gross_margin", t: "毛利率", f: (v) => fmtPct(v) },
  { key: "net_margin", t: "淨利率", f: (v) => fmtPct(v) },
  { key: "debt_ratio", t: "負債比", f: (v) => fmtPct(v) },
  { key: "current_ratio", t: "流動比", f: (v) => fmtPct(v, 0) },
  { key: "revenue_yoy", t: "營收YoY", f: (v) => fmtPct(v), color: true },
  { key: "eps_ttm", t: "EPS(TTM)", f: (v) => fmtNum(v) },
  { key: "eps_yoy", t: "EPS YoY", f: (v) => fmtPct(v), color: true },
  { key: "revenue_ttm", t: "營收(TTM)", f: (v) => fmtMoneyK(v) },
];

export default function Screener() {
  const nav = useNavigate();
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState(null);
  const [q, setQ] = useState("");
  const [ind, setInd] = useState("");
  const [minRoe, setMinRoe] = useState("");
  const [maxDebt, setMaxDebt] = useState("");
  const [minYoy, setMinYoy] = useState("");
  const [sort, setSort] = useState({ k: "roe_ttm", dir: -1 });

  useEffect(() => {
    getLatest()
      .then((d) =>
        setRows(Object.entries(d).map(([code, v]) => ({ code, ...v })))
      )
      .catch((e) => setErr(String(e)));
  }, []);

  const industries = useMemo(() => {
    if (!rows) return [];
    return [...new Set(rows.map((r) => r.industry).filter(Boolean))].sort();
  }, [rows]);

  const view = useMemo(() => {
    if (!rows) return [];
    const qq = q.trim();
    const mr = minRoe === "" ? null : +minRoe;
    const md = maxDebt === "" ? null : +maxDebt;
    const my = minYoy === "" ? null : +minYoy;
    let out = rows.filter((r) => {
      if (ind && r.industry !== ind) return false;
      if (qq && !r.code.includes(qq) && !(r.name || "").includes(qq)) return false;
      if (mr != null && !(r.roe_ttm >= mr)) return false;
      if (md != null && !(r.debt_ratio <= md)) return false;
      if (my != null && !(r.revenue_yoy >= my)) return false;
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
  }, [rows, q, ind, minRoe, maxDebt, minYoy, sort]);

  const shown = view.slice(0, 250);

  const th = (k, label, cls) => (
    <th
      key={k}
      className={cls}
      onClick={() => setSort((s) => ({ k, dir: s.k === k ? -s.dir : -1 }))}
    >
      {label}
      {sort.k === k && <span className="arrow">{sort.dir < 0 ? "▾" : "▴"}</span>}
    </th>
  );

  if (err) return <div className="page errbox">載入失敗：{err}</div>;

  return (
    <div className="page">
      <div className="eyebrow">基本面橫斷面 · 全上市櫃</div>
      <h1>篩選與排行</h1>
      <p className="lede">
        以最新一季財報計算的獲利能力、財務結構與成長性。台股慣例
        <span className="up"> 紅為正成長</span>、<span className="down">綠為衰退</span>。點任一列看個股全貌。
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
          <label>ROE(TTM) ≥</label>
          <input type="number" value={minRoe} onChange={(e) => setMinRoe(e.target.value)} placeholder="15" />
        </div>
        <div className="field range">
          <label>負債比 ≤</label>
          <input type="number" value={maxDebt} onChange={(e) => setMaxDebt(e.target.value)} placeholder="40" />
        </div>
        <div className="field range">
          <label>營收YoY ≥</label>
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
                {COLS.map((c) => th(c.key, c.t))}
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
                  {COLS.map((c) => (
                    <td key={c.key} className={`num ${c.color ? signClass(r[c.key]) : ""}`}>
                      {c.f(r[c.key])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </motion.div>
      )}
    </div>
  );
}
