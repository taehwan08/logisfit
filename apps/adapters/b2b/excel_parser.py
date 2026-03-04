"""
B2B 엑셀 → 표준 주문 포맷 변환

거래처가 업로드한 B2B 발주 엑셀 파일을 파싱하여
WMS 표준 주문 포맷으로 변환합니다.
"""
import logging

import openpyxl

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ['발주번호', '상품코드', '수량', '수취인명', '연락처', '배송지']

OPTIONAL_COLUMNS = ['상품명', '우편번호', '배송메모']


class B2BExcelParser:
    """B2B 엑셀 파서"""

    def parse(self, file):
        """엑셀 파일 → 표준 주문 포맷 리스트 변환

        같은 발주번호의 행들을 하나의 주문으로 그룹핑합니다.

        Args:
            file: 업로드된 엑셀 파일 (InMemoryUploadedFile 등)

        Returns:
            list[dict]: 표준 주문 포맷 리스트

        Raises:
            ValueError: 필수 컬럼 누락 등 파싱 오류
        """
        try:
            wb = openpyxl.load_workbook(file, read_only=True, data_only=True)
        except Exception as e:
            raise ValueError(f'엑셀 파일을 읽을 수 없습니다: {e}')

        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))

        if len(rows) < 2:
            raise ValueError('데이터가 없습니다. 헤더와 1행 이상의 데이터가 필요합니다.')

        # 헤더 → 컬럼 인덱스 매핑
        header = [str(c).strip() if c else '' for c in rows[0]]
        col_map = {name: idx for idx, name in enumerate(header)}

        # 필수 컬럼 확인
        missing = [c for c in REQUIRED_COLUMNS if c not in col_map]
        if missing:
            raise ValueError(f"필수 컬럼 누락: {', '.join(missing)}")

        # 행 파싱 → 발주번호별 그룹핑
        orders_map = {}
        for row_idx, row in enumerate(rows[1:], start=2):
            order_id = self._cell(row, col_map, '발주번호')
            if not order_id:
                continue  # 빈 행 스킵

            sku = self._cell(row, col_map, '상품코드')
            qty = self._cell(row, col_map, '수량')

            if not sku or not qty:
                logger.warning('행 %d: 상품코드 또는 수량 누락, 스킵', row_idx)
                continue

            try:
                qty = int(qty)
            except (ValueError, TypeError):
                raise ValueError(f'행 {row_idx}: 수량이 숫자가 아닙니다: {qty}')

            if qty <= 0:
                raise ValueError(f'행 {row_idx}: 수량은 1 이상이어야 합니다: {qty}')

            if order_id not in orders_map:
                orders_map[order_id] = {
                    'source_order_id': str(order_id),
                    'recipient_name': self._cell(row, col_map, '수취인명', ''),
                    'recipient_phone': self._cell(row, col_map, '연락처', ''),
                    'recipient_address': self._cell(row, col_map, '배송지', ''),
                    'recipient_zip': self._cell(row, col_map, '우편번호', ''),
                    'shipping_memo': self._cell(row, col_map, '배송메모', ''),
                    'items': [],
                }

            orders_map[order_id]['items'].append({
                'sku': str(sku),
                'qty': qty,
                'source_item_id': '',
            })

        wb.close()

        if not orders_map:
            raise ValueError('유효한 주문 데이터가 없습니다.')

        return list(orders_map.values())

    @staticmethod
    def _cell(row, col_map, column_name, default=None):
        """안전하게 셀 값 조회"""
        idx = col_map.get(column_name)
        if idx is None or idx >= len(row):
            return default
        val = row[idx]
        if val is None:
            return default
        return str(val).strip()
