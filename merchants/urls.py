from django.urls import path
from .views import MerchantListView, MerchantBalanceView, MerchantLedgerView, MerchantPayoutListView

urlpatterns = [
    path('', MerchantListView.as_view(), name='merchant-list'),
    path('<uuid:merchant_id>/balance/', MerchantBalanceView.as_view(), name='merchant-balance'),
    path('<uuid:merchant_id>/ledger/', MerchantLedgerView.as_view(), name='merchant-ledger'),
    path('<uuid:merchant_id>/payouts/', MerchantPayoutListView.as_view(), name='merchant-payouts'),
]
