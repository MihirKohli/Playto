import { useState, useEffect, useCallback } from "react";
import { getMerchants, getBalance, getLedger, getPayouts } from "../api";
import { toRupees } from "../utils";
import LedgerTable from "./LedgerTable";
import PayoutsTable from "./PayoutsTable";
import PayoutModal from "./PayoutModal";

export default function Dashboard() {
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
    <>
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

      {showModal && selected && (
        <PayoutModal
          merchant={selected}
          onClose={() => setShowModal(false)}
          onSuccess={handlePayoutSuccess}
        />
      )}
    </>
  );
}
