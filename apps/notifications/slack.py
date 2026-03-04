"""
운영 알림 Slack 모듈

안전재고, 웨이브 지연, 주문 보류, 프린터 오류, API 연동 오류 등
운영 이벤트 발생 시 Slack Block Kit 메시지를 전송합니다.
"""
import logging

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def _get_webhook_url():
    return (
        getattr(settings, 'SLACK_WEBHOOK_ALERTS', '')
        or getattr(settings, 'SLACK_WEBHOOK_URL', '')
    )


def _post_slack(payload):
    webhook_url = _get_webhook_url()
    if not webhook_url:
        return
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code != 200:
            logger.warning(
                'Slack 알림 발송 실패: status=%s body=%s',
                resp.status_code, resp.text[:200],
            )
    except requests.RequestException as e:
        logger.warning('Slack 알림 중 오류: %s', e)


def send_safety_stock_alert(alerts):
    """안전재고 미달 알림

    Args:
        alerts: check_safety_stock_alerts() 반환값 리스트
    """
    if not alerts:
        return

    now = timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M')
    lines = []
    for a in alerts[:20]:  # 최대 20건
        ss = a['safety_stock']
        lines.append(
            f"• *{ss.client.company_name}* | {ss.product.name}"
            f" — 현재 {a['total_on_hand']:,}개 / 안전재고 {ss.min_qty:,}개"
            f" (부족 {a['shortage']:,}개)"
        )

    blocks = [
        {
            'type': 'header',
            'text': {
                'type': 'plain_text',
                'text': f'안전재고 미달 알림 ({len(alerts)}건)',
                'emoji': True,
            },
        },
        {
            'type': 'section',
            'text': {
                'type': 'mrkdwn',
                'text': '\n'.join(lines),
            },
        },
        {
            'type': 'context',
            'elements': [
                {'type': 'mrkdwn', 'text': f'확인 시각: {now}'},
            ],
        },
    ]

    if len(alerts) > 20:
        blocks.insert(2, {
            'type': 'section',
            'text': {
                'type': 'mrkdwn',
                'text': f'_...외 {len(alerts) - 20}건 더 있습니다._',
            },
        })

    _post_slack({
        'text': f'안전재고 미달 알림: {len(alerts)}건',
        'blocks': blocks,
    })


def send_wave_delay_alert(wave):
    """웨이브 처리 지연 알림

    Args:
        wave: Wave 인스턴스 (2시간 이상 미완료)
    """
    now = timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M')
    created = timezone.localtime(wave.created_at).strftime('%H:%M')
    elapsed = timezone.now() - wave.created_at
    hours = elapsed.total_seconds() / 3600

    blocks = [
        {
            'type': 'header',
            'text': {
                'type': 'plain_text',
                'text': '웨이브 처리 지연 알림',
                'emoji': True,
            },
        },
        {
            'type': 'section',
            'text': {
                'type': 'mrkdwn',
                'text': (
                    f'*웨이브:*  {wave.wave_id}\n'
                    f'*상태:*  {wave.get_status_display()}\n'
                    f'*생성 시각:*  {created}\n'
                    f'*경과 시간:*  {hours:.1f}시간\n'
                    f'*진행률:*  {wave.shipped_count}/{wave.total_orders}건 출고'
                ),
            },
        },
        {
            'type': 'context',
            'elements': [
                {'type': 'mrkdwn', 'text': f'확인 시각: {now}'},
            ],
        },
    ]

    _post_slack({
        'text': f'웨이브 처리 지연: {wave.wave_id} ({hours:.1f}시간 경과)',
        'blocks': blocks,
    })


def send_order_held_alert(order):
    """주문 보류 발생 알림

    Args:
        order: OutboundOrder 인스턴스 (HELD 상태)
    """
    now = timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M')
    client_name = order.client.company_name if order.client else '-'

    blocks = [
        {
            'type': 'header',
            'text': {
                'type': 'plain_text',
                'text': '주문 보류 발생',
                'emoji': True,
            },
        },
        {
            'type': 'section',
            'text': {
                'type': 'mrkdwn',
                'text': (
                    f'*주문번호:*  {order.wms_order_id}\n'
                    f'*거래처:*  {client_name}\n'
                    f'*수취인:*  {order.recipient_name}\n'
                    f'*보류사유:*  {order.hold_reason}'
                ),
            },
        },
        {
            'type': 'context',
            'elements': [
                {'type': 'mrkdwn', 'text': f'발생 시각: {now}'},
            ],
        },
    ]

    _post_slack({
        'text': f'주문 보류: {order.wms_order_id} ({client_name})',
        'blocks': blocks,
    })


def send_printer_error_alert(print_job):
    """프린터 오류 알림

    Args:
        print_job: PrintJob 인스턴스 (FAILED 상태)
    """
    now = timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M')
    order_id = print_job.order.wms_order_id if print_job.order else '-'
    printer_name = print_job.printer.name if print_job.printer else '-'

    blocks = [
        {
            'type': 'header',
            'text': {
                'type': 'plain_text',
                'text': '프린터 오류 알림',
                'emoji': True,
            },
        },
        {
            'type': 'section',
            'text': {
                'type': 'mrkdwn',
                'text': (
                    f'*주문번호:*  {order_id}\n'
                    f'*프린터:*  {printer_name}\n'
                    f'*시도 횟수:*  {print_job.attempts}회\n'
                    f'*오류 메시지:*  {print_job.error_message}'
                ),
            },
        },
        {
            'type': 'context',
            'elements': [
                {'type': 'mrkdwn', 'text': f'발생 시각: {now}'},
            ],
        },
    ]

    _post_slack({
        'text': f'프린터 오류: {order_id} ({printer_name})',
        'blocks': blocks,
    })


def send_api_error_alert(adapter_name, error_message):
    """API 연동 오류 알림

    Args:
        adapter_name: 어댑터 이름 (예: '사방넷')
        error_message: 오류 메시지
    """
    now = timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M')

    blocks = [
        {
            'type': 'header',
            'text': {
                'type': 'plain_text',
                'text': 'API 연동 오류 알림',
                'emoji': True,
            },
        },
        {
            'type': 'section',
            'text': {
                'type': 'mrkdwn',
                'text': (
                    f'*어댑터:*  {adapter_name}\n'
                    f'*오류:*  {error_message}'
                ),
            },
        },
        {
            'type': 'context',
            'elements': [
                {'type': 'mrkdwn', 'text': f'발생 시각: {now}'},
            ],
        },
    ]

    _post_slack({
        'text': f'API 연동 오류: {adapter_name} — {error_message}',
        'blocks': blocks,
    })
