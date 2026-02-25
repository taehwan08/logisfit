"""
입고 관리 Slack 알림 모듈

입고 등록 시 슬랙 채널에 알림을 전송합니다.
"""
import logging
import threading

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def _extract_inbound_data(record):
    """입고 기록에서 슬랙 알림용 데이터를 추출한다.

    메인 스레드에서 호출하여 DB 접근을 안전하게 수행한다.

    Args:
        record: InboundRecord 인스턴스 (select_related('product', 'registered_by') 권장)

    Returns:
        dict 또는 None
    """
    try:
        return {
            'product_name': record.product.name,
            'product_barcode': record.product.barcode,
            'quantity': record.quantity,
            'expiry_date': record.expiry_date or '-',
            'lot_number': record.lot_number or '-',
            'memo': record.memo or '',
            'registered_by': record.registered_by.name if record.registered_by else '-',
            'created_at': timezone.localtime(record.created_at).strftime('%Y-%m-%d %H:%M'),
        }
    except Exception as e:
        logger.warning('입고 슬랙 데이터 추출 실패: %s', e)
        return None


def _send_inbound_slack(data):
    """슬랙으로 입고 알림을 전송한다.

    백그라운드 스레드에서 호출 가능 (DB 접근 없음).

    Args:
        data: _extract_inbound_data()에서 반환된 dict
    """
    webhook_url = getattr(settings, 'SLACK_WEBHOOK_URL', '')
    if not webhook_url:
        return

    site_url = getattr(settings, 'SITE_URL', '').rstrip('/')

    info_parts = [
        f'*상품명:*  {data["product_name"]}',
        f'*바코드:*  {data["product_barcode"]}',
        f'*입고수량:*  {data["quantity"]:,}',
        f'*유통기한:*  {data["expiry_date"]}',
        f'*로트번호:*  {data["lot_number"]}',
    ]
    if data['memo']:
        info_parts.append(f'*메모:*  {data["memo"]}')

    blocks = [
        {
            'type': 'header',
            'text': {
                'type': 'plain_text',
                'text': '입고 등록',
                'emoji': True,
            },
        },
        {
            'type': 'section',
            'text': {
                'type': 'mrkdwn',
                'text': '\n'.join(info_parts),
            },
        },
        {
            'type': 'context',
            'elements': [
                {
                    'type': 'mrkdwn',
                    'text': f'등록자: {data["registered_by"]} | 등록일시: {data["created_at"]}',
                },
            ],
        },
        {
            'type': 'actions',
            'elements': [
                {
                    'type': 'button',
                    'text': {'type': 'plain_text', 'text': '입고관리 열기', 'emoji': True},
                    'url': f'{site_url}/inventory/inbound/',
                    'action_id': 'open_inbound_page',
                },
            ],
        },
    ]

    payload = {
        'text': f'입고 등록: {data["product_name"]} ({data["quantity"]:,}개)',
        'blocks': blocks,
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code != 200:
            logger.warning(
                'Slack 입고 알림 실패: status=%s body=%s',
                resp.status_code,
                resp.text[:200],
            )
    except requests.RequestException as e:
        logger.warning('Slack 입고 알림 중 오류: %s', e)


def send_inbound_notification(record):
    """입고 등록 시 슬랙 알림을 동기적으로 전송한다.

    Args:
        record: InboundRecord 인스턴스
    """
    data = _extract_inbound_data(record)
    if data:
        _send_inbound_slack(data)


def send_inbound_notification_async(record):
    """입고 등록 시 슬랙 알림을 비동기로 전송한다.

    메인 스레드에서 데이터를 추출하고, 백그라운드 스레드에서 전송한다.

    Args:
        record: InboundRecord 인스턴스
    """
    data = _extract_inbound_data(record)
    if not data:
        return

    thread = threading.Thread(target=_send_inbound_slack, args=(data,), daemon=True)
    thread.start()
