import { useState } from "react";
import { createPayout } from "../api";

export default function PayoutModal({ merchant, onClose, onSuccess }) {
  const [amount, setAmount]               = useState("");
  const [bankAccountId, setBankAccountId] = useState(merchant.bank_accounts[0]?.id ?? "");
  const [error, setError]                 = useState("");
  const [loading, setLoading]             = useState(false);

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
