import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { getLatest } from "../lib/data.js";
import { fmtPct, fmtNum, signClass } from "../lib/format.js";

// 動能成長頁欄位
const COLS = [
  { key: "revenue_yoy", t: "營收YoY", f: (v) => fmtPct(v), color: true },
  { key: "revenue_yoy_accel", t: "營收加速", f: (v) => fmtNum(v, 0), color: true },
  { key: "operating_income_yoy", t: "營益YoY", f: (v) => fmtPct(v), color: true },
  { key: "mrev_yoy_3m", t: "月營收動能", f: (v) => fmtPct(v), color: true },
  { key: "mrev_streak", t: "連續月", f: (v) => (v == null ? "—" : `${v}`) },
  { key: "price_return_1y", t: "1Y報酬", f: (v) => fmtPct(v), color: true },
  { key: "eps_yoy", t: "EPS YoY", f: (v) => fmtPct(v), color: true },
  { key: "roe_ttm", t: "ROE(TTM)", f: (v) => fmtPct(v) },
  { key: "operating_margin", t: "營益率", f: (v) => fmtPct(v) },
];

export default function Momentum() {
  const nav = useNavigate();
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState(null);
  const [q, setQ] = useState("");
  const [ind, setInd] = useState("");
  const [minRoe, setMinRoe] = useState("10");
  const [minOpm, setMinOpm] = useState("5");
  const [minScore, setMinScore] = useState("");
  const [sort, setSort] = useState({ k: "mg_score", dir: -1 });

  useEffect(() => {
    getLatest()
      .then((d) =>
        setRows(
          Object.entries(d)
            .filter(([, v]) => v.mg_score != null)
            .map(([code, v]) => ({ code, ...v }))
        )
      )
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

  const view = useMemo(() => {
    if (!rows) return [];
    const qq = q.trim();
    const mr = minRoe === "" ? null : +minRoe;
    const mo = minOpm === "" ? null : +minOpm;
    const ms = minScore === "" ? null : +minScore;
    let out = rows.filter((r) => {
      if (ind && r.sector !== ind) return false;
      if (qq && !r.code.includes(qq) && !(r.name || "").includes(qq)) return false;
      if (mr != null && !(r.roe_ttm >= mr)) return false;
      if (mo != null && !(r.operating_margin >= mo)) return false;
      if (ms != null && !(r.mg_score >= ms)) return false;
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
  }, [rows, q, ind, minRoe, minOpm, minScore, sort]);

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
      <div className="eyebrow">動能成長選股 · 全上市櫃</div>
      <h1>動能成長</h1>
      <p className="lede">
        綜合分數＝營收/營益/EPS 成長 + 成長加速度 + 月營收動能（各因子全市場百分位後加權，0–100）。
        預設套品質護欄。<span className="up">紅為正/加速</span>、<span className="down">綠為轉弱</span>。
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
          <label>動能成長分 ≥</label>
          <input type="number" value={minScore} onChange={(e) => setMinScore(e.target.value)} placeholder="80" />
        </div>
        <div className="field range">
          <label>ROE(TTM) ≥</label>
          <input type="number" value={minRoe} onChange={(e) => setMinRoe(e.target.value)} />
        </div>
        <div className="field range">
          <label>營益率 ≥</label>
          <input type="number" value={minOpm} onChange={(e) => setMinOpm(e.target.value)} />
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
                {th("mg_score", "動能成長分")}
                {COLS.map((c) => th(c.key, c.t))}
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
                  <td className="num" style={{ color: "var(--amber)", fontWeight: 600 }}>
                    {fmtNum(r.mg_score, 1)}
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
