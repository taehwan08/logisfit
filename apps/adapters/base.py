"""
어댑터 기본 클래스

모든 외부 연동 어댑터는 이 클래스를 상속합니다.
"""


class BaseAdapter:
    """어댑터 기본 클래스"""

    def fetch_orders(self):
        """외부 시스템에서 신규 주문을 조회합니다."""
        raise NotImplementedError

    def send_invoice(self, order_id, tracking_number, carrier_code):
        """외부 시스템에 송장 정보를 역전송합니다."""
        raise NotImplementedError
