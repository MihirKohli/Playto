import logging
from django.db.models import Sum, Q
from adrf.views import APIView
from rest_framework.response import Response

from .models import Merchant, LedgerEntry
from .serializers import MerchantSerializer, LedgerEntrySerializer
from payouts.models import Payout
from payouts.serializers import PayoutSerializer

logger = logging.getLogger('merchants')


class MerchantListView(APIView):
    async def get(self, request):
        logger.info('Merchant list requested',
                    extra={'context': {'ip': request.META.get('REMOTE_ADDR')}})

        merchants = [m async for m in Merchant.objects.prefetch_related('bank_accounts').all()]

        logger.info('Merchant list returned',
                    extra={'context': {'count': len(merchants),
                                       'ids': [str(m.id) for m in merchants]}})
        return Response(MerchantSerializer(merchants, many=True).data)


class MerchantBalanceView(APIView):
    async def get(self, request, merchant_id):
        logger.info('Balance requested',
                    extra={'context': {'merchant_id': str(merchant_id)}})

        try:
            merchant = await Merchant.objects.aget(id=merchant_id)
            logger.debug('Merchant found',
                         extra={'context': {'merchant_id': str(merchant_id),
                                            'name': merchant.name}})
        except Merchant.DoesNotExist:
            logger.warning('Merchant not found for balance request',
                           extra={'context': {'merchant_id': str(merchant_id)}})
            return Response({'error': 'Merchant not found'}, status=404)

        logger.debug('Aggregating ledger entries for balance',
                     extra={'context': {'merchant_id': str(merchant_id)}})

        agg = await LedgerEntry.objects.filter(merchant=merchant).aaggregate(
            total_credits=Sum('amount_paise', filter=Q(entry_type='CREDIT')),
            total_debits=Sum('amount_paise', filter=Q(entry_type='DEBIT')),
            held_balance=Sum('amount_paise', filter=Q(entry_type='DEBIT', status='HELD')),
        )

        total_credits = agg['total_credits'] or 0
        total_debits  = agg['total_debits']  or 0
        held_balance  = agg['held_balance']  or 0
        available     = total_credits - total_debits

        logger.info('Balance calculated',
                    extra={'context': {'merchant_id': str(merchant_id),
                                       'name': merchant.name,
                                       'available_balance': available,
                                       'held_balance': held_balance,
                                       'total_credits': total_credits,
                                       'total_debits': total_debits}})
        return Response({
            'available_balance': available,
            'held_balance': held_balance,
            'total_credits': total_credits,
            'total_debits': total_debits,
        })


class MerchantLedgerView(APIView):
    async def get(self, request, merchant_id):
        logger.info('Ledger requested',
                    extra={'context': {'merchant_id': str(merchant_id)}})

        try:
            merchant = await Merchant.objects.aget(id=merchant_id)
            logger.debug('Merchant found for ledger',
                         extra={'context': {'merchant_id': str(merchant_id),
                                            'name': merchant.name}})
        except Merchant.DoesNotExist:
            logger.warning('Merchant not found for ledger request',
                           extra={'context': {'merchant_id': str(merchant_id)}})
            return Response({'error': 'Merchant not found'}, status=404)

        entries = [e async for e in
                   LedgerEntry.objects.filter(merchant=merchant).order_by('-created_at')[:50]]

        logger.info('Ledger returned',
                    extra={'context': {'merchant_id': str(merchant_id),
                                       'name': merchant.name,
                                       'entry_count': len(entries)}})
        return Response(LedgerEntrySerializer(entries, many=True).data)


class MerchantPayoutListView(APIView):
    async def get(self, request, merchant_id):
        logger.info('Payouts list requested',
                    extra={'context': {'merchant_id': str(merchant_id)}})

        try:
            merchant = await Merchant.objects.aget(id=merchant_id)
            logger.debug('Merchant found for payouts list',
                         extra={'context': {'merchant_id': str(merchant_id),
                                            'name': merchant.name}})
        except Merchant.DoesNotExist:
            logger.warning('Merchant not found for payouts list',
                           extra={'context': {'merchant_id': str(merchant_id)}})
            return Response({'error': 'Merchant not found'}, status=404)

        payouts = [p async for p in
                   Payout.objects.filter(merchant=merchant).order_by('-created_at')[:50]]

        logger.info('Payouts list returned',
                    extra={'context': {'merchant_id': str(merchant_id),
                                       'name': merchant.name,
                                       'payout_count': len(payouts)}})
        return Response(PayoutSerializer(payouts, many=True).data)
