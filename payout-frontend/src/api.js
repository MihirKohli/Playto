const BASE_URL = "http://127.0.0.1:8000";

export async function getDashboard() {
  const res = await fetch(`${BASE_URL}/dashboard`);
  return res.json();
}

export async function createPayout(amount_paise) {
  const res = await fetch(`${BASE_URL}/payouts`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify({
      amount_paise,
      bank_account_id: 1,
    }),
  });

  return res.json();
}