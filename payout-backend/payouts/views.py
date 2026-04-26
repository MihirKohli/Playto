import json
from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone
from datetime import timedelta
from asgiref.sync import sync_to_async
from adrf.views import APIView
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from merchants.models import Merchant, BankAccount, LedgerEntry
from .models import Payout, IdempotencyKey
from .serializers import PayoutSerializer
from .tasks import process_payout


class PayoutCreateView(APIView):

    async def post(self, request):
        merchant_id = request.headers.get('X-Merchant-Id')
        idempotency_key = request.headers.get('Idempotency-Key')

        if not idempotency_key:
            return Response({'error': 'Idempotency-Key header required'}, status=400)

        try:
            merchant = await Merchant.objects.aget(id=merchant_id)
        except (Merchant.DoesNotExist, ValueError):
            return Response({'error': 'Merchant not found'}, status=404)

        # ── VALIDATE INPUT ─────────────────────────────────────────────────
        # FIX #6: Explicitly cast amount_paise to int. Previously, a string
        # value like "10000" would throw TypeError on `<= 0`, returning a
        # 500 instead of a clean 400.
        raw_amount = request.data.get('amount_paise')
        try:
            amount_paise = int(raw_amount)
        except (TypeError, ValueError):
            return Response({'error': 'Invalid amount'}, status=400)

        if amount_paise <= 0:
            return Response({'error': 'Invalid amount'}, status=400)

        bank_account_id = request.data.get('bank_account_id')
        try:
            bank_account = await merchant.bank_accounts.aget(id=bank_account_id)
        except (BankAccount.DoesNotExist, ValueError):
            return Response({'error': 'Bank account not found'}, status=404)

        # ── SINGLE ATOMIC BLOCK: idempotency + balance check + payout ─────
        # FIX #1 (THE BIG ONE): Previously, payout creation and idempotency
        # key storage lived in separate transactions. Two concurrent requests
        # with the SAME idempotency key could both pass the early lookup,
        # both create payouts (double-debit), and then aget_or_create would
        # discard the loser's *response* but leave its payout + ledger entry
        # committed. Now everything is in one atomic block under the merchant
        # row lock, so the second request sees the key the first created.
        response_data, response_status, payout = await sync_to_async(
            self._create_payout_atomic
        )(merchant, bank_account, amount_paise, idempotency_key)

        if payout is not None:
            process_payout.delay(str(payout.id))

        return Response(response_data, status=response_status)

    def _create_payout_atomic(self, merchant, bank_account, amount_paise, idempotency_key):
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
                debits=Sum('amount_paise', filter=Q(entry_type='DEBIT')),
            )

            credits = balance_data['credits'] or 0
            debits = balance_data['debits'] or 0
            available = credits - debits

            if available < amount_paise:
                response_data = {'error': 'Insufficient balance'}
                IdempotencyKey.objects.create(
                    merchant=locked_merchant,
                    key=idempotency_key,
                    response_status_code=400,
                    response_body=response_data,
                    payout=None,
                    expires_at=timezone.now() + timedelta(hours=24),
                )
                return response_data, 400, None

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

            response_data = json.loads(
                JSONRenderer().render(PayoutSerializer(payout).data)
            )

            IdempotencyKey.objects.create(
                merchant=locked_merchant,
                key=idempotency_key,
                response_status_code=201,
                response_body=response_data,
                payout=payout,
                expires_at=timezone.now() + timedelta(hours=24),
            )

            return response_data, 201, payout
