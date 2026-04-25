from django.db import models
from django.utils import timezone
import uuid

class Payout(models.Model):
    # This is the state machine. Valid transitions enforced in code:
    # pending → processing → completed
    # pending → processing → failed
    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'

    VALID_TRANSITIONS = {
        STATUS_PENDING: [STATUS_PROCESSING],
        STATUS_PROCESSING: [STATUS_COMPLETED, STATUS_FAILED],
        STATUS_COMPLETED: [],   # terminal
        STATUS_FAILED: [],      # terminal
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey('merchants.Merchant', on_delete=models.CASCADE, related_name='payouts')
    bank_account = models.ForeignKey('merchants.BankAccount', on_delete=models.CASCADE)
    amount_paise = models.BigIntegerField()
    status = models.CharField(max_length=20, default=STATUS_PENDING)
    attempt_count = models.IntegerField(default=0)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def transition_to(self, new_status):
        """Enforces the state machine. Raises if transition is illegal."""
        allowed = self.VALID_TRANSITIONS.get(self.status, [])
        if new_status not in allowed:
            raise ValueError(
                f"Illegal state transition: {self.status} → {new_status}"
            )
        self.status = new_status

    def __str__(self):
        return f"Payout {self.id} | {self.merchant.name} | {self.status}"


class IdempotencyKey(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey('merchants.Merchant', on_delete=models.CASCADE)
    key = models.CharField(max_length=255)
    # Store the full response so we can replay it exactly
    response_status_code = models.IntegerField()
    response_body = models.JSONField()
    payout = models.ForeignKey(Payout, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        # KEY CONSTRAINT: key is unique per merchant
        unique_together = [('merchant', 'key')]
        indexes = [
            models.Index(fields=['merchant', 'key']),
        ]

# Create your models here.
