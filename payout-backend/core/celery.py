import os
from celery import Celery
from datetime import timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
app = Celery('core')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'retry-stuck-payouts': {
        'task': 'payouts.tasks.retry_stuck_payouts',
        'schedule': timedelta(seconds=30),
    },
    'cleanup-expired-idempotency-keys': {
        'task': 'payouts.tasks.cleanup_expired_idempotency_keys',
        'schedule': timedelta(hours=1),
    },
}