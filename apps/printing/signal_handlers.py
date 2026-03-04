"""
출력 관리 시그널 핸들러

waves.signals.order_inspected 시그널을 받아 송장 출력을 트리거합니다.
"""
import logging

logger = logging.getLogger(__name__)


def handle_order_inspected(sender, **kwargs):
    """검수 완료 → 송장 출력 트리거"""
    from .services import PrintService

    order = kwargs.get('order')
    user = kwargs.get('user')

    if not order:
        return

    try:
        PrintService.trigger_print(order=order, performed_by=user)
    except Exception:
        logger.exception(
            'Failed to trigger print for order %s',
            order.wms_order_id,
        )
