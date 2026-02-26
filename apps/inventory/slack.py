"""
입고 관리 Slack 알림 모듈

입고 등록 시 슬랙 채널에 알림을 전송합니다.
슬랙 인터랙티브 버튼("전산 등록 완료")을 통해 상태를 변경합니다.
"""
import json
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
        # 모든 이미지 URL 추출
        image_urls = []
        for img in record.images.all():
            try:
                url = img.image.url
                if url:
                    image_urls.append(url)
            except Exception:
                pass

        return {
            'record_id': record.pk,
            'product_name': record.product.name,
            'product_barcode': record.product.barcode,
            'quantity': record.quantity,
            'expiry_date': record.expiry_date or '-',
            'lot_number': record.lot_number or '-',
            'memo': record.memo or '',
            'registered_by': record.registered_by.name if record.registered_by else '-',
            'created_at': timezone.localtime(record.created_at).strftime('%Y-%m-%d %H:%M'),
            'image_urls': image_urls,
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
    webhook_url = getattr(settings, 'SLACK_WEBHOOK_INBOUND', '') or getattr(settings, 'SLACK_WEBHOOK_URL', '')
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
    ]

    # 이미지가 있으면 image 블록 추가 (public HTTPS URL 필요)
    for idx, url in enumerate(data.get('image_urls', [])):
        if url and url.startswith('https://'):
            blocks.append({
                'type': 'image',
                'image_url': url,
                'alt_text': f'{data["product_name"]} 입고 이미지 {idx + 1}',
            })

    blocks += [
        {'type': 'divider'},
        {
            'type': 'actions',
            'elements': [
                {
                    'type': 'button',
                    'text': {'type': 'plain_text', 'text': '전산 등록 완료', 'emoji': True},
                    'style': 'primary',
                    'action_id': 'complete_inbound',
                    'value': json.dumps({
                        'record_id': data['record_id'],
                        'action': 'complete',
                    }),
                },
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


# ============================================================================
# Slack Interactive Action 처리
# ============================================================================

def process_inbound_slack_action(payload):
    """슬랙 인터랙티브 버튼 클릭을 처리한다 (입고 전산 등록 완료).

    Args:
        payload: 슬랙에서 전달한 interaction payload (dict)

    Returns:
        dict 또는 None
    """
    from .models import InboundRecord

    actions = payload.get('actions', [])
    if not actions:
        return None

    action = actions[0]
    action_id = action.get('action_id', '')
    response_url = payload.get('response_url', '')

    # URL 링크 버튼은 별도 처리 불필요
    if action_id.startswith('open_'):
        return None

    if action_id != 'complete_inbound':
        return None

    try:
        value = json.loads(action.get('value', '{}'))
    except (json.JSONDecodeError, TypeError):
        _send_response_url(response_url, {
            'replace_original': False,
            'response_type': 'ephemeral',
            'text': ':warning: 잘못된 요청입니다.',
        })
        return None

    record_id = value.get('record_id')
    if not record_id:
        _send_response_url(response_url, {
            'replace_original': False,
            'response_type': 'ephemeral',
            'text': ':warning: 입고 기록 ID를 찾을 수 없습니다.',
        })
        return None

    try:
        record = InboundRecord.objects.select_related('product', 'registered_by').get(pk=record_id)
    except InboundRecord.DoesNotExist:
        _send_response_url(response_url, {
            'replace_original': False,
            'response_type': 'ephemeral',
            'text': ':warning: 해당 입고 기록을 찾을 수 없습니다.',
        })
        return None

    # 이미 처리된 기록
    if record.status == 'completed':
        completed_at = ''
        if record.completed_at:
            completed_at = timezone.localtime(record.completed_at).strftime('%Y-%m-%d %H:%M')
        _send_response_url(response_url, {
            'replace_original': False,
            'response_type': 'ephemeral',
            'text': f':information_source: 이미 전산 등록 완료된 기록입니다. (처리일시: {completed_at})',
        })
        return None

    # 슬랙에서 누른 사람 정보
    slack_user = payload.get('user', {})
    slack_username = slack_user.get('name', '알 수 없음')

    # 상태 변경
    now = timezone.now()
    record.status = 'completed'
    record.completed_at = now
    record.save(update_fields=['status', 'completed_at', 'updated_at'])

    now_str = timezone.localtime(now).strftime('%Y-%m-%d %H:%M')

    # 원본 메시지를 완료 상태로 업데이트
    info_parts = [
        f'*상품명:*  {record.product.name}',
        f'*바코드:*  {record.product.barcode}',
        f'*입고수량:*  {record.quantity:,}',
        f'*유통기한:*  {record.expiry_date or "-"}',
        f'*로트번호:*  {record.lot_number or "-"}',
    ]

    registered_by = record.registered_by.name if record.registered_by else '-'
    created_at = timezone.localtime(record.created_at).strftime('%Y-%m-%d %H:%M')

    blocks = [
        {
            'type': 'header',
            'text': {
                'type': 'plain_text',
                'text': '입고 등록 - 전산등록완료',
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
            'type': 'section',
            'text': {
                'type': 'mrkdwn',
                'text': ':white_check_mark: *전산 등록 완료*',
            },
        },
        {
            'type': 'context',
            'elements': [
                {
                    'type': 'mrkdwn',
                    'text': f'등록자: {registered_by} | 등록일시: {created_at} | 처리자: @{slack_username} | 처리일시: {now_str}',
                },
            ],
        },
    ]

    updated_msg = {
        'replace_original': True,
        'text': f'입고 전산등록완료: {record.product.name} ({record.quantity:,}개)',
        'blocks': blocks,
    }

    _send_response_url(response_url, updated_msg)
    return None


def _send_response_url(response_url, message):
    """Slack response_url로 메시지를 전송하여 원본 메시지를 업데이트한다."""
    if not response_url:
        logger.warning('response_url이 없어 슬랙 메시지를 업데이트할 수 없습니다.')
        return

    try:
        resp = requests.post(response_url, json=message, timeout=10)
        if resp.status_code != 200:
            logger.warning(
                'Slack response_url 응답 실패: status=%s body=%s',
                resp.status_code,
                resp.text[:200],
            )
    except requests.RequestException as e:
        logger.warning('Slack response_url 전송 중 오류: %s', e)
