import { useEffect, useMemo, useState } from "react";
import { useParams, useLocation, useNavigate, Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ResponsiveContainer, ComposedChart, Bar, Line, LineChart,
  XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, Legend,
} from "recharts";
import { getCompany, getValuation, getPriceReturns, getLatest, cleanVal } from "../lib/data.js";
import { fmtPct, fmtNum, fmtMoneyK, signClass, qKey, fmtYoy, yoyClass, fmtCore, CORE_LOW } from "../lib/format.js";

const C = { amber: "#e3a84a", sky: "#6db1d9", mauve: "#c98bb9", grid: "rgba(236,228,212,0.08)", dim: "#998f7e" };
const axis = { stroke: "rgba(236,228,212,0.25)", fontSize: 11, fontFamily: "IBM Plex Mono", fill: "#998f7e" };
const tip = {
  contentStyle: { background: "#221d16", border: "1px solid rgba(236,228,212,0.22)", borderRadius: 3, fontFamily: "IBM Plex Mono", fontSize: 12 },
  labelStyle: { color: "#e3a84a" },
};
const moneyTick = (v) => (Math.abs(v) >= 1e8 ? (v / 1e8).toFixed(0) + "億" : Math.round(v / 1e4) + "萬");

function Stat({ k, v, cls, sub }) {
  return (
    <div className="stat">
      <div className="k">{k}</div>
      <div className={`v ${cls || ""}`}>{v}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

// 同業比較欄位(子類股內)
const PEER_COLS = [
  { key: "mg_score", t: "動能分", f: (v) => fmtNum(v, 1) },
  { key: "pe", t: "本益比", f: (v) => fmtNum(v, 1) },
  { key: "roe_ttm", t: "ROE(TTM)", f: (v) => fmtPct(v) },
  { key: "gross_margin", t: "毛利率", f: (v) => fmtPct(v) },
  { key: "operating_margin", t: "營益率", f: (v) => fmtPct(v) },
  { key: "revenue_yoy", t: "營收YoY", f: (v) => fmtPct(v), color: true },
  { key: "eps_yoy", t: "EPS YoY", yoy: true },
  { key: "core_ratio", t: "本業比", f: fmtCore },
];
const PEER_MAX = 30;

// 子類股內排名：同業中位數 + 依動能分排序的同業表(超過上限時保證本檔在列)
function Peers({ code, sector }) {
  const nav = useNavigate();
  const loc = useLocation();
  const [rows, setRows] = useState(null);
  useEffect(() => {
    Promise.all([getLatest(), getValuation()])
      .then(([d, val]) =>
        setRows(
          Object.entries(d)
            .filter(([, v]) => v.sector === sector)
            .map(([c, v]) => ({ code: c, ...v, ...cleanVal(val[c], v.roe_ttm) }))
            .sort((a, b) => (b.mg_score ?? -1) - (a.mg_score ?? -1))
        )
      )
      .catch(() => setRows([]));
  }, [sector]);

  const med = useMemo(() => {
    if (!rows) return {};
    const m = {};
    for (const c of PEER_COLS) {
      const xs = rows.map((r) => r[c.key]).filter((v) => typeof v === "number").sort((a, b) => a - b);
      m[c.key] = xs.length ? xs[Math.floor((xs.length - 1) / 2)] : null;
    }
    return m;
  }, [rows]);

  if (!rows || rows.length < 2) return null;
  const rank = rows.findIndex((r) => r.code === code) + 1;
  const shown = rows.slice(0, PEER_MAX);
  if (rank > PEER_MAX) shown.push(rows[rank - 1]);

  return (
    <div className="chartcard" style={{ padding: "18px 0 0" }}>
      <h3 style={{ padding: "0 18px" }}>同業比較 · {sector}</h3>
      <p className="note" style={{ padding: "0 18px" }}>
        共 {rows.length} 檔，依動能分排序{rank > 0 && <>，本檔第 <b>{rank}</b> 名</>}；最上列為同業中位數
      </p>
      <div className="tablewrap" style={{ border: "none" }}>
        <table className="data">
          <thead>
            <tr>
              <th className="l">代號</th>
              <th className="l">名稱</th>
              {PEER_COLS.map((c) => <th key={c.key}>{c.t}</th>)}
            </tr>
          </thead>
          <tbody>
            <tr style={{ cursor: "default", color: "var(--ink-dim)" }}>
              <td className="l" colSpan={2}>中位數</td>
              {PEER_COLS.map((c) => (
                <td key={c.key} className="num">{c.yoy ? fmtPct(med[c.key]) : c.f(med[c.key])}</td>
              ))}
            </tr>
            {shown.map((r) => (
              <tr
                key={r.code}
                style={r.code === code ? { background: "rgba(227,168,74,0.12)", cursor: "default" } : undefined}
                onClick={() => r.code !== code && nav(`/c/${r.code}`, { state: loc.state })}
              >
                <td className="l"><span className="code">{r.code}</span></td>
                <td className="l"><span className="cname">{r.name}</span></td>
                {PEER_COLS.map((c) =>
                  c.yoy ? (
                    <td key={c.key} className={`num ${yoyClass(r, c.key)}`}>{fmtYoy(r, c.key)}</td>
                  ) : (
                    <td
                      key={c.key}
                      className={`num ${c.color ? signClass(r[c.key]) : ""} ${c.key === "core_ratio" && r.core_ratio < CORE_LOW ? "down" : ""}`}
                    >
                      {c.f(r[c.key])}
                    </td>
                  )
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Company() {
  const { code } = useParams();
  // 來源列表頁(含篩選 query)由跳轉時帶進 location.state；直接開連結則退回篩選排行
  const { from, label } = useLocation().state || {};
  const [d, setD] = useState(null);
  const [val, setVal] = useState(null);
  const [ret1y, setRet1y] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    window.scrollTo(0, 0); // 從列表中段點進來時不該停在半空
    setD(null);
    setErr(null);
    getCompany(code).then(setD).catch((e) => setErr(String(e)));
    getValuation().then((v) => setVal(v[code] || null)).catch(() => {});
    getPriceReturns().then((r) => setRet1y(r[code] ?? null)).catch(() => {});
  }, [code]);

  if (err) return <div className="page errbox">查無此公司資料（{code}）</div>;
  if (!d) return <div className="page loading">載入中…</div>;

  const q = Object.entries(d.quarterly || {})
    .map(([p, v]) => ({ p, ...v }))
    .sort((a, b) => qKey(a.p) - qKey(b.p));
  const m = Object.entries(d.monthly || {})
    .map(([p, v]) => ({ p, ...v }))
    .sort((a, b) => a.p.localeCompare(b.p));
  const qN = q.slice(-16);
  const mN = m.slice(-24).map((r) => ({ ...r, revYi: r.revenue }));
  const last = q.at(-1) || {};
  const v = val && cleanVal(val, last.roe_ttm);

  return (
    <motion.div className="page" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.35 }}>
      <Link to={from || "/"} className="backlink">← 返回{label || "篩選排行"}</Link>
      <div className="cohead" style={{ marginTop: 14 }}>
        <div>
          <div className="bigcode">{d.code}</div>
          <div className="big">{d.name}</div>
        </div>
        {d.sector_parent && <span className="chip" style={{ marginBottom: 6 }}>{d.sector_parent}</span>}
        {d.sector && (
          <Link to={`/?sector=${encodeURIComponent(d.sector)}`} className="chip" style={{ marginBottom: 6, color: "var(--amber)", borderColor: "var(--amber-deep)" }}>
            {d.sector}
          </Link>
        )}
        {d.industry && <span className="chip" style={{ marginBottom: 6 }}>{d.industry}</span>}
        <span className="chip" style={{ marginBottom: 6 }}>最新 {last.p || "—"}</span>
      </div>

      <div className="statgrid">
        <Stat k="ROE (TTM)" v={fmtPct(last.roe_ttm)} cls="num" />
        <Stat k="毛利率" v={fmtPct(last.gross_margin)} cls="num" />
        <Stat k="淨利率" v={fmtPct(last.net_margin)} cls="num" />
        <Stat k="負債比" v={fmtPct(last.debt_ratio)} cls="num" />
        <Stat k="EPS (TTM)" v={fmtNum(last.eps_ttm)} cls="num" sub={last.eps_basis_adj ? "舊季已依配股/面額變更換算" : ""} />
        <Stat k="營收YoY" v={fmtPct(last.revenue_yoy)} cls={`num ${signClass(last.revenue_yoy)}`} sub={`單季 ${last.p || ""}`} />
        <Stat k="本益比" v={fmtNum(v?.pe, 1)} cls="num" sub={v?.date ? `收盤 ${v.date}` : ""} />
        <Stat k="股價淨值比" v={fmtNum(v?.pb, 2)} cls="num" sub={val?.pb != null && v.pb == null ? "官方值疑誤，未顯示" : ""} />
        <Stat k="殖利率" v={fmtPct(v?.yield)} cls="num" sub={val?.yield != null && v.yield == null ? "官方值疑誤，未顯示" : ""} />
        <Stat k="近一年報酬" v={fmtPct(ret1y)} cls={`num ${signClass(ret1y)}`} />
      </div>

      <div className="chartcard" style={{ padding: "18px 0 0" }}>
        <h3 style={{ padding: "0 18px" }}>近 3 期財報</h3>
        <p className="note" style={{ padding: "0 18px" }}>單季數據；成長率為 YoY，ROE 為單季</p>
        <div className="tablewrap" style={{ border: "none" }}>
          <table className="data">
            <thead>
              <tr>
                <th className="l">期別</th>
                <th>EPS</th>
                <th>營收成長率</th>
                <th>營業利益成長率</th>
                <th>營業利益率</th>
                <th>稅後淨利率</th>
                <th>本業比</th>
                <th>單季ROE</th>
              </tr>
            </thead>
            <tbody>
              {q.slice(-3).reverse().map((r) => (
                <tr key={r.p} style={{ cursor: "default" }}>
                  <td className="l"><span className="code">{r.p}</span></td>
                  <td className="num">{fmtNum(r.eps)}</td>
                  <td className={`num ${signClass(r.revenue_yoy)}`}>{fmtPct(r.revenue_yoy)}</td>
                  <td className={`num ${yoyClass(r, "operating_income_yoy")}`}>{fmtYoy(r, "operating_income_yoy")}</td>
                  <td className="num">{fmtPct(r.operating_margin)}</td>
                  <td className="num">{fmtPct(r.net_margin)}</td>
                  <td className={`num ${r.core_ratio < CORE_LOW ? "down" : ""}`}>{fmtCore(r.core_ratio)}</td>
                  <td className="num">{fmtPct(r.roe_q)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {d.sector && <Peers code={d.code} sector={d.sector} />}

      <div className="grid2">
        <div className="chartcard">
          <h3>單季營收與年增</h3>
          <p className="note">柱：營收(仟元) · 線：YoY %</p>
          <ResponsiveContainer width="100%" height={240}>
            <ComposedChart data={qN} margin={{ left: 6, right: 6, top: 6 }}>
              <CartesianGrid stroke={C.grid} vertical={false} />
              <XAxis dataKey="p" {...axis} tickLine={false} />
              <YAxis yAxisId="l" {...axis} tickLine={false} tickFormatter={(v) => moneyTick(v * 1000)} width={48} />
              <YAxis yAxisId="r" orientation="right" {...axis} tickLine={false} tickFormatter={(v) => v + "%"} width={42} />
              <Tooltip {...tip} formatter={(v, n) => (n === "營收" ? fmtMoneyK(v) : fmtPct(v))} />
              <ReferenceLine yAxisId="r" y={0} stroke={C.grid} />
              <Bar yAxisId="l" dataKey="revenue" name="營收" fill={C.amber} radius={[2, 2, 0, 0]} />
              <Line yAxisId="r" dataKey="revenue_yoy" name="YoY" stroke={C.sky} strokeWidth={2} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div className="chartcard">
          <h3>獲利率趨勢</h3>
          <p className="note">毛利率 / 營益率 / 淨利率 %</p>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={qN} margin={{ left: 6, right: 6, top: 6 }}>
              <CartesianGrid stroke={C.grid} vertical={false} />
              <XAxis dataKey="p" {...axis} tickLine={false} />
              <YAxis {...axis} tickLine={false} tickFormatter={(v) => v + "%"} width={42} />
              <Tooltip {...tip} formatter={(v) => fmtPct(v)} />
              <Line dataKey="gross_margin" name="毛利率" stroke={C.amber} strokeWidth={2} dot={false} />
              <Line dataKey="operating_margin" name="營益率" stroke={C.sky} strokeWidth={2} dot={false} />
              <Line dataKey="net_margin" name="淨利率" stroke={C.mauve} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="chartcard">
          <h3>每股盈餘</h3>
          <p className="note">柱：單季 EPS · 線：TTM EPS（元）</p>
          <ResponsiveContainer width="100%" height={240}>
            <ComposedChart data={qN} margin={{ left: 6, right: 6, top: 6 }}>
              <CartesianGrid stroke={C.grid} vertical={false} />
              <XAxis dataKey="p" {...axis} tickLine={false} />
              <YAxis {...axis} tickLine={false} width={42} />
              <Tooltip {...tip} formatter={(v) => fmtNum(v)} />
              <ReferenceLine y={0} stroke={C.grid} />
              <Bar dataKey="eps" name="單季EPS" fill={C.amber} radius={[2, 2, 0, 0]} />
              <Line dataKey="eps_ttm" name="TTM EPS" stroke={C.sky} strokeWidth={2} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div className="chartcard">
          <h3>月營收與年增</h3>
          <p className="note">柱：月營收(仟元) · 線：YoY 單月(細) / 3m / 12m %</p>
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={mN} margin={{ left: 6, right: 6, top: 6 }}>
              <CartesianGrid stroke={C.grid} vertical={false} />
              <XAxis dataKey="p" {...axis} tickLine={false} interval={3} />
              <YAxis yAxisId="l" {...axis} tickLine={false} tickFormatter={(v) => moneyTick(v * 1000)} width={48} />
              <YAxis yAxisId="r" orientation="right" {...axis} tickLine={false} tickFormatter={(v) => v + "%"} width={42} />
              <Tooltip {...tip} formatter={(v, n) => (n === "月營收" ? fmtMoneyK(v) : fmtPct(v))} />
              <Legend wrapperStyle={{ fontFamily: "IBM Plex Mono", fontSize: 11 }} />
              <ReferenceLine yAxisId="r" y={0} stroke={C.grid} />
              <Bar yAxisId="l" dataKey="revenue" name="月營收" fill={C.amber} radius={[2, 2, 0, 0]} />
              <Line yAxisId="r" dataKey="yoy" name="YoY" stroke={C.dim} strokeWidth={1} dot={false} />
              <Line yAxisId="r" dataKey="yoy_3m" name="YoY 3m" stroke={C.sky} strokeWidth={2} dot={false} />
              <Line yAxisId="r" dataKey="yoy_12m" name="YoY 12m" stroke={C.mauve} strokeWidth={2} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
    </motion.div>
  );
}
