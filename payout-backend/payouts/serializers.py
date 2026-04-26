from rest_framework import serializers
from .models import Payout


class PayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payout
        fields = [
            'id', 'merchant', 'bank_account', 'amount_paise', 'status',
            'attempt_count', 'processing_started_at', 'completed_at',
            'failure_reason', 'created_at', 'updated_at',
        ]
        read_only_fields = fields
