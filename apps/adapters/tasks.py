"""
외부 연동 어댑터 Celery 태스크
"""
import logging

from config.celery import app

logger = logging.getLogger(__name__)


@app.task(bind=True, max_retries=2, default_retry_delay=60)
def poll_sabangnet_orders(self):
    """사방넷 주문 수집 (periodic task)"""
    from .sabangnet.order_poller import SabangnetOrderPoller

    try:
        poller = SabangnetOrderPoller()
        result = poller.poll_orders()
        logger.info('poll_sabangnet_orders 결과: %s', result)
        return result
    except Exception as exc:
        from apps.notifications.tasks import send_api_error_alert_task
        send_api_error_alert_task.delay('사방넷', str(exc))
        raise


@app.task(bind=True, max_retries=2, default_retry_delay=30)
def send_sabangnet_invoice(self, wms_order_id):
    """사방넷 송장 역전송"""
    from apps.waves.models import OutboundOrder
    from .sabangnet.invoice_sender import SabangnetInvoiceSender

    try:
        order = OutboundOrder.objects.select_related('carrier').get(
            wms_order_id=wms_order_id,
        )
    except OutboundOrder.DoesNotExist:
        logger.error('주문을 찾을 수 없습니다: %s', wms_order_id)
        return

    sender = SabangnetInvoiceSender()
    sender.send_invoice(order)
