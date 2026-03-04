"""
송장 출력 서비스 및 API 테스트
"""
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User, WorkerProfile
from apps.clients.models import Client
from apps.inventory.models import Product, Location, InventoryBalance
from apps.waves.models import Wave, OutboundOrder, OutboundOrderItem
from apps.waves.services import WaveService

from apps.printing.models import Printer, Carrier, PrintJob
from apps.printing.services import PrintService


class PrintingTestMixin:
    """출력 테스트 공통 데이터"""

    def setUp(self):
        self.carrier = Carrier.objects.create(
            name='CJ대한통운', code='CJ',
            label_template=(
                '^XA\n'
                '^FO50,50^FD{tracking_number}^FS\n'
                '^FO50,100^FD{recipient_name}^FS\n'
                '^FO50,140^FD{recipient_address}^FS\n'
                '^FO50,180^FD{recipient_phone}^FS\n'
                '^XZ'
            ),
        )
        self.printer = Printer.objects.create(
            name='출고존 프린터', ip_address='192.168.1.100', port=9100,
            printer_type='ZEBRA', printer_language='ZPL',
        )

        self.client_obj = Client.objects.create(
            company_name='테스트 거래처',
            business_number='123-45-67890',
            contact_person='홍길동',
            contact_phone='010-1234-5678',
            contact_email='test@test.com',
            invoice_email='invoice@test.com',
            default_carrier=self.carrier,
        )
        self.product = Product.objects.create(
            barcode='SKU-A001', name='상품A', client=self.client_obj,
        )
        self.loc_storage = Location.objects.create(
            barcode='STOR-01', zone_type='STORAGE',
        )
        self.loc_outbound = Location.objects.create(
            barcode='OUT-01', zone_type='OUTBOUND_STAGING',
        )

        InventoryBalance.objects.create(
            product=self.product, location=self.loc_storage,
            client=self.client_obj, on_hand_qty=100, allocated_qty=10,
        )

        # 유저
        self.field_user = User.objects.create_user(
            email='field@test.com', password='test1234',
            name='필드작업자', role='field', is_approved=True,
        )
        self.office_user = User.objects.create_user(
            email='office@test.com', password='test1234',
            name='오피스', role='office', is_approved=True,
        )
        self.client_user = User.objects.create_user(
            email='client@test.com', password='test1234',
            name='거래처유저', role='client', is_approved=True,
        )

        # 작업자 프린터 할당
        WorkerProfile.objects.create(
            user=self.field_user, assigned_printer=self.printer,
        )

        self.api = APIClient()

    def _create_inspected_order(self):
        """INSPECTED 상태 주문 생성 (웨이브 포함)"""
        order = OutboundOrder.objects.create(
            source='TEST', source_order_id='T-001',
            client=self.client_obj, status='ALLOCATED',
            recipient_name='수취인A', recipient_phone='010-0000-0000',
            recipient_address='서울 강남구 테헤란로 123',
            recipient_zip='06234',
            ordered_at=timezone.now(),
        )
        OutboundOrderItem.objects.create(
            order=order, product=self.product, qty=3,
        )
        wave = WaveService.create_wave(
            wave_time='09:00', created_by=self.office_user,
        )
        order.refresh_from_db()
        order.status = 'INSPECTED'
        order.save(update_fields=['status'])
        return order, wave


# ------------------------------------------------------------------
# PrintService 테스트
# ------------------------------------------------------------------

