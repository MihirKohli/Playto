import React, { useState, useEffect, useCallback } from "react";
import "./App.css";
import { getMerchants, getBalance, getLedger, getPayouts, createPayout, getLogs } from "./api";

const toRupees = (paise) =>
  "₹" + (paise / 100).toLocaleString("en-IN", { minimumFractionDigits: 2 });

const fmtDate = (d) =>
  new Date(d).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });

function Badge({ label, filled }) {
  return <span className={`badge ${filled ? "filled" : ""}`}>{label}</span>;
}

// ── Payout modal ─────────────────────────────────────────────────────────────
function PayoutModal({ merchant, onClose, onSuccess }) {
  const [amount, setAmount]           = useState("");
  const [bankAccountId, setBankAccountId] = useState(merchant.bank_accounts[0]?.id ?? "");
  const [error, setError]             = useState("");
  const [loading, setLoading]         = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    const paise = Math.round(parseFloat(amount) * 100);
    if (!paise || paise <= 0) { setError("Enter a valid amount"); return; }
    setLoading(true);
    try {
      await createPayout(merchant.id, bankAccountId, paise);
      onSuccess();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>New Payout</h3>
        {error && <div className="error-msg">{error}</div>}
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Amount (₹)</label>
            <input
              type="number" min="0.01" step="0.01"
              value={amount} onChange={(e) => setAmount(e.target.value)}
              placeholder="e.g. 1000" autoFocus
            />
          </div>
          <div className="form-group">
            <label>Bank Account</label>
            <select value={bankAccountId} onChange={(e) => setBankAccountId(e.target.value)}>
              {merchant.bank_accounts.map((ba) => (
                <option key={ba.id} value={ba.id}>
                  {ba.account_holder_name} — ••••{ba.account_number.slice(-4)} ({ba.ifsc_code})
                </option>
              ))}
            </select>
          </div>
          <div className="form-actions">
            <button type="button" className="btn" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn primary" disabled={loading}>
              {loading ? "Sending…" : "Send Payout"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Ledger table ─────────────────────────────────────────────────────────────
function LedgerTable({ entries }) {
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Type</th><th>Amount</th><th>Status</th><th>Description</th><th>Date</th>
        </tr>
      </thead>
      <tbody>
        {entries.length === 0 ? (
          <tr className="no-rows"><td colSpan={5}>no ledger entries</td></tr>
        ) : entries.map((e) => (
          <tr key={e.id}>
            <td><Badge label={e.entry_type} filled={e.entry_type === "CREDIT"} /></td>
            <td>{toRupees(e.amount_paise)}</td>
            <td><Badge label={e.status} filled={e.status === "SETTLED"} /></td>
            <td>{e.description}</td>
            <td>{fmtDate(e.created_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ── Payouts table ─────────────────────────────────────────────────────────────
function PayoutsTable({ payouts }) {
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Amount</th><th>Status</th><th>Attempts</th><th>Failure Reason</th><th>Created</th>
        </tr>
      </thead>
      <tbody>
        {payouts.length === 0 ? (
          <tr className="no-rows"><td colSpan={5}>no payouts yet</td></tr>
        ) : payouts.map((p) => (
          <tr key={p.id}>
            <td>{toRupees(p.amount_paise)}</td>
            <td><Badge label={p.status} filled={p.status === "COMPLETED"} /></td>
            <td>{p.attempt_count}</td>
            <td>{p.failure_reason || "—"}</td>
            <td>{fmtDate(p.created_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ── Logs view ─────────────────────────────────────────────────────────────────
const LEVELS = ['', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'];

function LogsView() {
  const [logs, setLogs]         = useState([]);
  const [total, setTotal]       = useState(0);
  const [loading, setLoading]   = useState(false);
  const [expanded, setExpanded] = useState(null);
  const [filters, setFilters]   = useState({ level: '', logger: '', limit: '100' });

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getLogs({
        level:  filters.level,
        logger: filters.logger,
        limit:  parseInt(filters.limit) || 100,
      });
      setLogs(data.results);
      setTotal(data.count);
    } catch {
      setLogs([]);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  const setFilter = (key, val) => setFilters((f) => ({ ...f, [key]: val }));

  return (
    <div className="logs-view">
      <div className="logs-toolbar">
        <div className="logs-filters">
          <select value={filters.level} onChange={(e) => setFilter('level', e.target.value)}>
            {LEVELS.map((l) => <option key={l} value={l}>{l || 'All levels'}</option>)}
          </select>
          <input
            type="text" placeholder="Filter by logger…"
            value={filters.logger} onChange={(e) => setFilter('logger', e.target.value)}
          />
          <select value={filters.limit} onChange={(e) => setFilter('limit', e.target.value)}>
            {['50', '100', '250', '500'].map((n) => (
              <option key={n} value={n}>Last {n}</option>
            ))}
          </select>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span className="log-count">{total} entries</span>
          <button className="btn" onClick={fetchLogs}>Refresh</button>
        </div>
      </div>

      {loading ? (
        <div className="loading">fetching logs…</div>
      ) : (
        <div className="logs-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: 160 }}>Time</th>
                <th style={{ width: 90 }}>Level</th>
                <th style={{ width: 110 }}>Logger</th>
                <th>Message</th>
                <th style={{ width: 180 }}>Location</th>
                <th style={{ width: 50 }}></th>
              </tr>
            </thead>
            <tbody>
              {logs.length === 0 ? (
                <tr className="no-rows"><td colSpan={6}>no logs found</td></tr>
              ) : logs.map((log) => (
                <React.Fragment key={log.id}>
                  <tr className={`log-row log-row--${log.level.toLowerCase()}`}>
                    <td className="log-time">{fmtDate(log.created_at)}</td>
                    <td>
                      <span className={`log-badge log-badge--${log.level.toLowerCase()}`}>
                        {log.level}
                      </span>
                    </td>
                    <td className="log-logger">{log.logger_name}</td>
                    <td className="log-message">{log.message}</td>
                    <td className="log-location">
                      {log.module}.{log.func_name}:{log.line_no}
                    </td>
                    <td>
                      {log.context && Object.keys(log.context).length > 0 && (
                        <button
                          className="btn-ctx"
                          onClick={() => setExpanded(expanded === log.id ? null : log.id)}
                        >
                          {expanded === log.id ? '▲' : '▼'}
                        </button>
                      )}
                    </td>
                  </tr>
                  {expanded === log.id && (
                    <tr className="log-ctx-row">
                      <td colSpan={6}>
                        <pre className="log-ctx-pre">
                          {JSON.stringify(log.context, null, 2)}
                        </pre>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── App ───────────────────────────────────────────────────────────────────────
export default function App() {
  const [page, setPage]               = useState("dashboard");
  const [merchants, setMerchants]     = useState([]);
  const [selected, setSelected]       = useState(null);
  const [balance, setBalance]         = useState(null);
  const [ledger, setLedger]           = useState([]);
  const [payouts, setPayouts]         = useState([]);
  const [tab, setTab]                 = useState("ledger");
  const [showModal, setShowModal]     = useState(false);
  const [loadingMerchants, setLoadingMerchants] = useState(true);
  const [loadingData, setLoadingData] = useState(false);

  useEffect(() => {
    getMerchants()
      .then(setMerchants)
      .finally(() => setLoadingMerchants(false));
  }, []);

  const loadMerchantData = useCallback(async (merchant) => {
    setLoadingData(true);
    setBalance(null); setLedger([]); setPayouts([]);
    try {
      const [bal, led, pay] = await Promise.all([
        getBalance(merchant.id),
        getLedger(merchant.id),
        getPayouts(merchant.id),
      ]);
      setBalance(bal); setLedger(led); setPayouts(pay);
    } finally {
      setLoadingData(false);
    }
  }, []);

  const selectMerchant = (m) => {
    setSelected(m);
    setTab("ledger");
    loadMerchantData(m);
  };

  const handlePayoutSuccess = () => {
    setShowModal(false);
    if (selected) loadMerchantData(selected);
  };

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

      {page === "logs" ? <LogsView /> : (
        <div className="layout">
          <aside className="sidebar">
            <h2>Merchants</h2>
            {loadingMerchants ? (
              <div className="loading">loading…</div>
            ) : merchants.map((m) => (
              <div
                key={m.id}
                className={`merchant-card ${selected?.id === m.id ? "active" : ""}`}
                onClick={() => selectMerchant(m)}
              >
                <div className="name">{m.name}</div>
                <div className="email">{m.email}</div>
              </div>
            ))}
          </aside>

          <main className="main">
            {!selected ? (
              <div className="empty-state">
                <div className="arrow">↖</div>
                <p>select a merchant</p>
              </div>
            ) : (
              <>
                <div className="merchant-header">
                  <div>
                    <h2>{selected.name}</h2>
                    <div className="sub">{selected.email}</div>
                  </div>
                  <button className="btn primary" onClick={() => setShowModal(true)}>
                    + New Payout
                  </button>
                </div>

                {loadingData ? (
                  <div className="loading">fetching data…</div>
                ) : (
                  <>
                    {balance && (
                      <div className="balance-grid">
                        <div className="balance-card highlight">
                          <div className="label">Available</div>
                          <div className="value">{toRupees(balance.available_balance)}</div>
                        </div>
                        <div className="balance-card">
                          <div className="label">Held</div>
                          <div className="value">{toRupees(balance.held_balance)}</div>
                        </div>
                        <div className="balance-card">
                          <div className="label">Total Credits</div>
                          <div className="value">{toRupees(balance.total_credits)}</div>
                        </div>
                        <div className="balance-card">
                          <div className="label">Total Debits</div>
                          <div className="value">{toRupees(balance.total_debits)}</div>
                        </div>
                      </div>
                    )}

                    <div className="tabs">
                      <button
                        className={`tab ${tab === "ledger" ? "active" : ""}`}
                        onClick={() => setTab("ledger")}
                      >Ledger</button>
                      <button
                        className={`tab ${tab === "payouts" ? "active" : ""}`}
                        onClick={() => setTab("payouts")}
                      >Payouts</button>
                    </div>

                    {tab === "ledger"  && <LedgerTable  entries={ledger} />}
                    {tab === "payouts" && <PayoutsTable payouts={payouts} />}
                  </>
                )}
              </>
            )}
          </main>
        </div>
      )}

      {page === "dashboard" && showModal && selected && (
        <PayoutModal
          merchant={selected}
          onClose={() => setShowModal(false)}
          onSuccess={handlePayoutSuccess}
        />
      )}
    </div>
  );
}
