import random
import time
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from .models import Payout, IdempotencyKey
from merchants.models import LedgerEntry

MAX_PAYOUT_ATTEMPTS = 3


@shared_task(bind=True, max_retries=MAX_PAYOUT_ATTEMPTS)
def process_payout(self, payout_id):
    try:
        with transaction.atomic():
            payout = (
                Payout.objects
                .select_for_update(skip_locked=True)
                .get(id=payout_id, status=Payout.STATUS_PENDING)
            )
            payout.transition_to(Payout.STATUS_PROCESSING)
            payout.processing_started_at = timezone.now()
            payout.attempt_count += 1
            payout.save()
    except Payout.DoesNotExist:
        return

    outcome = _simulate_bank_api()

    should_retry = False
    with transaction.atomic():
        payout = Payout.objects.select_for_update().get(id=payout_id)

        if outcome == 'success':
            payout.transition_to(Payout.STATUS_COMPLETED)
            payout.completed_at = timezone.now()
            LedgerEntry.objects.filter(
                payout=payout, status='HELD'
            ).update(status='SETTLED')
            payout.save()

        elif outcome == 'failure':
            _fail_payout(payout, reason='Bank rejected the transfer')

        elif outcome == 'hang':
            payout.transition_to(Payout.STATUS_PENDING)
            payout.save()
            should_retry = True

    if should_retry:
        try:
            self.retry(countdown=2 ** self.request.retries * 10)
        except MaxRetriesExceededError:
            with transaction.atomic():
                payout = Payout.objects.select_for_update().get(id=payout_id)
                if payout.status == Payout.STATUS_PENDING:
                    payout.transition_to(Payout.STATUS_PROCESSING)
                    _fail_payout(payout, reason='Max retry attempts exceeded')


@shared_task
def retry_stuck_payouts():
    cutoff = timezone.now() - timedelta(seconds=30)

    with transaction.atomic():
        stuck_ids = list(
            Payout.objects
            .select_for_update(skip_locked=True)
            .filter(
                status=Payout.STATUS_PROCESSING,
                processing_started_at__lt=cutoff,
            )
            .values_list('id', flat=True)
        )

    retry_ids = []
    for payout_id in stuck_ids:
        with transaction.atomic():
            try:
                payout = (
                    Payout.objects
                    .select_for_update()
                    .get(id=payout_id, status=Payout.STATUS_PROCESSING)
                )
            except Payout.DoesNotExist:
                continue

            if payout.attempt_count < MAX_PAYOUT_ATTEMPTS:
                payout.transition_to(Payout.STATUS_PENDING)
                payout.save()
                retry_ids.append(str(payout_id))
            else:
                _fail_payout(payout, reason='Max retry attempts exceeded')

    for payout_id in retry_ids:
        process_payout.delay(payout_id)


@shared_task
def cleanup_expired_idempotency_keys():
    deleted_count, _ = IdempotencyKey.objects.filter(
        expires_at__lt=timezone.now()
    ).delete()
    return deleted_count


def _fail_payout(payout, reason=''):
    payout.transition_to(Payout.STATUS_FAILED)
    payout.failure_reason = reason
    payout.save()

    held_entry = LedgerEntry.objects.filter(
        payout=payout, entry_type='DEBIT', status='HELD'
    ).first()
    if held_entry is None:
        return

    LedgerEntry.objects.create(
        merchant=payout.merchant,
        entry_type='CREDIT',
        amount_paise=payout.amount_paise,
        status='SETTLED',
        description=f'Reversal for failed payout {payout.id}',
        payout=payout,
    )
    held_entry.status = 'SETTLED'
    held_entry.save()


def _simulate_bank_api():
    roll = random.random()
    if roll < 0.70:
        return 'success'
    elif roll < 0.90:
        return 'failure'
    else:
        time.sleep(0.1)
        return 'hang'
