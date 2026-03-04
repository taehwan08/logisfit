from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.clients.models import Brand, Client
from apps.history.models import InventoryTransaction
from apps.inventory.models import (
    InventoryBalance,
    Location,
    Product,
    SafetyStock,
)
from apps.printing.models import Carrier, PrintJob, Printer
from apps.waves.models import OutboundOrder, Wave


class NotificationTestMixin:
    def setUp(self):
        self.client_obj = Client.objects.create(
            company_name='테스트거래처',
            business_number='123-45-67890',
            contact_person='담당자',
            contact_phone='010-1234-5678',
            contact_email='test@test.com',
            invoice_email='invoice@test.com',
        )
        self.brand = Brand.objects.create(
            client=self.client_obj, name='테스트브랜드',
        )
        self.product = Product.objects.create(
            barcode='P001', name='상품1',
            client=self.client_obj, brand=self.brand,
        )
        self.location = Location.objects.create(
            barcode='LOC-001', name='A-01',
        )
        self.admin_user = User.objects.create_user(
            email='admin@test.com', password='test1234',
            name='관리자', role='admin', is_approved=True,
        )
        self.client_user = User.objects.create_user(
            email='client@test.com', password='test1234',
            name='거래처유저', role='client', is_approved=True,
        )
        self.client_user.clients.add(self.client_obj)


# ============================================================================
# Slack 알림 테스트
# ============================================================================

class SafetyStockAlertTest(NotificationTestMixin, TestCase):

    @patch('apps.notifications.slack.requests.post')
    @override_settings(SLACK_WEBHOOK_ALERTS='https://hooks.slack.com/test')
    def test_safety_stock_alert_sends_slack(self, mock_post):
        """안전재고 미달 시 Slack 메시지 발송"""
        mock_post.return_value.status_code = 200
        SafetyStock.objects.create(
            product=self.product, client=self.client_obj,
            min_qty=100, alert_enabled=True,
        )
        InventoryBalance.objects.create(
            product=self.product, location=self.location,
            client=self.client_obj, on_hand_qty=10,
        )

        from apps.notifications.tasks import check_safety_stock_task
        result = check_safety_stock_task()
        self.assertEqual(result['alert_count'], 1)
        mock_post.assert_called_once()

        payload = mock_post.call_args[1]['json']
        self.assertIn('안전재고 미달', payload['text'])

    def test_safety_stock_no_alert_when_sufficient(self):
        """재고 충분 시 알림 없음"""
        SafetyStock.objects.create(
            product=self.product, client=self.client_obj,
            min_qty=10, alert_enabled=True,
        )
        InventoryBalance.objects.create(
            product=self.product, location=self.location,
            client=self.client_obj, on_hand_qty=100,
        )

        from apps.notifications.tasks import check_safety_stock_task
        result = check_safety_stock_task()
        self.assertEqual(result['alert_count'], 0)


class WaveDelayAlertTest(NotificationTestMixin, TestCase):

    @patch('apps.notifications.slack.requests.post')
    @override_settings(SLACK_WEBHOOK_ALERTS='https://hooks.slack.com/test')
    def test_wave_delay_alert(self, mock_post):
        """2시간 초과 웨이브 지연 알림"""
        mock_post.return_value.status_code = 200
        wave = Wave.objects.create(
            wave_id='WV-TEST-01', status='PICKING',
            wave_time='09:00', total_orders=10,
        )
        # 생성 시각을 3시간 전으로 변경
        Wave.objects.filter(pk=wave.pk).update(
            created_at=timezone.now() - timedelta(hours=3),
        )

        from apps.notifications.tasks import check_wave_delays_task
        result = check_wave_delays_task()
        self.assertEqual(result['delayed_count'], 1)
        mock_post.assert_called_once()

    def test_no_delay_within_2_hours(self):
        """2시간 이내 웨이브는 알림 없음"""
        Wave.objects.create(
            wave_id='WV-TEST-02', status='PICKING',
            wave_time='09:00', total_orders=10,
        )

        from apps.notifications.tasks import check_wave_delays_task
        result = check_wave_delays_task()
        self.assertEqual(result['delayed_count'], 0)

    def test_completed_wave_no_alert(self):
        """완료된 웨이브는 알림 제외"""
        wave = Wave.objects.create(
            wave_id='WV-TEST-03', status='COMPLETED',
            wave_time='09:00', total_orders=10,
        )
        Wave.objects.filter(pk=wave.pk).update(
            created_at=timezone.now() - timedelta(hours=3),
        )

        from apps.notifications.tasks import check_wave_delays_task
        result = check_wave_delays_task()
        self.assertEqual(result['delayed_count'], 0)


