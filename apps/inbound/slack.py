"""
입고 관리 Slack 알림 모듈
"""
import logging
import threading

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def _extract_order_data(order):
    """InboundOrder에서 슬랙 알림용 데이터를 추출한다."""
    try:
        items = list(order.items.select_related('product').all())
        item_lines = []
        total_qty = 0
        for item in items:
            item_lines.append(
                f'• {item.product.name} ({item.product.barcode}) — {item.expected_qty:,}개'
            )
            total_qty += item.expected_qty

        return {
            'inbound_id': order.inbound_id,
            'client_name': order.client.company_name,
            'brand_name': order.brand.name if order.brand else '-',
            'status': order.get_status_display(),
            'expected_date': order.expected_date.strftime('%Y-%m-%d'),
            'item_lines': item_lines,
            'item_count': len(items),
            'total_qty': total_qty,
            'notes': order.notes or '',
            'created_by': order.created_by.name if order.created_by else '-',
            'created_at': timezone.localtime(order.created_at).strftime('%Y-%m-%d %H:%M'),
        }
    except Exception:
        logger.exception('입고 Slack 데이터 추출 실패')
        return None


def _send_slack(data):
    """슬랙 웹훅 발송"""
    webhook_url = (
        getattr(settings, 'SLACK_WEBHOOK_INBOUND', '')
        or getattr(settings, 'SLACK_WEBHOOK_URL', '')
    )
    if not webhook_url:
        return

    items_text = '\n'.join(data['item_lines'][:10])
    if len(data['item_lines']) > 10:
        items_text += f'\n... 외 {len(data["item_lines"]) - 10}건'

    blocks = [
        {
            'type': 'header',
            'text': {
                'type': 'plain_text',
                'text': f'📦 입고 등록 — {data["inbound_id"]}',
            },
        },
        {
            'type': 'section',
            'fields': [
                {'type': 'mrkdwn', 'text': f'*거래처:*  {data["client_name"]}'},
                {'type': 'mrkdwn', 'text': f'*브랜드:*  {data["brand_name"]}'},
                {'type': 'mrkdwn', 'text': f'*입고예정일:*  {data["expected_date"]}'},
                {'type': 'mrkdwn', 'text': f'*품목수:*  {data["item_count"]}건 / 총 {data["total_qty"]:,}개'},
                {'type': 'mrkdwn', 'text': f'*등록자:*  {data["created_by"]}'},
                {'type': 'mrkdwn', 'text': f'*등록일시:*  {data["created_at"]}'},
            ],
        },
        {'type': 'divider'},
        {
            'type': 'section',
            'text': {
                'type': 'mrkdwn',
                'text': f'*품목 상세:*\n{items_text}',
            },
        },
    ]

    if data['notes']:
        blocks.append({
            'type': 'section',
            'text': {'type': 'mrkdwn', 'text': f'*비고:*  {data["notes"]}'},
        })

    payload = {'blocks': blocks}

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code != 200:
            logger.warning('입고 Slack 발송 실패: %s %s', resp.status_code, resp.text)
    except Exception:
        logger.exception('입고 Slack 발송 에러')


def send_inbound_order_notification(order):
    """입고 등록 슬랙 알림 (동기)"""
    data = _extract_order_data(order)
    if data:
        _send_slack(data)


def send_inbound_order_notification_async(order):
    """입고 등록 슬랙 알림 (비동기 — 메인 스레드에서 데이터 추출 후 전송)"""
    data = _extract_order_data(order)
    if data:
        thread = threading.Thread(target=_send_slack, args=(data,), daemon=True)
        thread.start()
