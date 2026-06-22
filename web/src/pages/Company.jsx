import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ResponsiveContainer, ComposedChart, Bar, Line, LineChart,
  XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine,
} from "recharts";
import { getCompany, getValuation } from "../lib/data.js";
import { fmtPct, fmtNum, fmtMoneyK, signClass, qKey } from "../lib/format.js";

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

export default function Company() {
  const { code } = useParams();
  const [d, setD] = useState(null);
  const [val, setVal] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    setD(null);
    setErr(null);
    getCompany(code).then(setD).catch((e) => setErr(String(e)));
    getValuation().then((v) => setVal(v[code] || null)).catch(() => {});
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

  return (
    <motion.div className="page" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.35 }}>
      <Link to="/" className="backlink">← 返回篩選排行</Link>
      <div className="cohead" style={{ marginTop: 14 }}>
        <div>
          <div className="bigcode">{d.code}</div>
          <div className="big">{d.name}</div>
        </div>
        {d.industry && <span className="chip" style={{ marginBottom: 6 }}>{d.industry}</span>}
        <span className="chip" style={{ marginBottom: 6 }}>最新 {last.p || "—"}</span>
      </div>

      <div className="statgrid">
        <Stat k="ROE (TTM)" v={fmtPct(last.roe_ttm)} cls="num" />
        <Stat k="毛利率" v={fmtPct(last.gross_margin)} cls="num" />
        <Stat k="淨利率" v={fmtPct(last.net_margin)} cls="num" />
        <Stat k="負債比" v={fmtPct(last.debt_ratio)} cls="num" />
        <Stat k="EPS (TTM)" v={fmtNum(last.eps_ttm)} cls="num" />
        <Stat k="營收YoY" v={fmtPct(last.revenue_yoy)} cls={`num ${signClass(last.revenue_yoy)}`} sub={`單季 ${last.p || ""}`} />
        <Stat k="本益比" v={fmtNum(val?.pe, 1)} cls="num" sub={val?.date ? `收盤 ${val.date}` : ""} />
        <Stat k="股價淨值比" v={fmtNum(val?.pb, 2)} cls="num" />
        <Stat k="殖利率" v={fmtPct(val?.yield)} cls="num" />
      </div>

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
          <p className="note">柱：月營收(仟元) · 線：YoY %</p>
          <ResponsiveContainer width="100%" height={240}>
            <ComposedChart data={mN} margin={{ left: 6, right: 6, top: 6 }}>
              <CartesianGrid stroke={C.grid} vertical={false} />
              <XAxis dataKey="p" {...axis} tickLine={false} interval={3} />
              <YAxis yAxisId="l" {...axis} tickLine={false} tickFormatter={(v) => moneyTick(v * 1000)} width={48} />
              <YAxis yAxisId="r" orientation="right" {...axis} tickLine={false} tickFormatter={(v) => v + "%"} width={42} />
              <Tooltip {...tip} formatter={(v, n) => (n === "月營收" ? fmtMoneyK(v) : fmtPct(v))} />
              <ReferenceLine yAxisId="r" y={0} stroke={C.grid} />
              <Bar yAxisId="l" dataKey="revenue" name="月營收" fill={C.amber} radius={[2, 2, 0, 0]} />
              <Line yAxisId="r" dataKey="yoy" name="YoY" stroke={C.sky} strokeWidth={2} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
    </motion.div>
  );
}
