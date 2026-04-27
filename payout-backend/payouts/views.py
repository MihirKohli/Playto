import logging
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

logger = logging.getLogger('payouts')


class PayoutCreateView(APIView):

    async def post(self, request):
        merchant_id     = request.headers.get('X-Merchant-Id')
        idempotency_key = request.headers.get('Idempotency-Key')

        logger.info('Payout request received',
                    extra={'context': {'merchant_id': merchant_id,
                                       'idempotency_key': idempotency_key}})

        if not idempotency_key:
            logger.warning('Missing Idempotency-Key header',
                           extra={'context': {'merchant_id': merchant_id}})
            return Response({'error': 'Idempotency-Key header required'}, status=400)

        try:
            merchant = await Merchant.objects.aget(id=merchant_id)
            logger.debug('Merchant resolved',
                         extra={'context': {'merchant_id': merchant_id,
                                            'name': merchant.name}})
        except (Merchant.DoesNotExist, ValueError):
            logger.warning('Merchant not found',
                           extra={'context': {'merchant_id': merchant_id}})
            return Response({'error': 'Merchant not found'}, status=404)

        raw_amount = request.data.get('amount_paise')
        try:
            amount_paise = int(raw_amount)
        except (TypeError, ValueError):
            logger.warning('Invalid payout amount',
                           extra={'context': {'merchant_id': merchant_id,
                                              'raw_amount': raw_amount}})
            return Response({'error': 'Invalid amount'}, status=400)

        if amount_paise <= 0:
            logger.warning('Payout amount not positive',
                           extra={'context': {'merchant_id': merchant_id,
                                              'amount_paise': amount_paise}})
            return Response({'error': 'Invalid amount'}, status=400)

        logger.debug('Amount validated',
                     extra={'context': {'merchant_id': merchant_id,
                                        'amount_paise': amount_paise}})

        bank_account_id = request.data.get('bank_account_id')
        try:
            bank_account = await merchant.bank_accounts.aget(id=bank_account_id)
            logger.debug('Bank account resolved',
                         extra={'context': {'merchant_id': merchant_id,
                                            'bank_account_id': str(bank_account_id),
                                            'masked': f'****{bank_account.account_number[-4:]}',
                                            'ifsc': bank_account.ifsc_code}})
        except (BankAccount.DoesNotExist, ValueError):
            logger.warning('Bank account not found',
                           extra={'context': {'merchant_id': merchant_id,
                                              'bank_account_id': str(bank_account_id)}})
            return Response({'error': 'Bank account not found'}, status=404)

        logger.info('Starting atomic payout creation',
                    extra={'context': {'merchant_id': merchant_id,
                                       'amount_paise': amount_paise,
                                       'bank_account_id': str(bank_account_id),
                                       'idempotency_key': idempotency_key}})

        response_data, response_status, payout = await sync_to_async(
            self._create_payout_atomic
        )(merchant, bank_account, amount_paise, idempotency_key)

        if payout is not None:
            logger.info('Payout created — dispatching to Celery',
                        extra={'context': {'payout_id': str(payout.id),
                                           'merchant_id': merchant_id,
                                           'amount_paise': amount_paise}})
            process_payout.delay(str(payout.id))
        else:
            logger.info('No new payout created (idempotent hit or insufficient balance)',
                        extra={'context': {'merchant_id': merchant_id,
                                           'response_status': response_status}})

        return Response(response_data, status=response_status)

    def _create_payout_atomic(self, merchant, bank_account, amount_paise, idempotency_key):
        with transaction.atomic():
            logger.debug('Acquiring merchant row lock',
                         extra={'context': {'merchant_id': str(merchant.id)}})

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
                logger.info('Idempotent response — returning cached result',
                            extra={'context': {'merchant_id': str(merchant.id),
                                               'idempotency_key': idempotency_key,
                                               'cached_status': existing.response_status_code}})
                return existing.response_body, existing.response_status_code, None

            logger.debug('Calculating available balance',
                         extra={'context': {'merchant_id': str(merchant.id)}})

            balance_data = LedgerEntry.objects.filter(
                merchant=locked_merchant
            ).aggregate(
                credits=Sum('amount_paise', filter=Q(entry_type='CREDIT')),
                debits=Sum('amount_paise',  filter=Q(entry_type='DEBIT')),
            )

            credits   = balance_data['credits'] or 0
            debits    = balance_data['debits']  or 0
            available = credits - debits

            logger.debug('Balance check',
                         extra={'context': {'merchant_id': str(merchant.id),
                                            'credits': credits,
                                            'debits': debits,
                                            'available': available,
                                            'requested': amount_paise,
                                            'sufficient': available >= amount_paise}})

            if available < amount_paise:
                logger.warning('Insufficient balance',
                               extra={'context': {'merchant_id': str(merchant.id),
                                                  'available': available,
                                                  'requested': amount_paise,
                                                  'shortfall': amount_paise - available}})
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

            logger.debug('Creating payout record',
                         extra={'context': {'merchant_id': str(merchant.id),
                                            'amount_paise': amount_paise}})

            payout = Payout.objects.create(
                merchant=locked_merchant,
                bank_account=bank_account,
                amount_paise=amount_paise,
                status=Payout.STATUS_PENDING,
            )

            logger.debug('Creating HELD debit ledger entry',
                         extra={'context': {'payout_id': str(payout.id),
                                            'amount_paise': amount_paise}})

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

            logger.info('Payout record created successfully',
                        extra={'context': {'payout_id': str(payout.id),
                                           'merchant_id': str(merchant.id),
                                           'amount_paise': amount_paise,
                                           'status': payout.status}})
            return response_data, 201, payout
