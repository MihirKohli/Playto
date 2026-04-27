const BASE = process.env.REACT_APP_API_URL || "http://localhost:8000/api/v1";

export async function getMerchants() {
  const res = await fetch(`${BASE}/merchants/`);
  if (!res.ok) throw new Error("Failed to fetch merchants");
  return res.json();
}

export async function getBalance(merchantId) {
  const res = await fetch(`${BASE}/merchants/${merchantId}/balance/`);
  if (!res.ok) throw new Error("Failed to fetch balance");
  return res.json();
}

export async function getLedger(merchantId) {
  const res = await fetch(`${BASE}/merchants/${merchantId}/ledger/`);
  if (!res.ok) throw new Error("Failed to fetch ledger");
  return res.json();
}

export async function getPayouts(merchantId) {
  const res = await fetch(`${BASE}/merchants/${merchantId}/payouts/`);
  if (!res.ok) throw new Error("Failed to fetch payouts");
  return res.json();
}

export async function getLogs({ level = '', logger = '', limit = 100 } = {}) {
  const params = new URLSearchParams();
  if (level)  params.set('level', level);
  if (logger) params.set('logger', logger);
  params.set('limit', limit);
  const res = await fetch(`${BASE}/logs/?${params}`);
  if (!res.ok) throw new Error("Failed to fetch logs");
  return res.json();
}

export async function createPayout(merchantId, bankAccountId, amountPaise) {
  const res = await fetch(`${BASE}/payouts/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Merchant-Id": merchantId,
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify({ amount_paise: amountPaise, bank_account_id: bankAccountId }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Payout failed");
  return data;
}
