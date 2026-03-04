"""
사방넷 데이터 포맷 → WMS 표준 포맷 변환

사방넷 API에서 수신한 주문 데이터를 OrderReceiveSerializer가
수용하는 표준 포맷으로 변환합니다.
"""


def map_order(raw_order, client_id):
    """사방넷 주문 1건 → 표준 주문 포맷 변환

    Args:
        raw_order: 사방넷 API 응답의 주문 dict
        client_id: WMS 거래처 ID

    Returns:
        dict: OrderReceiveSerializer 호환 포맷

    사방넷 필드 매핑 (TODO: 실제 필드명 확인 후 수정):
        order_id      → source_order_id
        buyer_name    → recipient_name
        buyer_phone   → recipient_phone
        buyer_address → recipient_address
        buyer_zip     → recipient_zip
        memo          → shipping_memo
        order_date    → ordered_at
        items[].sku   → items[].sku
        items[].qty   → items[].qty
        items[].item_id → items[].source_item_id
    """
    # TODO: 실제 사방넷 API 응답 필드에 맞게 매핑
    return {
        'source': 'SABANGNET',
        'source_order_id': str(raw_order.get('order_id', '')),
        'client_id': client_id,
        'order_type': 'B2C',
        'ordered_at': raw_order.get('order_date', ''),
        'shipping': {
            'recipient_name': raw_order.get('buyer_name', ''),
            'recipient_phone': raw_order.get('buyer_phone', ''),
            'recipient_address': raw_order.get('buyer_address', ''),
            'recipient_zip': raw_order.get('buyer_zip', ''),
            'shipping_memo': raw_order.get('memo', ''),
        },
        'items': [
            {
                'sku': item.get('sku', ''),
                'qty': int(item.get('qty', 1)),
                'source_item_id': str(item.get('item_id', '')),
            }
            for item in raw_order.get('items', [])
        ],
    }


def map_carrier_code(sabangnet_carrier):
    """사방넷 택배사 코드 → WMS 택배사 코드 변환

    TODO: 실제 사방넷 택배사 코드 매핑 테이블 확인 후 완성
    """
    mapping = {
        '대한통운': 'CJ',
        'CJ대한통운': 'CJ',
        '한진택배': 'HANJIN',
        '롯데택배': 'LOTTE',
        '로젠택배': 'LOGEN',
        '우체국택배': 'EPOST',
    }
    return mapping.get(sabangnet_carrier, sabangnet_carrier)
