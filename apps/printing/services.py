"""
송장 출력 서비스
"""
import logging
import socket
import uuid

from django.utils import timezone

from .models import Printer, Carrier, PrintJob

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
SOCKET_TIMEOUT = 10  # 초


class PrintService:

    @staticmethod
    def trigger_print(order, performed_by=None):
        """검수 완료 후 송장 출력 트리거

        1. 작업자의 WorkerProfile에서 assigned_printer 조회
        2. 주문의 carrier 또는 client의 default_carrier 확인
        3. 송장번호 채번 (더미, 실제는 택배사 API 어댑터에서)
        4. PrintJob 생성 (PENDING)
        5. Celery 태스크로 실제 프린터 전송 (비동기)
        """
        # 1. 프린터 조회
        printer = None
        if performed_by:
            profile = getattr(performed_by, 'worker_profile', None)
            if profile:
                printer = profile.assigned_printer

        if not printer:
            printer = Printer.objects.filter(is_active=True).first()

        # 2. 택배사 확인
        carrier = order.carrier
        if not carrier:
            carrier = getattr(order.client, 'default_carrier', None)

        # 3. 송장번호 채번 (더미)
        tracking_number = order.tracking_number
        if not tracking_number:
            tracking_number = _generate_dummy_tracking(carrier)

        # 4. PrintJob 생성
        print_job = PrintJob.objects.create(
            order=order,
            printer=printer,
            tracking_number=tracking_number,
            carrier=carrier,
            printed_by=performed_by,
        )

        # 주문에 송장번호/택배사 반영
        update_fields = []
        if not order.tracking_number:
            order.tracking_number = tracking_number
            update_fields.append('tracking_number')
        if not order.carrier and carrier:
            order.carrier = carrier
            update_fields.append('carrier')
        if update_fields:
            update_fields.append('updated_at')
            order.save(update_fields=update_fields)

        # 5. Celery 비동기 전송
        from .tasks import send_to_printer_task
        send_to_printer_task.delay(print_job.id)

        return print_job

    @staticmethod
    def send_to_printer(print_job_id):
        """프린터로 라벨 전송

        1. PrintJob 조회
        2. Carrier의 label_template에 데이터 바인딩
        3. 프린터 IP:PORT로 소켓 전송
        4. 성공 → PRINTED, 실패 → attempts++, 3회 초과 시 FAILED
        """
        try:
            print_job = PrintJob.objects.select_related(
                'order', 'printer', 'carrier',
            ).get(pk=print_job_id)
        except PrintJob.DoesNotExist:
            logger.error('PrintJob %s not found', print_job_id)
            return

        if print_job.status == 'PRINTED':
            return

        printer = print_job.printer
        if not printer:
            print_job.status = 'FAILED'
            print_job.error_message = '할당된 프린터가 없습니다.'
            print_job.save(update_fields=['status', 'error_message'])
            return

        # 라벨 데이터 생성
        label_data = _build_label_data(print_job)

        # 소켓 전송 시도
        print_job.attempts += 1
        try:
            _send_socket(printer.ip_address, printer.port, label_data)
            print_job.status = 'PRINTED'
            print_job.printed_at = timezone.now()
            print_job.error_message = ''
            print_job.save(update_fields=[
                'status', 'printed_at', 'attempts', 'error_message',
            ])
            logger.info(
                'Print success: job=%s order=%s printer=%s',
                print_job.id, print_job.order.wms_order_id, printer.name,
            )
        except Exception as e:
            error_msg = str(e)
            print_job.error_message = error_msg
            if print_job.attempts >= MAX_ATTEMPTS:
                print_job.status = 'FAILED'
            print_job.save(update_fields=[
                'status', 'attempts', 'error_message',
            ])
            logger.warning(
                'Print failed: job=%s attempt=%d/%d error=%s',
                print_job.id, print_job.attempts, MAX_ATTEMPTS, error_msg,
            )


def _generate_dummy_tracking(carrier=None):
    """더미 송장번호 생성 (실제 택배사 API 연동 전까지 사용)"""
    prefix = carrier.code if carrier else 'TRK'
    return f'{prefix}-{uuid.uuid4().hex[:10].upper()}'


def _build_label_data(print_job):
    """라벨 템플릿에 데이터 바인딩"""
    order = print_job.order
    carrier = print_job.carrier
    template = carrier.label_template if carrier and carrier.label_template else ''

    if not template:
        # 기본 ZPL 라벨 (간이)
        template = (
            '^XA\n'
            '^FO50,50^A0N,40,40^FD{tracking_number}^FS\n'
            '^FO50,100^A0N,30,30^FD{recipient_name}^FS\n'
            '^FO50,140^A0N,25,25^FD{recipient_address}^FS\n'
            '^FO50,180^A0N,25,25^FD{recipient_phone}^FS\n'
            '^FO50,230^BY3^BCN,100,Y,N,N^FD{tracking_number}^FS\n'
            '^XZ'
        )

    label_data = template.format(
        tracking_number=print_job.tracking_number,
        recipient_name=order.recipient_name,
        recipient_address=order.recipient_address,
        recipient_phone=order.recipient_phone,
        recipient_zip=order.recipient_zip,
        wms_order_id=order.wms_order_id,
        carrier_name=carrier.name if carrier else '',
    )
    return label_data.encode('utf-8')


def _send_socket(ip_address, port, data):
    """프린터로 소켓 전송"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(SOCKET_TIMEOUT)
    try:
        sock.connect((ip_address, port))
        sock.sendall(data)
    finally:
        sock.close()
