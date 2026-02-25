"""
검수 시스템 Slack 알림 모듈

배치(파일) 단위 검수 완료 시 슬랙 알림을 전송합니다.
"""
import logging

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def send_batch_complete_notification(batch):
    """배치(파일)의 모든 송장 검수가 완료되었을 때 슬랙 알림을 전송한다.

    Args:
        batch: UploadBatch 인스턴스
    """
    webhook_url = getattr(settings, 'SLACK_WEBHOOK_INSPECTION', '') or getattr(settings, 'SLACK_WEBHOOK_URL', '')
    if not webhook_url:
        return

    site_url = getattr(settings, 'SITE_URL', '').rstrip('/')
    now = timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M')

    # 배치 통계
    orders = batch.orders.all()
    total_orders = orders.count()
    total_products = sum(
        p.quantity for o in orders for p in o.products.all()
    )

    # 소요 시간 계산 (첫 송장 스캔 완료 ~ 마지막 송장 스캔 완료)
    completed_orders = orders.filter(completed_at__isnull=False).order_by('completed_at')
    first_completed = completed_orders.first()
    last_completed = completed_orders.last()
    duration_text = ''
    start_time_text = ''
    end_time_text = ''
    if first_completed and last_completed and first_completed.completed_at and last_completed.completed_at:
        start_time_text = timezone.localtime(first_completed.completed_at).strftime('%H:%M')
        end_time_text = timezone.localtime(last_completed.completed_at).strftime('%H:%M')
        delta = last_completed.completed_at - first_completed.completed_at
        total_seconds = max(0, int(delta.total_seconds()))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            duration_text = f'{hours}시간 {minutes}분'
        elif minutes > 0:
            duration_text = f'{minutes}분 {seconds}초'
        else:
            duration_text = f'{seconds}초'

    # 배치 정보 텍스트
    info_parts = []
    if batch.print_order:
        info_parts.append(f'*출력차수:*  {batch.print_order}')
    if batch.delivery_memo:
        info_parts.append(f'*배송메모:*  {batch.delivery_memo}')
    info_parts.append(f'*송장 수:*  {total_orders}건')
    info_parts.append(f'*상품 수:*  {total_products}개')
    if duration_text:
        info_parts.append(f'*소요시간:*  {duration_text} ({start_time_text} ~ {end_time_text})')

    blocks = [
        {
            'type': 'header',
            'text': {
                'type': 'plain_text',
                'text': '검수 완료',
                'emoji': True,
            },
        },
        {
            'type': 'section',
            'text': {
                'type': 'mrkdwn',
                'text': f':package: *{batch.file_name}*',
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
                    'text': (
                        f'업로드: {timezone.localtime(batch.uploaded_at).strftime("%Y-%m-%d %H:%M")}'
                        f' | 완료: {now}'
                        f'{" | 업로드자: " + batch.uploaded_by if batch.uploaded_by else ""}'
                    ),
                },
            ],
        },
        {
            'type': 'actions',
            'elements': [
                {
                    'type': 'button',
                    'text': {'type': 'plain_text', 'text': '관리 페이지 열기', 'emoji': True},
                    'url': f'{site_url}/inspection/office/',
                    'action_id': 'open_office_page',
                },
            ],
        },
    ]

    payload = {
        'text': f'검수 완료: {batch.file_name} ({total_orders}건)',
        'blocks': blocks,
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code != 200:
            logger.warning(
                'Slack 배치 완료 알림 실패: status=%s body=%s',
                resp.status_code,
                resp.text[:200],
            )
    except requests.RequestException as e:
        logger.warning('Slack 배치 완료 알림 중 오류: %s', e)
