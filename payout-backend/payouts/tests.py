import asyncio
import uuid
from unittest.mock import patch
from django.db.models import Sum, Q
from django.test import TransactionTestCase, AsyncClient

from merchants.models import Merchant, BankAccount, LedgerEntry
from payouts.models import Payout


def make_key():
    return str(uuid.uuid4())


class IdempotencyTests(TransactionTestCase):

    def setUp(self):
        self.client = AsyncClient()
        self.merchant = Merchant.objects.create(
            name='Test Merchant',
            email='test@example.com',
        )
        self.bank_account = BankAccount.objects.create(
            merchant=self.merchant,
            account_number='1234567890',
            ifsc_code='HDFC0001234',
            account_holder_name='Test Merchant',
            is_primary=True,
        )
        LedgerEntry.objects.create(
            merchant=self.merchant,
            entry_type='CREDIT',
            amount_paise=100_000,
            status='SETTLED',
            description='Test credit',
        )

    def _headers(self, key):
        return {
            'HTTP_X_MERCHANT_ID': str(self.merchant.id),
            'HTTP_IDEMPOTENCY_KEY': key,
        }

    def _payload(self, amount=10_000):
        return {'amount_paise': amount, 'bank_account_id': str(self.bank_account.id)}

    @patch('payouts.views.process_payout')
    async def test_same_key_returns_identical_response_and_one_payout(self, mock_task):
        key = make_key()

        r1 = await self.client.post(
            '/api/v1/payouts/', self._payload(),
            content_type='application/json', **self._headers(key),
        )
        r2 = await self.client.post(
            '/api/v1/payouts/', self._payload(),
            content_type='application/json', **self._headers(key),
        )

        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(r1.json(), r2.json())
        self.assertEqual(await Payout.objects.acount(), 1)

    @patch('payouts.views.process_payout')
    async def test_different_keys_create_independent_payouts(self, mock_task):
        r1 = await self.client.post(
            '/api/v1/payouts/', self._payload(),
            content_type='application/json', **self._headers(make_key()),
        )
        r2 = await self.client.post(
            '/api/v1/payouts/', self._payload(),
            content_type='application/json', **self._headers(make_key()),
        )

        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        self.assertNotEqual(r1.json()['id'], r2.json()['id'])
        self.assertEqual(await Payout.objects.acount(), 2)

    @patch('payouts.views.process_payout')
    async def test_idempotency_key_required(self, mock_task):
        r = await self.client.post(
            '/api/v1/payouts/', self._payload(),
            content_type='application/json',
            HTTP_X_MERCHANT_ID=str(self.merchant.id),
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn('Idempotency-Key', r.json()['error'])

    @patch('payouts.views.process_payout')
    async def test_failed_request_is_replayed_not_retried(self, mock_task):
        """A 400 response (insufficient funds) is stored and replayed on retry."""
        key = make_key()
        payload = {'amount_paise': 999_999_999, 'bank_account_id': str(self.bank_account.id)}

        r1 = await self.client.post(
            '/api/v1/payouts/', payload,
            content_type='application/json', **self._headers(key),
        )
        r2 = await self.client.post(
            '/api/v1/payouts/', payload,
            content_type='application/json', **self._headers(key),
        )

        self.assertEqual(r1.status_code, 400)
        self.assertEqual(r2.status_code, 400)
        self.assertEqual(r1.json(), r2.json())
        self.assertEqual(await Payout.objects.acount(), 0)

    @patch('payouts.views.process_payout')
    async def test_string_amount_returns_400_not_500(self, mock_task):
        """FIX #6: String amount_paise should return a clean 400, not crash."""
        payload = {'amount_paise': 'not_a_number', 'bank_account_id': str(self.bank_account.id)}
        r = await self.client.post(
            '/api/v1/payouts/', payload,
            content_type='application/json', **self._headers(make_key()),
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn('Invalid amount', r.json()['error'])

    @patch('payouts.views.process_payout')
    async def test_null_amount_returns_400(self, mock_task):
        """amount_paise missing entirely should be a clean 400."""
        payload = {'bank_account_id': str(self.bank_account.id)}
        r = await self.client.post(
            '/api/v1/payouts/', payload,
            content_type='application/json', **self._headers(make_key()),
        )
        self.assertEqual(r.status_code, 400)


class ConcurrencyTests(TransactionTestCase):

    def setUp(self):
        self.client = AsyncClient()
        self.merchant = Merchant.objects.create(
            name='Concurrent Merchant',
            email='concurrent@example.com',
        )
        self.bank_account = BankAccount.objects.create(
            merchant=self.merchant,
            account_number='9999999999',
            ifsc_code='ICIC0001234',
            account_holder_name='Concurrent Merchant',
            is_primary=True,
        )
        LedgerEntry.objects.create(
            merchant=self.merchant,
            entry_type='CREDIT',
            amount_paise=1000,
            status='SETTLED',
            description='Test credit',
        )

    async def _request(self, amount):
        return await self.client.post(
            '/api/v1/payouts/',
            {'amount_paise': amount, 'bank_account_id': str(self.bank_account.id)},
            content_type='application/json',
            HTTP_X_MERCHANT_ID=str(self.merchant.id),
            HTTP_IDEMPOTENCY_KEY=make_key(),
        )

    @patch('payouts.views.process_payout')
    async def test_two_concurrent_requests_cannot_overdraft(self, mock_task):
        """
        Balance = 1000 paise. Two simultaneous requests for 600 paise.
        SELECT FOR UPDATE ensures exactly one wins; the other gets 400.
        """
        r1, r2 = await asyncio.gather(
            self._request(600),
            self._request(600),
        )

        statuses = sorted([r1.status_code, r2.status_code])
        self.assertEqual(statuses, [201, 400], 'Exactly one request must succeed')
        self.assertEqual(await Payout.objects.acount(), 1)

        agg = await LedgerEntry.objects.filter(merchant=self.merchant).aaggregate(
            credits=Sum('amount_paise', filter=Q(entry_type='CREDIT')),
            debits=Sum('amount_paise', filter=Q(entry_type='DEBIT')),
        )
        balance = (agg['credits'] or 0) - (agg['debits'] or 0)
        self.assertEqual(balance, 400)

    @patch('payouts.views.process_payout')
    async def test_concurrent_same_key_no_double_debit(self, mock_task):
        """
        FIX #1 regression test: Two concurrent requests with the SAME
        idempotency key must produce exactly one payout and one debit,
        not two.
        """
        key = make_key()

        async def _request_with_key():
            return await self.client.post(
                '/api/v1/payouts/',
                {'amount_paise': 500, 'bank_account_id': str(self.bank_account.id)},
                content_type='application/json',
                HTTP_X_MERCHANT_ID=str(self.merchant.id),
                HTTP_IDEMPOTENCY_KEY=key,
            )

        r1, r2 = await asyncio.gather(
            _request_with_key(),
            _request_with_key(),
        )

        # Both should return 201 with the same response body
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(r1.json(), r2.json())

        # Only one payout and one debit must exist
        self.assertEqual(await Payout.objects.acount(), 1)
        debit_count = await LedgerEntry.objects.filter(
            merchant=self.merchant, entry_type='DEBIT'
        ).acount()
        self.assertEqual(debit_count, 1)

        # Balance integrity: 1000 - 500 = 500
        agg = await LedgerEntry.objects.filter(merchant=self.merchant).aaggregate(
            credits=Sum('amount_paise', filter=Q(entry_type='CREDIT')),
            debits=Sum('amount_paise', filter=Q(entry_type='DEBIT')),
        )
        balance = (agg['credits'] or 0) - (agg['debits'] or 0)
        self.assertEqual(balance, 500)

    @patch('payouts.views.process_payout')
    async def test_exact_balance_amount_succeeds(self, mock_task):
        r = await self._request(1000)
        self.assertEqual(r.status_code, 201)

        agg = await LedgerEntry.objects.filter(merchant=self.merchant).aaggregate(
            credits=Sum('amount_paise', filter=Q(entry_type='CREDIT')),
            debits=Sum('amount_paise', filter=Q(entry_type='DEBIT')),
        )
        self.assertEqual((agg['credits'] or 0) - (agg['debits'] or 0), 0)

    @patch('payouts.views.process_payout')
    async def test_overdraft_rejected(self, mock_task):
        r = await self._request(1001)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json(), {'error': 'Insufficient balance'})
        self.assertEqual(await Payout.objects.acount(), 0)


class ValidationTests(TransactionTestCase):

    def setUp(self):
        self.client = AsyncClient()
        self.merchant = Merchant.objects.create(
            name='Validation Merchant',
            email='validation@example.com',
        )
        self.bank_account = BankAccount.objects.create(
            merchant=self.merchant,
            account_number='1111111111',
            ifsc_code='HDFC0001111',
            account_holder_name='Validation Merchant',
            is_primary=True,
        )
        LedgerEntry.objects.create(
            merchant=self.merchant,
            entry_type='CREDIT',
            amount_paise=50_000,
            status='SETTLED',
            description='Test credit',
        )

    def _post(self, payload, *, merchant_id=None, key=None):
        return self.client.post(
            '/api/v1/payouts/', payload,
            content_type='application/json',
            HTTP_X_MERCHANT_ID=merchant_id if merchant_id is not None else str(self.merchant.id),
            HTTP_IDEMPOTENCY_KEY=key or make_key(),
        )

    async def test_zero_amount_returns_400(self):
        r = await self._post({'amount_paise': 0, 'bank_account_id': str(self.bank_account.id)})
        self.assertEqual(r.status_code, 400)
        self.assertIn('Invalid amount', r.json()['error'])

    async def test_negative_amount_returns_400(self):
        r = await self._post({'amount_paise': -500, 'bank_account_id': str(self.bank_account.id)})
        self.assertEqual(r.status_code, 400)
        self.assertIn('Invalid amount', r.json()['error'])

    async def test_nonexistent_bank_account_returns_404(self):
        r = await self._post({'amount_paise': 1000, 'bank_account_id': str(uuid.uuid4())})
        self.assertEqual(r.status_code, 404)
        self.assertIn('Bank account', r.json()['error'])

    async def test_non_uuid_bank_account_id_returns_404(self):
        r = await self._post({'amount_paise': 1000, 'bank_account_id': 'not-a-uuid'})
        self.assertEqual(r.status_code, 404)

    async def test_non_uuid_merchant_id_returns_404(self):
        r = await self._post(
            {'amount_paise': 1000, 'bank_account_id': str(self.bank_account.id)},
            merchant_id='not-a-uuid',
        )
        self.assertEqual(r.status_code, 404)

    async def test_zero_balance_merchant_returns_insufficient_funds(self):
        empty_merchant = await Merchant.objects.acreate(
            name='Empty Merchant',
            email='empty@example.com',
        )
        empty_bank = await empty_merchant.bank_accounts.acreate(
            account_number='0000000000',
            ifsc_code='HDFC0000000',
            account_holder_name='Empty Merchant',
            is_primary=True,
        )
        r = await self.client.post(
            '/api/v1/payouts/',
            {'amount_paise': 1, 'bank_account_id': str(empty_bank.id)},
            content_type='application/json',
            HTTP_X_MERCHANT_ID=str(empty_merchant.id),
            HTTP_IDEMPOTENCY_KEY=make_key(),
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json(), {'error': 'Insufficient balance'})