import { useState } from "react";
import "./App.css";
import Dashboard from "./components/Dashboard";
import LogsView from "./components/LogsView";

export default function App() {
  const [page, setPage] = useState("dashboard");

  return (
    <div className="app">
      <header className="header">
        <h1>Playout</h1>
        <span>merchant payout dashboard</span>
        <nav className="header-nav">
          <button
            className={`nav-btn ${page === "dashboard" ? "active" : ""}`}
            onClick={() => setPage("dashboard")}
          >
            Dashboard
          </button>
          <button
            className={`nav-btn ${page === "logs" ? "active" : ""}`}
            onClick={() => setPage("logs")}
          >
            Logs
          </button>
        </nav>
      </header>

      {page === "logs" ? <LogsView /> : <Dashboard />}
    </div>
  );
}
