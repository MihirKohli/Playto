import random
import time
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from .models import Payout
from merchants.models import LedgerEntry


@shared_task(bind=True, max_retries=3)
def process_payout(self, payout_id):
    """
    Picks up a pending payout and simulates bank settlement.
    70% success, 20% failure, 10% hang (timeout → retry).
    """
    try:
        with transaction.atomic():
            payout = (
                Payout.objects
                .select_for_update()
                .get(id=payout_id, status=Payout.STATUS_PENDING)
            )
            payout.transition_to(Payout.STATUS_PROCESSING)
            payout.processing_started_at = timezone.now()
            payout.attempt_count += 1
            payout.save()
    except Payout.DoesNotExist:
        # Already picked up by another worker or in wrong state — skip
        return

    # Simulate bank API call OUTSIDE the transaction (don't hold DB lock during IO)
    outcome = _simulate_bank_api()

    should_retry = False
    with transaction.atomic():
        payout = Payout.objects.select_for_update().get(id=payout_id)

        if outcome == 'success':
            payout.transition_to(Payout.STATUS_COMPLETED)
            payout.completed_at = timezone.now()
            LedgerEntry.objects.filter(payout=payout, status='HELD').update(status='SETTLED')
            payout.save()

        elif outcome == 'failure':
            _fail_payout(payout, reason='Bank rejected the transfer')

        elif outcome == 'hang':
            # Revert to pending so the retry attempt can pick it up.
            # We MUST commit this save before raising self.retry() —
            # raising inside the atomic block would roll it back.
            payout.status = Payout.STATUS_PENDING
            payout.save()
            should_retry = True

    # Raise retry AFTER the transaction commits so the PENDING save is durable.
    if should_retry:
        try:
            raise self.retry(countdown=2 ** self.request.retries * 10)
        except MaxRetriesExceededError:
            # All retries exhausted — fail the payout and release held funds.
            with transaction.atomic():
                payout = Payout.objects.select_for_update().get(id=payout_id)
                if payout.status == Payout.STATUS_PENDING:
                    payout.transition_to(Payout.STATUS_PROCESSING)
                    payout.save()
                    _fail_payout(payout, reason='Max retry attempts exceeded')


def _fail_payout(payout, reason=''):
    """
    Atomically: transition to failed + reverse the held funds.
    Both must succeed or neither does (caller must be inside atomic).
    """
    payout.transition_to(Payout.STATUS_FAILED)
    payout.failure_reason = reason
    payout.save()

    # Reverse the hold: create a CREDIT entry to undo the DEBIT
    held_entry = LedgerEntry.objects.get(payout=payout, entry_type='DEBIT', status='HELD')
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
        time.sleep(0.1)  # simulate hang
        return 'hang'


@shared_task
def retry_stuck_payouts():
    """
    Beat task: runs every 30s. Finds payouts stuck in processing > 30s.
    Uses skip_locked so parallel beat workers don't double-queue the same row.
    """
    cutoff = timezone.now() - timedelta(seconds=30)

    retry_ids = []
    with transaction.atomic():
        stuck = (
            Payout.objects
            .select_for_update(skip_locked=True)
            .filter(
                status=Payout.STATUS_PROCESSING,
                processing_started_at__lt=cutoff,
            )
        )
        for payout in stuck:
            if payout.attempt_count < 3:
                payout.status = Payout.STATUS_PENDING
                payout.save()
                retry_ids.append(str(payout.id))
            else:
                # Exhausted attempts — fail and release funds.
                _fail_payout(payout, reason='Max retry attempts exceeded')

    # Dispatch outside the transaction so workers see the committed PENDING status.
    for payout_id in retry_ids:
        process_payout.delay(payout_id)