class OrderHeldAlertTest(NotificationTestMixin, TestCase):

    @patch('apps.notifications.slack.requests.post')
    @override_settings(SLACK_WEBHOOK_ALERTS='https://hooks.slack.com/test')
    def test_order_held_alert(self, mock_post):
        """주문 보류 시 Slack 알림"""
        mock_post.return_value.status_code = 200
        order = OutboundOrder.objects.create(
            source='TEST', source_order_id='SO-001',
            client=self.client_obj, status='HELD',
            hold_reason='상품1: 요청 100, 가용 10',
            recipient_name='홍길동', recipient_phone='010-0000-0000',
            recipient_address='서울시', ordered_at=timezone.now(),
        )

        from apps.notifications.tasks import send_order_held_alert_task
        send_order_held_alert_task(order.id)
        mock_post.assert_called_once()

        payload = mock_post.call_args[1]['json']
        self.assertIn('주문 보류', payload['text'])
        self.assertIn(order.wms_order_id, payload['text'])


class PrinterErrorAlertTest(NotificationTestMixin, TestCase):

    @patch('apps.notifications.slack.requests.post')
    @override_settings(SLACK_WEBHOOK_ALERTS='https://hooks.slack.com/test')
    def test_printer_error_alert(self, mock_post):
        """프린터 오류 시 Slack 알림"""
        mock_post.return_value.status_code = 200
        printer = Printer.objects.create(
            name='테스트프린터', ip_address='192.168.1.1', port=9100,
        )
        order = OutboundOrder.objects.create(
            source='TEST', source_order_id='SO-001',
            client=self.client_obj,
            recipient_name='홍길동', recipient_phone='010-0000-0000',
            recipient_address='서울시', ordered_at=timezone.now(),
        )
        print_job = PrintJob.objects.create(
            order=order, printer=printer, tracking_number='TRK-001',
            status='FAILED', attempts=3,
            error_message='Connection refused',
        )

        from apps.notifications.tasks import send_printer_error_alert_task
        send_printer_error_alert_task(print_job.id)
        mock_post.assert_called_once()

        payload = mock_post.call_args[1]['json']
        self.assertIn('프린터 오류', payload['text'])


class ApiErrorAlertTest(NotificationTestMixin, TestCase):

    @patch('apps.notifications.slack.requests.post')
    @override_settings(SLACK_WEBHOOK_ALERTS='https://hooks.slack.com/test')
    def test_api_error_alert(self, mock_post):
        """API 오류 시 Slack 알림"""
        mock_post.return_value.status_code = 200

        from apps.notifications.tasks import send_api_error_alert_task
        send_api_error_alert_task('사방넷', 'Connection timeout')
        mock_post.assert_called_once()

        payload = mock_post.call_args[1]['json']
        self.assertIn('사방넷', payload['text'])
        self.assertIn('API 연동 오류', payload['text'])


class SlackWebhookFallbackTest(NotificationTestMixin, TestCase):

    @patch('apps.notifications.slack.requests.post')
    @override_settings(SLACK_WEBHOOK_ALERTS='', SLACK_WEBHOOK_URL='https://hooks.slack.com/fallback')
    def test_fallback_to_default_webhook(self, mock_post):
        """SLACK_WEBHOOK_ALERTS 미설정 시 SLACK_WEBHOOK_URL 사용"""
        mock_post.return_value.status_code = 200

        from apps.notifications.tasks import send_api_error_alert_task
        send_api_error_alert_task('테스트', '오류')
        mock_post.assert_called_once()
        self.assertEqual(
            mock_post.call_args[0][0], 'https://hooks.slack.com/fallback',
        )

    @override_settings(SLACK_WEBHOOK_ALERTS='', SLACK_WEBHOOK_URL='')
    def test_no_webhook_configured_no_error(self):
        """웹훅 미설정 시 에러 없이 스킵"""
        from apps.notifications.tasks import send_api_error_alert_task
        # 예외 없이 실행되어야 함
        send_api_error_alert_task('테스트', '오류')


# ============================================================================
# 이메일 알림 테스트
# ============================================================================

