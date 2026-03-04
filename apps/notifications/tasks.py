"""
알림 Celery 태스크

주기적 알림(안전재고, 웨이브 지연, 일일 출고 요약) 및
이벤트 기반 알림(주문 보류, 프린터 오류, API 오류) 태스크.
"""
import logging
from datetime import timedelta

from django.utils import timezone

from config.celery import app

logger = logging.getLogger(__name__)


@app.task(bind=True, ignore_result=True)
def check_safety_stock_task(self):
    """안전재고 미달 체크 (1시간 주기)"""
    from apps.inventory.models import check_safety_stock_alerts

    from .slack import send_safety_stock_alert

    alerts = check_safety_stock_alerts()
    if alerts:
        logger.info('안전재고 미달 %d건 발견', len(alerts))
        send_safety_stock_alert(alerts)
    return {'alert_count': len(alerts)}


@app.task(bind=True, ignore_result=True)
def check_wave_delays_task(self):
    """웨이브 처리 지연 체크 (30분 주기)

    생성 후 2시간 이상 미완료 웨이브를 검출합니다.
    """
    from apps.waves.models import Wave

    from .slack import send_wave_delay_alert

    threshold = timezone.now() - timedelta(hours=2)
    delayed_waves = Wave.objects.filter(
        created_at__lte=threshold,
        status__in=['CREATED', 'PICKING', 'DISTRIBUTING', 'SHIPPING'],
        created_at__date=timezone.localdate(),
    )

    count = 0
    for wave in delayed_waves:
        send_wave_delay_alert(wave)
        count += 1

    if count:
        logger.info('웨이브 처리 지연 %d건 알림', count)
    return {'delayed_count': count}


@app.task(bind=True, ignore_result=True)
def send_order_held_alert_task(self, order_id):
    """주문 보류 알림 (즉시)"""
    from apps.waves.models import OutboundOrder

    from .slack import send_order_held_alert

    try:
        order = OutboundOrder.objects.select_related('client').get(pk=order_id)
    except OutboundOrder.DoesNotExist:
        logger.error('OutboundOrder %s not found', order_id)
        return

    send_order_held_alert(order)


@app.task(bind=True, ignore_result=True)
def send_printer_error_alert_task(self, print_job_id):
    """프린터 오류 알림 (즉시)"""
    from apps.printing.models import PrintJob

    from .slack import send_printer_error_alert

    try:
        print_job = PrintJob.objects.select_related(
            'order', 'printer',
        ).get(pk=print_job_id)
    except PrintJob.DoesNotExist:
        logger.error('PrintJob %s not found', print_job_id)
        return

    send_printer_error_alert(print_job)


@app.task(bind=True, ignore_result=True)
def send_api_error_alert_task(self, adapter_name, error_message):
    """API 연동 오류 알림 (즉시)"""
    from .slack import send_api_error_alert

    send_api_error_alert(adapter_name, error_message)


@app.task(bind=True, ignore_result=True)
def send_daily_shipment_summary_task(self):
    """일일 출고 요약 이메일 발송 (매일 18시)

    출고 완료 건이 있는 거래처에게만 발송합니다.
    """
    from apps.clients.models import Client
    from apps.waves.models import OutboundOrder

    from .email import send_daily_shipment_summary

    today = timezone.localdate()

    # 오늘 출고 건이 있는 거래처 ID 목록
    client_ids = (
        OutboundOrder.objects.filter(
            status='SHIPPED', shipped_at__date=today,
        )
        .values_list('client_id', flat=True)
        .distinct()
    )

    clients = Client.objects.filter(id__in=client_ids, is_active=True)
    sent = 0
    for client in clients:
        try:
            if send_daily_shipment_summary(client, today):
                sent += 1
        except Exception as e:
            logger.error(
                '일일 출고 요약 발송 실패 (거래처=%s): %s',
                client.company_name, e,
            )

    logger.info('일일 출고 요약 발송 완료: %d/%d건', sent, len(client_ids))
    return {'sent': sent, 'total_clients': len(client_ids)}
