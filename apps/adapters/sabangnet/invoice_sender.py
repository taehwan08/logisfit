"""
사방넷 송장 역전송

출고 확정(ORDER_SHIPPED) 시 사방넷으로 송장 정보를 역전송합니다.
"""
import logging

from .client import SabangnetClient
from .mappers import map_carrier_code

logger = logging.getLogger(__name__)


class SabangnetInvoiceSender:
    """사방넷 송장 역전송"""

    def __init__(self):
        self.client = SabangnetClient()

    def send_invoice(self, order):
        """출고 확정된 주문의 송장 정보를 사방넷에 역전송

        Args:
            order: OutboundOrder 인스턴스 (SHIPPED 상태)

        Returns:
            bool: 전송 성공 여부
        """
        if order.source != 'SABANGNET':
            logger.debug(
                '사방넷 주문이 아닙니다: order=%s source=%s',
                order.wms_order_id, order.source,
            )
            return False

        tracking_number = order.tracking_number
        if not tracking_number:
            logger.warning(
                '송장번호 없음: order=%s', order.wms_order_id,
            )
            return False

        carrier_code = ''
        if order.carrier:
            carrier_code = map_carrier_code(order.carrier.name)

        success = self.client.register_invoice(
            source_order_id=order.source_order_id,
            tracking_number=tracking_number,
            carrier_code=carrier_code,
        )

        if success:
            logger.info(
                '사방넷 송장 역전송 성공: order=%s tracking=%s',
                order.wms_order_id, tracking_number,
            )
        else:
            logger.error(
                '사방넷 송장 역전송 실패: order=%s', order.wms_order_id,
            )

        return success
