"""
재고 관련 예외
"""


class InsufficientStockError(Exception):
    """재고 부족 예외

    가용재고, 실물재고, 할당재고 등이 요청 수량보다 부족할 때 발생합니다.
    """

    def __init__(self, product, requested, available, detail=''):
        self.product = product
        self.requested = requested
        self.available = available
        self.detail = detail
        msg = (
            f'재고 부족: {product} — '
            f'요청 {requested}, 가용 {available}'
        )
        if detail:
            msg += f' ({detail})'
        super().__init__(msg)
