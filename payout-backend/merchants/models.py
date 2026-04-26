from django.db import models
import uuid


class Merchant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class BankAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name='bank_accounts')
    account_number = models.CharField(max_length=20)
    ifsc_code = models.CharField(max_length=11)
    account_holder_name = models.CharField(max_length=255)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class LedgerEntry(models.Model):
    ENTRY_TYPES = [
        ('CREDIT', 'Credit'),   # money coming in
        ('DEBIT', 'Debit'),     # money going out or held
    ]
    STATUS_CHOICES = [
        ('SETTLED', 'Settled'),   # permanent
        ('HELD', 'Held'),         # pending payout — not final yet
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name='ledger_entries')
    entry_type = models.CharField(max_length=10, choices=ENTRY_TYPES)
    amount_paise = models.BigIntegerField()  
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='SETTLED')
    description = models.TextField(blank=True)
    payout = models.ForeignKey(
        'payouts.Payout', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ledger_entries'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['merchant', 'created_at']),
        ]

