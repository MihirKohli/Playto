from asgiref.sync import sync_to_async
from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone
from datetime import timedelta
from adrf.views import APIView
from rest_framework.response import Response
from rest_framework import status

from merchants.models import Merchant, LedgerEntry
from .models import Payout, IdempotencyKey
from .serializers import PayoutSerializer
from .tasks import process_payout


class PayoutCreateView(APIView):

    async def post(self, request):
        merchant_id = request.headers.get('X-Merchant-Id')  # auth simplified
        idempotency_key = request.headers.get('Idempotency-Key')

        if not idempotency_key:
            return Response({'error': 'Idempotency-Key header required'}, status=400)

        try:
            merchant = await Merchant.objects.aget(id=merchant_id)
        except Merchant.DoesNotExist:
            return Response({'error': 'Merchant not found'}, status=404)

        # ── IDEMPOTENCY CHECK ──────────────────────────────────────────────
        existing = await IdempotencyKey.objects.filter(
            merchant=merchant,
            key=idempotency_key,
            expires_at__gt=timezone.now()
        ).afirst()

        if existing:
            return Response(existing.response_body, status=existing.response_status_code)

        # ── VALIDATE INPUT ─────────────────────────────────────────────────
        amount_paise = request.data.get('amount_paise')
        bank_account_id = request.data.get('bank_account_id')

        if not amount_paise or amount_paise <= 0:
            return Response({'error': 'Invalid amount'}, status=400)

        try:
            bank_account = await merchant.bank_accounts.aget(id=bank_account_id)
        except Exception:
            return Response({'error': 'Bank account not found'}, status=404)

        # ── CONCURRENCY-SAFE PAYOUT CREATION ──────────────────────────────
        try:
            payout, response_data, response_status_code = await sync_to_async(
                self._create_payout_atomic
            )(merchant, bank_account, amount_paise)
        except InsufficientFundsError:
            response_data = {'error': 'Insufficient balance'}
            response_status_code = 400
            payout = None

        # ── STORE IDEMPOTENCY KEY ──────────────────────────────────────────
        await IdempotencyKey.objects.aget_or_create(
            merchant=merchant,
            key=idempotency_key,
            defaults={
                'response_status_code': response_status_code,
                'response_body': response_data,
                'payout': payout,
                'expires_at': timezone.now() + timedelta(hours=24),
            }
        )

        if payout is not None:
            process_payout.delay(str(payout.id))

        return Response(response_data, status=response_status_code)

    @transaction.atomic
    def _create_payout_atomic(self, merchant, bank_account, amount_paise):
        """
        THE CRITICAL SECTION.

        SELECT FOR UPDATE locks the merchant's ledger rows so no concurrent
        request can read or modify them until this transaction commits.

        This is the database primitive that prevents overdraft.
        Python-level locks (threading.Lock, etc.) don't work here because:
          1. Multiple processes / workers can be running
          2. They don't survive server restarts
          3. They don't span network boundaries
        """
        locked_merchant = (
            Merchant.objects
            .select_for_update()   # ← acquires row-level lock in PostgreSQL
            .get(id=merchant.id)
        )

        balance_data = LedgerEntry.objects.filter(
            merchant=locked_merchant
        ).aggregate(
            credits=Sum('amount_paise', filter=Q(entry_type='CREDIT')),
            debits=Sum('amount_paise', filter=Q(entry_type='DEBIT')),
        )

        credits = balance_data['credits'] or 0
        debits = balance_data['debits'] or 0
        available = credits - debits

        if available < amount_paise:
            raise InsufficientFundsError()

        payout = Payout.objects.create(
            merchant=locked_merchant,
            bank_account=bank_account,
            amount_paise=amount_paise,
            status=Payout.STATUS_PENDING,
        )

        LedgerEntry.objects.create(
            merchant=locked_merchant,
            entry_type='DEBIT',
            amount_paise=amount_paise,
            status='HELD',
            description=f'Hold for payout {payout.id}',
            payout=payout,
        )

        response_data = PayoutSerializer(payout).data
        return payout, response_data, 201


class InsufficientFundsError(Exception):
    pass