class PrintServiceTriggerTest(PrintingTestMixin, TestCase):
    """PrintService.trigger_print() 테스트"""

    @patch('apps.printing.tasks.send_to_printer_task.delay')
    def test_trigger_creates_print_job(self, mock_delay):
        order, _ = self._create_inspected_order()

        job = PrintService.trigger_print(
            order=order, performed_by=self.field_user,
        )

        self.assertIsInstance(job, PrintJob)
        self.assertEqual(job.status, 'PENDING')
        self.assertEqual(job.printer, self.printer)
        self.assertEqual(job.carrier, self.carrier)
        self.assertTrue(job.tracking_number)
        mock_delay.assert_called_once_with(job.id)

    @patch('apps.printing.tasks.send_to_printer_task.delay')
    def test_uses_worker_printer(self, mock_delay):
        """작업자의 assigned_printer 사용"""
        order, _ = self._create_inspected_order()

        job = PrintService.trigger_print(
            order=order, performed_by=self.field_user,
        )
        self.assertEqual(job.printer, self.printer)

    @patch('apps.printing.tasks.send_to_printer_task.delay')
    def test_uses_client_default_carrier(self, mock_delay):
        """주문에 carrier 없으면 client의 default_carrier 사용"""
        order, _ = self._create_inspected_order()
        self.assertIsNone(order.carrier)

        job = PrintService.trigger_print(order=order)
        self.assertEqual(job.carrier, self.carrier)

    @patch('apps.printing.tasks.send_to_printer_task.delay')
    def test_uses_order_carrier_if_set(self, mock_delay):
        """주문에 carrier가 이미 있으면 그것을 사용"""
        other_carrier = Carrier.objects.create(
            name='한진택배', code='HANJIN',
        )
        order, _ = self._create_inspected_order()
        order.carrier = other_carrier
        order.save(update_fields=['carrier'])

        job = PrintService.trigger_print(order=order)
        self.assertEqual(job.carrier, other_carrier)

    @patch('apps.printing.tasks.send_to_printer_task.delay')
    def test_uses_existing_tracking_number(self, mock_delay):
        """주문에 이미 tracking_number 있으면 그것을 사용"""
        order, _ = self._create_inspected_order()
        order.tracking_number = 'EXISTING-123'
        order.save(update_fields=['tracking_number'])

        job = PrintService.trigger_print(order=order)
        self.assertEqual(job.tracking_number, 'EXISTING-123')

    @patch('apps.printing.tasks.send_to_printer_task.delay')
    def test_generates_dummy_tracking(self, mock_delay):
        """tracking_number 없으면 더미 생성"""
        order, _ = self._create_inspected_order()
        self.assertEqual(order.tracking_number, '')

        job = PrintService.trigger_print(order=order)
        self.assertTrue(job.tracking_number.startswith('CJ-'))

    @patch('apps.printing.tasks.send_to_printer_task.delay')
    def test_updates_order_tracking_and_carrier(self, mock_delay):
        """주문에 tracking_number와 carrier 반영"""
        order, _ = self._create_inspected_order()

        job = PrintService.trigger_print(order=order)

        order.refresh_from_db()
        self.assertEqual(order.tracking_number, job.tracking_number)
        self.assertEqual(order.carrier, self.carrier)

    @patch('apps.printing.tasks.send_to_printer_task.delay')
    def test_fallback_printer(self, mock_delay):
        """작업자에 프린터 미할당 → 활성 프린터 중 첫 번째 사용"""
        user_no_profile = User.objects.create_user(
            email='no-profile@test.com', password='test1234',
            name='프로필없음', role='field', is_approved=True,
        )
        order, _ = self._create_inspected_order()

        job = PrintService.trigger_print(
            order=order, performed_by=user_no_profile,
        )
        self.assertEqual(job.printer, self.printer)


# ------------------------------------------------------------------
# PrintService.send_to_printer() 테스트
# ------------------------------------------------------------------

class PrintServiceSendTest(PrintingTestMixin, TestCase):
    """PrintService.send_to_printer() 테스트"""

    @patch('apps.printing.services._send_socket')
    def test_send_success(self, mock_socket):
        order, _ = self._create_inspected_order()
        job = PrintJob.objects.create(
            order=order, printer=self.printer,
            tracking_number='TEST-123', carrier=self.carrier,
        )

        PrintService.send_to_printer(job.id)

        job.refresh_from_db()
        self.assertEqual(job.status, 'PRINTED')
        self.assertIsNotNone(job.printed_at)
        self.assertEqual(job.attempts, 1)
        mock_socket.assert_called_once()

    @patch('apps.printing.services._send_socket')
    def test_send_failure_increments_attempts(self, mock_socket):
        mock_socket.side_effect = ConnectionRefusedError('Connection refused')

        order, _ = self._create_inspected_order()
        job = PrintJob.objects.create(
            order=order, printer=self.printer,
            tracking_number='TEST-123', carrier=self.carrier,
        )

        PrintService.send_to_printer(job.id)

        job.refresh_from_db()
        self.assertEqual(job.status, 'PENDING')
        self.assertEqual(job.attempts, 1)
        self.assertIn('Connection refused', job.error_message)

    @patch('apps.printing.services._send_socket')
    def test_max_attempts_marks_failed(self, mock_socket):
        mock_socket.side_effect = ConnectionRefusedError('fail')

        order, _ = self._create_inspected_order()
        job = PrintJob.objects.create(
            order=order, printer=self.printer,
            tracking_number='TEST-123', carrier=self.carrier,
            attempts=2,  # 이미 2회 시도
        )

        PrintService.send_to_printer(job.id)

        job.refresh_from_db()
        self.assertEqual(job.status, 'FAILED')
        self.assertEqual(job.attempts, 3)

    def test_no_printer_marks_failed(self):
        order, _ = self._create_inspected_order()
        job = PrintJob.objects.create(
            order=order, printer=None,
            tracking_number='TEST-123', carrier=self.carrier,
        )

        PrintService.send_to_printer(job.id)

        job.refresh_from_db()
        self.assertEqual(job.status, 'FAILED')
        self.assertIn('프린터', job.error_message)

    @patch('apps.printing.services._send_socket')
    def test_label_data_contains_order_info(self, mock_socket):
        """라벨 데이터에 주문 정보가 포함되는지 확인"""
        order, _ = self._create_inspected_order()
        job = PrintJob.objects.create(
            order=order, printer=self.printer,
            tracking_number='TEST-123', carrier=self.carrier,
        )

        PrintService.send_to_printer(job.id)

        sent_data = mock_socket.call_args[0][2]
        self.assertIn(b'TEST-123', sent_data)
        self.assertIn(b'\xec\x88\x98\xec\xb7\xa8\xec\x9d\xb8A', sent_data)  # '수취인A' in UTF-8

    @patch('apps.printing.services._send_socket')
    def test_skip_already_printed(self, mock_socket):
        """이미 PRINTED 상태면 스킵"""
        order, _ = self._create_inspected_order()
        job = PrintJob.objects.create(
            order=order, printer=self.printer,
            tracking_number='TEST-123', carrier=self.carrier,
            status='PRINTED',
        )

        PrintService.send_to_printer(job.id)
        mock_socket.assert_not_called()


