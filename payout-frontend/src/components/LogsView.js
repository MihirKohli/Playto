import React, { useState, useEffect, useCallback } from "react";
import { getLogs } from "../api";
import { fmtDate } from "../utils";

const LEVELS = ['', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'];

export default function LogsView() {
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
                    <td className="log-location">{log.module}.{log.func_name}:{log.line_no}</td>
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
                        <pre className="log-ctx-pre">{JSON.stringify(log.context, null, 2)}</pre>
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
