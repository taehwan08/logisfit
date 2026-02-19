"""
출고 관리 Slack 알림 모듈

주문 등록(단건/벌크) 시 슬랙 알림을 전송합니다.
벌크 등록은 건별이 아닌 1건의 요약 메시지만 발송하여 채널 도배를 방지합니다.
"""
import logging

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

PLATFORM_LABELS = dict([
    ('coupang', '쿠팡'), ('kurly', '컬리'), ('oliveyoung', '올리브영'),
    ('smartstore', '스마트스토어'), ('offline', '오프라인마트'),
    ('export', '해외수출'), ('other', '기타'),
])


def send_order_created_notification(order):
    """단건 주문 등록 시 슬랙 알림을 전송한다.

    Args:
        order: FulfillmentOrder 인스턴스
    """
    webhook_url = getattr(settings, 'SLACK_WEBHOOK_URL', '')
    if not webhook_url:
        return

    site_url = getattr(settings, 'SITE_URL', '').rstrip('/')
    now = timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M')
    platform_label = PLATFORM_LABELS.get(order.platform, order.platform)
    brand_name = order.brand.name if order.brand else '-'
    created_by_name = order.created_by.name if order.created_by else '-'

    info_parts = [
        f'*거래처:*  {order.client.company_name}',
        f'*브랜드:*  {brand_name}',
        f'*플랫폼:*  {platform_label}',
        f'*발주번호:*  {order.order_number}',
        f'*상품명:*  {order.product_name}',
        f'*발주수량:*  {order.order_quantity:,}',
    ]
    if order.confirmed_quantity:
        info_parts.append(f'*확정수량:*  {order.confirmed_quantity:,}')

    blocks = [
        {
            'type': 'header',
            'text': {
                'type': 'plain_text',
                'text': '주문 등록',
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
                    'text': f'등록자: {created_by_name} | 등록일시: {now}',
                },
            ],
        },
        {
            'type': 'actions',
            'elements': [
                {
                    'type': 'button',
                    'text': {'type': 'plain_text', 'text': '출고 현황 열기', 'emoji': True},
                    'url': f'{site_url}/fulfillment/',
                    'action_id': 'open_fulfillment_page',
                },
            ],
        },
    ]

    payload = {
        'text': f'주문 등록: {order.client.company_name} / {order.product_name} ({order.order_quantity:,}개)',
        'blocks': blocks,
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code != 200:
            logger.warning(
                'Slack 주문 등록 알림 실패: status=%s body=%s',
                resp.status_code,
                resp.text[:200],
            )
    except requests.RequestException as e:
        logger.warning('Slack 주문 등록 알림 중 오류: %s', e)


def send_bulk_orders_notification(client, brand, platform, created_count, error_count, user):
    """벌크 붙여넣기 주문 등록 시 요약 슬랙 알림을 전송한다.

    건별 메시지 대신 1건의 요약 메시지만 발송한다.

    Args:
        client: Client 인스턴스
        brand: Brand 인스턴스 (없으면 None)
        platform: 플랫폼 코드 (str)
        created_count: 등록 성공 건수
        error_count: 에러 건수
        user: 등록자 User 인스턴스
    """
    webhook_url = getattr(settings, 'SLACK_WEBHOOK_URL', '')
    if not webhook_url:
        return

    site_url = getattr(settings, 'SITE_URL', '').rstrip('/')
    now = timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M')
    platform_label = PLATFORM_LABELS.get(platform, platform)
    brand_name = brand.name if brand else '-'
    user_name = user.name if user else '-'

    info_parts = [
        f'*거래처:*  {client.company_name}',
        f'*브랜드:*  {brand_name}',
        f'*플랫폼:*  {platform_label}',
        f'*등록 건수:*  {created_count:,}건',
    ]
    if error_count > 0:
        info_parts.append(f'*에러 건수:*  {error_count}건')

    blocks = [
        {
            'type': 'header',
            'text': {
                'type': 'plain_text',
                'text': '주문 일괄 등록',
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
                    'text': f'등록자: {user_name} | 등록일시: {now}',
                },
            ],
        },
        {
            'type': 'actions',
            'elements': [
                {
                    'type': 'button',
                    'text': {'type': 'plain_text', 'text': '출고 현황 열기', 'emoji': True},
                    'url': f'{site_url}/fulfillment/',
                    'action_id': 'open_fulfillment_page',
                },
            ],
        },
    ]

    summary_text = f'주문 일괄 등록: {client.company_name} / {platform_label} ({created_count:,}건)'
    if error_count > 0:
        summary_text += f' [에러 {error_count}건]'

    payload = {
        'text': summary_text,
        'blocks': blocks,
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code != 200:
            logger.warning(
                'Slack 벌크 주문 등록 알림 실패: status=%s body=%s',
                resp.status_code,
                resp.text[:200],
            )
    except requests.RequestException as e:
        logger.warning('Slack 벌크 주문 등록 알림 중 오류: %s', e)
