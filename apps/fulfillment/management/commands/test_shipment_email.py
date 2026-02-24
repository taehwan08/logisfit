"""
출고 알림 이메일 테스트 커맨드

사용법:
    python3 manage.py test_shipment_email <order_id>
    python3 manage.py test_shipment_email <order_id> --to=test@example.com
"""
from django.core.management.base import BaseCommand

from apps.fulfillment.models import FulfillmentOrder
from apps.accounts.email import send_shipment_notification, send_email


class Command(BaseCommand):
    help = '출고 알림 이메일 발송을 테스트합니다.'

    def add_arguments(self, parser):
        parser.add_argument('order_id', type=int, help='테스트할 주문 ID')
        parser.add_argument('--to', type=str, help='수신 이메일 오버라이드 (테스트용)')

    def handle(self, *args, **options):
        order_id = options['order_id']
        override_email = options.get('to')

        # 1) 주문 조회
        try:
            order = FulfillmentOrder.objects.select_related(
                'created_by', 'client', 'shipped_by',
            ).get(id=order_id)
        except FulfillmentOrder.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'주문 ID {order_id}를 찾을 수 없습니다.'))
            return

        self.stdout.write(f'주문 정보:')
        self.stdout.write(f'  - 발주번호: {order.order_number}')
        self.stdout.write(f'  - 상품명: {order.product_name}')
        self.stdout.write(f'  - 상태: {order.get_status_display()}')
        self.stdout.write(f'  - 플랫폼: {order.get_platform_display()}')
        self.stdout.write(f'  - 거래처: {order.client.name if order.client else "없음"}')
        self.stdout.write(f'  - created_by: {order.created_by}')
        self.stdout.write(f'  - created_by_id: {order.created_by_id}')
        self.stdout.write(f'  - created_by.email: {order.created_by.email if order.created_by else "없음"}')
        self.stdout.write(f'  - shipped_by: {order.shipped_by}')
        self.stdout.write(f'  - shipped_at: {order.shipped_at}')
        self.stdout.write('')

        # 2) 이메일 오버라이드
        if override_email and order.created_by:
            self.stdout.write(f'수신 이메일 오버라이드: {order.created_by.email} → {override_email}')
            order.created_by.email = override_email

        # 3) 간단한 테스트 이메일 먼저 시도
        self.stdout.write('\n--- 간단한 테스트 이메일 발송 ---')
        test_to = override_email or (order.created_by.email if order.created_by else None)
        if test_to:
            result = send_email(
                to=test_to,
                subject='[LogisFit] 이메일 발송 테스트',
                html_content='<h1>테스트</h1><p>이 이메일은 테스트입니다.</p>',
            )
            self.stdout.write(f'간단 테스트 결과: {result}')
        else:
            self.stdout.write(self.style.WARNING('수신자 이메일이 없어 간단 테스트를 건너뜁니다.'))

        # 4) 출고 알림 이메일 발송
        self.stdout.write('\n--- 출고 알림 이메일 발송 ---')
        result = send_shipment_notification(order)
        if result:
            self.stdout.write(self.style.SUCCESS(f'출고 알림 이메일 발송 성공!'))
        else:
            self.stdout.write(self.style.ERROR(f'출고 알림 이메일 발송 실패!'))