class DailyShipmentSummaryTest(NotificationTestMixin, TestCase):

    @patch('apps.notifications.email.send_email', return_value=True)
    def test_daily_summary_sent(self, mock_send):
        """오늘 출고 건이 있으면 이메일 발송"""
        now = timezone.now()
        OutboundOrder.objects.create(
            source='TEST', source_order_id='SO-001',
            client=self.client_obj, status='SHIPPED',
            shipped_at=now, recipient_name='홍길동',
            recipient_phone='010-0000-0000',
            recipient_address='서울시', ordered_at=now,
        )

        from apps.notifications.tasks import send_daily_shipment_summary_task
        result = send_daily_shipment_summary_task()
        self.assertEqual(result['sent'], 1)
        mock_send.assert_called_once()

        # 제목에 거래처명 포함
        subject = mock_send.call_args[0][1]
        self.assertIn('테스트거래처', subject)

    @patch('apps.notifications.email.send_email', return_value=True)
    def test_no_summary_when_no_shipments(self, mock_send):
        """출고 건 없으면 이메일 발송 안 함"""
        from apps.notifications.tasks import send_daily_shipment_summary_task
        result = send_daily_shipment_summary_task()
        self.assertEqual(result['sent'], 0)
        mock_send.assert_not_called()

    @patch('apps.notifications.email.send_email', return_value=True)
    def test_summary_includes_held_count(self, mock_send):
        """보류 건수 포함"""
        now = timezone.now()
        OutboundOrder.objects.create(
            source='TEST', source_order_id='SO-001',
            client=self.client_obj, status='SHIPPED',
            shipped_at=now, recipient_name='홍길동',
            recipient_phone='010-0000-0000',
            recipient_address='서울시', ordered_at=now,
        )
        OutboundOrder.objects.create(
            source='TEST', source_order_id='SO-002',
            client=self.client_obj, status='HELD',
            hold_reason='재고부족', recipient_name='김철수',
            recipient_phone='010-0000-0001',
            recipient_address='부산시', ordered_at=now,
        )

        from apps.notifications.tasks import send_daily_shipment_summary_task
        result = send_daily_shipment_summary_task()
        self.assertEqual(result['sent'], 1)

        html_content = mock_send.call_args[0][2]
        self.assertIn('보류 중인 주문', html_content)

    @patch('apps.notifications.email.send_email', return_value=True)
    def test_summary_sent_to_client_user_email(self, mock_send):
        """화주사 소속 유저 이메일로 발송"""
        now = timezone.now()
        OutboundOrder.objects.create(
            source='TEST', source_order_id='SO-001',
            client=self.client_obj, status='SHIPPED',
            shipped_at=now, recipient_name='홍길동',
            recipient_phone='010-0000-0000',
            recipient_address='서울시', ordered_at=now,
        )

        from apps.notifications.tasks import send_daily_shipment_summary_task
        send_daily_shipment_summary_task()

        to_emails = mock_send.call_args[0][0]
        self.assertIn('client@test.com', to_emails)


# ============================================================================
# 통합 트리거 테스트
# ============================================================================

class PrinterErrorTriggerTest(TestCase):

    @patch('apps.notifications.tasks.send_printer_error_alert_task.delay')
    def test_failed_print_triggers_alert(self, mock_delay):
        """PrintJob FAILED 시 알림 태스크 호출"""
        from apps.printing.services import PrintService

        client_obj = Client.objects.create(
            company_name='테스트', business_number='111-11-11111',
            contact_person='담당', contact_phone='010-1111-1111',
            contact_email='t@t.com', invoice_email='i@t.com',
        )
        order = OutboundOrder.objects.create(
            source='TEST', source_order_id='TR-001',
            client=client_obj, recipient_name='홍길동',
            recipient_phone='010-0000-0000',
            recipient_address='서울시', ordered_at=timezone.now(),
        )
        printer = Printer.objects.create(
            name='고장프린터', ip_address='192.168.1.1', port=9100,
        )
        print_job = PrintJob.objects.create(
            order=order, printer=printer, tracking_number='TRK-001',
            status='PENDING', attempts=2,
        )

        # 3번째 시도 → FAILED → 알림 트리거
        PrintService.send_to_printer(print_job.id)

        print_job.refresh_from_db()
        self.assertEqual(print_job.status, 'FAILED')
        mock_delay.assert_called_once_with(print_job.id)
