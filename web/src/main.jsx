import React from "react";
import ReactDOM from "react-dom/client";
import { HashRouter, Routes, Route, NavLink } from "react-router-dom";
import "./index.css";
import Screener from "./pages/Screener.jsx";
import Monthly from "./pages/Monthly.jsx";
import Company from "./pages/Company.jsx";

function Masthead() {
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
        <NavLink to="/monthly">月營收</NavLink>
      </nav>
    </header>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <HashRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Masthead />
      <Routes>
        <Route path="/" element={<Screener />} />
        <Route path="/monthly" element={<Monthly />} />
        <Route path="/c/:code" element={<Company />} />
      </Routes>
    </HashRouter>
  </React.StrictMode>
);