# ------------------------------------------------------------------
# Signal 연동 테스트
# ------------------------------------------------------------------

class SignalIntegrationTest(PrintingTestMixin, TestCase):
    """order_inspected 시그널 → PrintService.trigger_print() 연동"""

    @patch('apps.printing.tasks.send_to_printer_task.delay')
    def test_signal_triggers_print(self, mock_delay):
        from apps.waves.signals import order_inspected

        order, _ = self._create_inspected_order()

        order_inspected.send(
            sender=OutboundOrder,
            order=order,
            user=self.field_user,
        )

        # PrintJob 생성 확인
        self.assertTrue(PrintJob.objects.filter(order=order).exists())
        mock_delay.assert_called_once()


# ------------------------------------------------------------------
# API 테스트
# ------------------------------------------------------------------

class PendingPrintJobsViewTest(PrintingTestMixin, TestCase):
    """GET /api/v1/printing/pending/"""

    def test_returns_pending_jobs(self):
        order, _ = self._create_inspected_order()
        PrintJob.objects.create(
            order=order, printer=self.printer,
            tracking_number='TEST-001', carrier=self.carrier,
            status='PENDING',
        )
        PrintJob.objects.create(
            order=order, printer=self.printer,
            tracking_number='TEST-002', carrier=self.carrier,
            status='PRINTED',
        )

        self.api.force_authenticate(user=self.field_user)
        resp = self.api.get('/api/v1/printing/pending/')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['tracking_number'], 'TEST-001')

    def test_returns_empty_when_none_pending(self):
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.get('/api/v1/printing/pending/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 0)

    def test_permission_denied_for_client_role(self):
        self.api.force_authenticate(user=self.client_user)
        resp = self.api.get('/api/v1/printing/pending/')
        self.assertEqual(resp.status_code, 403)


class ReprintViewTest(PrintingTestMixin, TestCase):
    """POST /api/v1/printing/reprint/{id}/"""

    @patch('apps.printing.tasks.send_to_printer_task.delay')
    def test_reprint_pending_job(self, mock_delay):
        order, _ = self._create_inspected_order()
        job = PrintJob.objects.create(
            order=order, printer=self.printer,
            tracking_number='TEST-001', carrier=self.carrier,
            status='PENDING',
        )

        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(f'/api/v1/printing/reprint/{job.id}/')

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['success'])
        mock_delay.assert_called_once_with(job.id)

    @patch('apps.printing.tasks.send_to_printer_task.delay')
    def test_reprint_failed_job(self, mock_delay):
        order, _ = self._create_inspected_order()
        job = PrintJob.objects.create(
            order=order, printer=self.printer,
            tracking_number='TEST-001', carrier=self.carrier,
            status='FAILED', attempts=3,
        )

        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(f'/api/v1/printing/reprint/{job.id}/')

        self.assertEqual(resp.status_code, 200)
        mock_delay.assert_called_once()

    def test_reprint_already_printed_error(self):
        order, _ = self._create_inspected_order()
        job = PrintJob.objects.create(
            order=order, printer=self.printer,
            tracking_number='TEST-001', carrier=self.carrier,
            status='PRINTED',
        )

        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(f'/api/v1/printing/reprint/{job.id}/')
        self.assertEqual(resp.status_code, 400)

    def test_reprint_not_found(self):
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post('/api/v1/printing/reprint/99999/')
        self.assertEqual(resp.status_code, 404)

    @patch('apps.printing.tasks.send_to_printer_task.delay')
    def test_reprint_reassigns_printer(self, mock_delay):
        """재출력 시 현재 작업자 프린터로 재할당"""
        new_printer = Printer.objects.create(
            name='새 프린터', ip_address='192.168.1.200', port=9100,
        )
        # 작업자 프린터 변경
        profile = self.field_user.worker_profile
        profile.assigned_printer = new_printer
        profile.save()

        order, _ = self._create_inspected_order()
        job = PrintJob.objects.create(
            order=order, printer=self.printer,  # 원래 프린터
            tracking_number='TEST-001', carrier=self.carrier,
            status='FAILED',
        )

        self.api.force_authenticate(user=self.field_user)
        self.api.post(f'/api/v1/printing/reprint/{job.id}/')

        job.refresh_from_db()
        self.assertEqual(job.printer, new_printer)

    def test_permission_denied_for_client_role(self):
        order, _ = self._create_inspected_order()
        job = PrintJob.objects.create(
            order=order, printer=self.printer,
            tracking_number='TEST-001', carrier=self.carrier,
        )

        self.api.force_authenticate(user=self.client_user)
        resp = self.api.post(f'/api/v1/printing/reprint/{job.id}/')
        self.assertEqual(resp.status_code, 403)
