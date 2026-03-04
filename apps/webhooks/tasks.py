"""
웹훅 관리 Celery 태스크
"""
from config.celery import app


@app.task(bind=True, max_retries=3, default_retry_delay=10)
def deliver_webhook(self, subscriber_id, event_type, payload):
    """웹훅 배달 (비동기, exponential backoff)"""
    from .services import deliver

    log = deliver(subscriber_id, event_type, payload)

    if log and not log.success and log.attempts <= self.max_retries:
        raise self.retry(
            countdown=10 * (2 ** (self.request.retries)),
            exc=Exception(log.error_message),
        )
