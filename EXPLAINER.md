# Playto Payout System — Explainer

## Background

When I started developing this codebase, Django's ORM was synchronous, so I had to rewrite the critical section using `sync_to_async` to keep the async view from blocking the event loop.

Initially while developing the payout part, I had applied locks step by step first the merchant would get a transaction lock, then the idempotency part would get a lock, followed by the payout creation. The issue with this approach was that if async calls are made to the API it creates concurrency issues two requests could slip between the gaps and both pass the idempotency check before either one stores the key. So I realised we have to apply the lock on the whole process instead of on each sub-step. I wrapped the entire critical section in a single `transaction.atomic()` with one `select_for_update()` at the top, so the whole thing idempotency check, balance check, payout write executes as one atomic unit.

---

## 1. The Ledger

**Paste your balance calculation query. Why did you model credits and debits this way?**

```python
balance_data = LedgerEntry.objects.filter(
    merchant=locked_merchant
).aggregate(
    credits=Sum('amount_paise', filter=Q(entry_type='CREDIT')),
    debits=Sum('amount_paise',  filter=Q(entry_type='DEBIT')),
)

credits   = balance_data['credits'] or 0
debits    = balance_data['debits']  or 0
available = credits - debits
```

The balance is calculated from all ledger entries values are derived at query time from all previous entries rather than relying on a stored variable. A cached balance field can have wrong or stale values if a write fails mid-transaction. Summing from the ledger always gives an accurate result and also keeps a full audit trail of every credit and debit.

---

## 2. The Lock

**Paste the exact code that prevents two concurrent payouts from overdrawing a balance. Explain what database primitive it relies on.**

```python
@sync_to_async
def _do_atomic():
    with transaction.atomic():
        locked_merchant = (
            Merchant.objects
            .select_for_update()
            .get(id=merchant.id)
        )

        existing = IdempotencyKey.objects.filter(
            merchant=locked_merchant,
            key=idempotency_key,
            expires_at__gt=timezone.now(),
        ).first()

        if existing:
            return existing.response_body, existing.response_status_code, None

        balance_data = LedgerEntry.objects.filter(
            merchant=locked_merchant
        ).aggregate(
            credits=Sum('amount_paise', filter=Q(entry_type='CREDIT')),
            debits=Sum('amount_paise',  filter=Q(entry_type='DEBIT')),
        )

        credits   = balance_data['credits'] or 0
        debits    = balance_data['debits']  or 0
        available = credits - debits

        if available < amount_paise:
            ...  # store idempotency key and return 400

        # payout + debit ledger entry created here
```

The whole transaction block gets a lock so the second transaction will only execute after the first one finishes and releases it. The database primitive it relies on is `select_for_update()`, which issues a PostgreSQL `SELECT ... FOR UPDATE` an exclusive row-level lock on the merchant row that is held for the entire duration of the `transaction.atomic()` block. Any other transaction trying to lock the same row will block until the first one commits.

---

## 3. The Idempotency

**How does your system know it has seen a key before? What happens if the first request is in flight when the second arrives?**

Idempotency keys are stored in the PostgreSQL database as `IdempotencyKey` rows. Each row stores the merchant, the key, the cached response body and status, and an `expires_at` of 24 hours.

The lookup happens inside the `transaction.atomic()` block after the merchant row lock is acquired:

```python
existing = IdempotencyKey.objects.filter(
    merchant=locked_merchant,
    key=idempotency_key,
    expires_at__gt=timezone.now(),
).first()

if existing:
    return existing.response_body, existing.response_status_code, None
```

If the first request is still in flight when the second one arrives, the second will block at `select_for_update()` waiting for the merchant row lock. Once the first transaction commits and stores the `IdempotencyKey` row, the second request acquires the lock, finds the existing key, and returns the cached response without reprocessing the payout.

---

## 4. The State Machine

**Where in the code is failed-to-completed blocked? Show the check.**

In `payouts/models.py`, the `Payout` model has a `VALID_TRANSITIONS` dict and a `transition_to` method that enforces it:

```python
VALID_TRANSITIONS = {
    STATUS_PENDING:    [STATUS_PROCESSING],
    STATUS_PROCESSING: [STATUS_PENDING, STATUS_COMPLETED, STATUS_FAILED],
    STATUS_COMPLETED:  [],
    STATUS_FAILED:     [],
}

def transition_to(self, new_status):
    allowed = self.VALID_TRANSITIONS.get(self.status, [])
    if new_status not in allowed:
        raise ValueError(
            f"Illegal state transition: {self.status} → {new_status}"
        )
    self.status = new_status
```

Both `STATUS_FAILED` and `STATUS_COMPLETED` map to an empty list, so any attempt to transition out of them including `failed → completed` — raises a `ValueError` immediately and no database write happens.

---

## 5. The AI Audit

**One specific example where AI wrote subtly wrong code (bad locking, wrong aggregation, race condition). Paste what it gave you, what you caught, and what you replaced it with.**

**What AI gave me** — the idempotency check was outside the lock, in its own separate step before the merchant row was acquired:

```python
# idempotency check runs BEFORE the merchant lock
existing = await IdempotencyKey.objects.filter(
    key=idempotency_key,
    expires_at__gt=timezone.now(),
).afirst()

if existing:
    return existing.response_body, existing.response_status_code

# separate atomic block for balance + payout
async with transaction.atomic():
    locked_merchant = await Merchant.objects.select_for_update().aget(id=merchant_id)
    # balance check and payout creation here
```

**What I caught** — two concurrent requests with the same idempotency key could both pass the `existing` check at the same time, before either one had stored the key. That means two payouts get created and dispatched for the same request — a direct financial double-spend.

**What I replaced it with** — move the idempotency check inside the single atomic block, after the row lock is already held:

```python
@sync_to_async
def _do_atomic():
    with transaction.atomic():
        # lock first
        locked_merchant = Merchant.objects.select_for_update().get(id=merchant.id)

        # idempotency check is now inside the lock — no race possible
        existing = IdempotencyKey.objects.filter(
            merchant=locked_merchant,
            key=idempotency_key,
            expires_at__gt=timezone.now(),
        ).first()

        if existing:
            return existing.response_body, existing.response_status_code, None

        # balance check + payout + ledger write all in the same atomic block
```

Now the whole critical section is one atomic operation no second request can get between the idempotency check and the payout write.
