import React, { Suspense, lazy, useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { HashRouter, Routes, Route, NavLink } from "react-router-dom";
import "./index.css";
import { getMeta } from "./lib/data.js";
import Screener from "./pages/Screener.jsx";
import Monthly from "./pages/Monthly.jsx";
import Momentum from "./pages/Momentum.jsx";
// 個股頁含 recharts(重)，lazy 拆成獨立 chunk，首頁不載入
const Company = lazy(() => import("./pages/Company.jsx"));

function Masthead() {
  const [meta, setMeta] = useState(null);
  useEffect(() => {
    getMeta().then(setMeta).catch(() => {});
  }, []);
  const updated = meta?.updated_at
    ? new Date(meta.updated_at).toLocaleString("zh-TW", {
        timeZone: "Asia/Taipei",
        year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", hour12: false,
      })
    : null;
  return (
    <header className="masthead">
      <NavLink to="/" className="wordmark">
        臺股<em>財報</em>
      </NavLink>
      <span className="tag">Fundamentals Terminal</span>
      <nav>
        <NavLink to="/" end>
          篩選排行
        </NavLink>
        <NavLink to="/momentum">動能成長</NavLink>
        <NavLink to="/monthly">月營收</NavLink>
      </nav>
      {updated && (
        <span className="updated" title={`季 ${meta.latest_quarter} · 月 ${meta.latest_month}`}>
          更新 {updated}
        </span>
      )}
    </header>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <HashRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Masthead />
      <Suspense fallback={<div className="page loading">載入中…</div>}>
        <Routes>
          <Route path="/" element={<Screener />} />
          <Route path="/momentum" element={<Momentum />} />
          <Route path="/monthly" element={<Monthly />} />
          <Route path="/c/:code" element={<Company />} />
        </Routes>
      </Suspense>
    </HashRouter>
  </React.StrictMode>
);
