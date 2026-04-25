from django.db.models import Sum, Q
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import Merchant, LedgerEntry
from .serializers import MerchantSerializer, LedgerEntrySerializer


class MerchantListView(APIView):
    def get(self, request):
        merchants = Merchant.objects.prefetch_related('bank_accounts').all()
        return Response(MerchantSerializer(merchants, many=True).data)


class MerchantBalanceView(APIView):
    def get(self, request, merchant_id):
        try:
            merchant = Merchant.objects.get(id=merchant_id)
        except Merchant.DoesNotExist:
            return Response({'error': 'Merchant not found'}, status=404)

        agg = LedgerEntry.objects.filter(merchant=merchant).aggregate(
            total_credits=Sum('amount_paise', filter=Q(entry_type='CREDIT')),
            total_debits=Sum('amount_paise', filter=Q(entry_type='DEBIT')),
            held_balance=Sum('amount_paise', filter=Q(entry_type='DEBIT', status='HELD')),
        )

        total_credits = agg['total_credits'] or 0
        total_debits = agg['total_debits'] or 0
        held_balance = agg['held_balance'] or 0

        return Response({
            'available_balance': total_credits - total_debits,
            'held_balance': held_balance,
            'total_credits': total_credits,
            'total_debits': total_debits,
        })


class MerchantLedgerView(APIView):
    def get(self, request, merchant_id):
        try:
            merchant = Merchant.objects.get(id=merchant_id)
        except Merchant.DoesNotExist:
            return Response({'error': 'Merchant not found'}, status=404)

        entries = (
            LedgerEntry.objects
            .filter(merchant=merchant)
            .order_by('-created_at')[:50]
        )
        return Response(LedgerEntrySerializer(entries, many=True).data)


class MerchantPayoutListView(APIView):
    def get(self, request, merchant_id):
        try:
            merchant = Merchant.objects.get(id=merchant_id)
        except Merchant.DoesNotExist:
            return Response({'error': 'Merchant not found'}, status=404)

        from payouts.models import Payout
        from payouts.serializers import PayoutSerializer

        payouts = (
            Payout.objects
            .filter(merchant=merchant)
            .order_by('-created_at')[:50]
        )
        return Response(PayoutSerializer(payouts, many=True).data)
