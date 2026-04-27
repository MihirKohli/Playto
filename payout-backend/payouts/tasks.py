import logging
import random
import time
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from .models import Payout, IdempotencyKey
from merchants.models import LedgerEntry

logger = logging.getLogger('payouts')

MAX_PAYOUT_ATTEMPTS = 3


@shared_task(bind=True, max_retries=MAX_PAYOUT_ATTEMPTS)
def process_payout(self, payout_id):
    logger.info('Payout task started',
                extra={'context': {'payout_id': payout_id,
                                   'attempt': self.request.retries + 1}})

    try:
        with transaction.atomic():
            payout = (
                Payout.objects
                .select_for_update(skip_locked=True)
                .get(id=payout_id, status=Payout.STATUS_PENDING)
            )
            logger.debug('Payout locked — transitioning to PROCESSING',
                         extra={'context': {'payout_id': payout_id,
                                            'merchant_id': str(payout.merchant_id),
                                            'amount_paise': payout.amount_paise}})
            payout.transition_to(Payout.STATUS_PROCESSING)
            payout.processing_started_at = timezone.now()
            payout.attempt_count += 1
            payout.save()
            logger.info('Payout status → PROCESSING',
                        extra={'context': {'payout_id': payout_id,
                                           'attempt_count': payout.attempt_count,
                                           'merchant_id': str(payout.merchant_id)}})
    except Payout.DoesNotExist:
        logger.warning('Payout not found or already processing — skipped',
                       extra={'context': {'payout_id': payout_id}})
        return

    logger.debug('Calling bank API', extra={'context': {'payout_id': payout_id}})
    outcome = _simulate_bank_api()
    logger.info('Bank API responded',
                extra={'context': {'payout_id': payout_id, 'outcome': outcome}})

    should_retry = False
    with transaction.atomic():
        payout = Payout.objects.select_for_update().get(id=payout_id)

        if outcome == 'success':
            logger.info('Bank transfer succeeded — settling ledger',
                        extra={'context': {'payout_id': payout_id,
                                           'merchant_id': str(payout.merchant_id),
                                           'amount_paise': payout.amount_paise}})
            payout.transition_to(Payout.STATUS_COMPLETED)
            payout.completed_at = timezone.now()
            updated = LedgerEntry.objects.filter(payout=payout, status='HELD').update(status='SETTLED')
            payout.save()
            logger.info('Payout status → COMPLETED',
                        extra={'context': {'payout_id': payout_id,
                                           'ledger_entries_settled': updated,
                                           'completed_at': payout.completed_at.isoformat()}})

        elif outcome == 'failure':
            logger.warning('Bank rejected the transfer',
                           extra={'context': {'payout_id': payout_id,
                                              'merchant_id': str(payout.merchant_id),
                                              'amount_paise': payout.amount_paise}})
            _fail_payout(payout, reason='Bank rejected the transfer')

        elif outcome == 'hang':
            logger.warning('Bank API timed out — will retry',
                           extra={'context': {'payout_id': payout_id,
                                              'attempt_count': payout.attempt_count,
                                              'max_attempts': MAX_PAYOUT_ATTEMPTS}})
            payout.transition_to(Payout.STATUS_PENDING)
            payout.save()
            should_retry = True

    if should_retry:
        try:
            delay = 2 ** self.request.retries * 10
            logger.info('Scheduling retry',
                        extra={'context': {'payout_id': payout_id,
                                           'countdown_seconds': delay}})
            self.retry(countdown=delay)
        except MaxRetriesExceededError:
            logger.error('Max retries exceeded — failing payout',
                         extra={'context': {'payout_id': payout_id,
                                            'max_attempts': MAX_PAYOUT_ATTEMPTS}})
            with transaction.atomic():
                payout = Payout.objects.select_for_update().get(id=payout_id)
                if payout.status == Payout.STATUS_PENDING:
                    payout.transition_to(Payout.STATUS_PROCESSING)
                    _fail_payout(payout, reason='Max retry attempts exceeded')


@shared_task
def retry_stuck_payouts():
    cutoff = timezone.now() - timedelta(seconds=30)
    logger.info('Scanning for stuck payouts',
                extra={'context': {'cutoff': cutoff.isoformat()}})

    with transaction.atomic():
        stuck_ids = list(
            Payout.objects
            .select_for_update(skip_locked=True)
            .filter(status=Payout.STATUS_PROCESSING, processing_started_at__lt=cutoff)
            .values_list('id', flat=True)
        )

    logger.info('Stuck payouts found',
                extra={'context': {'count': len(stuck_ids),
                                   'payout_ids': [str(i) for i in stuck_ids]}})

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
                logger.debug('Stuck payout no longer in PROCESSING (race)',
                             extra={'context': {'payout_id': str(payout_id)}})
                continue

            if payout.attempt_count < MAX_PAYOUT_ATTEMPTS:
                logger.info('Re-queuing stuck payout',
                            extra={'context': {'payout_id': str(payout_id),
                                               'attempt_count': payout.attempt_count}})
                payout.transition_to(Payout.STATUS_PENDING)
                payout.save()
                retry_ids.append(str(payout_id))
            else:
                logger.error('Stuck payout exceeded max attempts',
                             extra={'context': {'payout_id': str(payout_id),
                                                'attempt_count': payout.attempt_count}})
                _fail_payout(payout, reason='Max retry attempts exceeded')

    for payout_id in retry_ids:
        process_payout.delay(payout_id)

    logger.info('retry_stuck_payouts complete',
                extra={'context': {'requeued': len(retry_ids)}})


@shared_task
def cleanup_expired_idempotency_keys():
    logger.info('Cleaning up expired idempotency keys')
    deleted_count, _ = IdempotencyKey.objects.filter(expires_at__lt=timezone.now()).delete()
    logger.info('Idempotency key cleanup complete',
                extra={'context': {'deleted_count': deleted_count}})
    return deleted_count


def _fail_payout(payout, reason=''):
    logger.warning('Failing payout',
                   extra={'context': {'payout_id': str(payout.id),
                                      'merchant_id': str(payout.merchant_id),
                                      'amount_paise': payout.amount_paise,
                                      'reason': reason}})
    payout.transition_to(Payout.STATUS_FAILED)
    payout.failure_reason = reason
    payout.save()

    held_entry = LedgerEntry.objects.filter(
        payout=payout, entry_type='DEBIT', status='HELD'
    ).first()

    if held_entry is None:
        logger.error('No HELD ledger entry found — reversal skipped',
                     extra={'context': {'payout_id': str(payout.id)}})
        return

    reversal = LedgerEntry.objects.create(
        merchant=payout.merchant,
        entry_type='CREDIT',
        amount_paise=payout.amount_paise,
        status='SETTLED',
        description=f'Reversal for failed payout {payout.id}',
        payout=payout,
    )
    held_entry.status = 'SETTLED'
    held_entry.save()

    logger.info('Payout status → FAILED, reversal credit created',
                extra={'context': {'payout_id': str(payout.id),
                                   'reversal_entry_id': str(reversal.id),
                                   'amount_paise': payout.amount_paise,
                                   'reason': reason}})


def _simulate_bank_api():
    roll = random.random()
    if roll < 0.70:
        return 'success'
    elif roll < 0.90:
        return 'failure'
    else:
        time.sleep(0.1)
        return 'hang'
