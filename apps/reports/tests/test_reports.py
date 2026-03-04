"""
리포트 API 테스트

수불부, 출고실적, 작업자생산성, 안전재고, 비동기 리포트 테스트.
"""
from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client, Brand
from apps.inventory.models import (
    Product, Location, InventoryBalance, SafetyStock,
)
from apps.history.models import InventoryTransaction, log_transaction
from apps.waves.models import (
    Wave, OutboundOrder, OutboundOrderItem,
    TotalPickList, TotalPickListDetail,
)
from apps.reports.models import ReportFile


class ReportTestMixin:
    """리포트 테스트 공통 데이터"""

    def setUp(self):
        self.client_obj = Client.objects.create(
            company_name='테스트거래처', business_number='123-45-67890',
            contact_person='홍', contact_phone='010',
            contact_email='t@t.com', invoice_email='i@t.com',
        )
        self.brand = Brand.objects.create(
            client=self.client_obj, name='테스트브랜드',
        )
        self.product = Product.objects.create(
            barcode='SKU-001', name='상품A', client=self.client_obj,
        )
        self.product2 = Product.objects.create(
            barcode='SKU-002', name='상품B', client=self.client_obj,
        )
        self.loc = Location.objects.create(barcode='STOR-01', zone_type='STORAGE')
        self.loc_out = Location.objects.create(
            barcode='OUT-01', zone_type='OUTBOUND_STAGING',
        )

        self.office_user = User.objects.create_user(
            email='office@t.com', password='pw',
            name='오피스', role='office', is_approved=True,
        )
        self.field_user = User.objects.create_user(
            email='field@t.com', password='pw',
            name='필드', role='field', is_approved=True,
        )
        self.client_user = User.objects.create_user(
            email='client@t.com', password='pw',
            name='거래처유저', role='client', is_approved=True,
        )
        self.api = APIClient()
        self.today = date.today()
        self.date_from = str(self.today - timedelta(days=7))
        self.date_to = str(self.today)


# ------------------------------------------------------------------
# 수불부 리포트
# ------------------------------------------------------------------

class InventoryLedgerTest(ReportTestMixin, TestCase):

    def _create_transactions(self):
        """테스트 트랜잭션 생성"""
        # 기초재고 (기간 이전)
        log_transaction(
            client=self.client_obj, product=self.product,
            transaction_type='GR', to_location=self.loc,
            qty=100, balance_after=100,
            reference_type='INBOUND', reference_id='IB-INIT',
            performed_by=self.office_user,
        )
        # 기간 이전 시점을 만들기 위해 timestamp 직접 수정
        InventoryTransaction.objects.filter(reference_id='IB-INIT').update(
            timestamp=timezone.now() - timedelta(days=10),
        )

        # 기간 내 입고
        log_transaction(
            client=self.client_obj, product=self.product,
            transaction_type='GR', to_location=self.loc,
            qty=50, balance_after=150,
            reference_type='INBOUND', reference_id='IB-001',
            performed_by=self.office_user,
        )
        # 기간 내 출고
        log_transaction(
            client=self.client_obj, product=self.product,
            transaction_type='GI', from_location=self.loc,
            qty=-30, balance_after=120,
            reference_type='OUTBOUND', reference_id='WO-001',
            performed_by=self.office_user,
        )

    def test_requires_client_id(self):
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/reports/inventory-ledger/', {
            'date_from': self.date_from, 'date_to': self.date_to,
        })
        self.assertEqual(resp.status_code, 400)

    def test_json_response(self):
        self._create_transactions()
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/reports/inventory-ledger/', {
            'client_id': self.client_obj.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('results', resp.data)
        self.assertEqual(resp.data['count'], 1)

        row = resp.data['results'][0]
        self.assertEqual(row['sku'], 'SKU-001')
        self.assertEqual(row['opening_balance'], 100)
        self.assertEqual(row['inbound_qty'], 50)
        self.assertEqual(row['outbound_qty'], -30)
        self.assertEqual(row['closing_balance'], 120)

    def test_xlsx_response(self):
        self._create_transactions()
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/reports/inventory-ledger/', {
            'client_id': self.client_obj.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'export': 'xlsx',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('spreadsheetml', resp['Content-Type'])
        self.assertTrue(resp.has_header('Content-Disposition'))

    def test_date_filter_excludes_out_of_range(self):
        """범위 밖 트랜잭션 제외"""
        # 범위 밖 트랜잭션
        log_transaction(
            client=self.client_obj, product=self.product2,
            transaction_type='GR', to_location=self.loc,
            qty=10, balance_after=10,
            reference_type='INBOUND',
        )
        InventoryTransaction.objects.filter(
            product=self.product2,
        ).update(timestamp=timezone.now() - timedelta(days=30))

        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/reports/inventory-ledger/', {
            'client_id': self.client_obj.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
        })
        self.assertEqual(resp.status_code, 200)
        # product2는 기간 내 트랜잭션 없으므로 결과에 미포함
        self.assertEqual(resp.data['count'], 0)

    def test_permission_denied_for_client_role(self):
        self.api.force_authenticate(user=self.client_user)
        resp = self.api.get('/api/v1/reports/inventory-ledger/', {
            'client_id': self.client_obj.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
        })
        self.assertEqual(resp.status_code, 403)


# ------------------------------------------------------------------
# 출고 실적 리포트
# ------------------------------------------------------------------

class ShipmentSummaryTest(ReportTestMixin, TestCase):

    def _create_shipped_orders(self):
        wave = Wave.objects.create(
            wave_time='09:00', created_by=self.office_user,
        )
        for i in range(3):
            order = OutboundOrder.objects.create(
                source='TEST', source_order_id=f'T-{i}',
                client=self.client_obj, brand=self.brand,
                status='SHIPPED', shipped_at=timezone.now(),
                wave=wave,
                recipient_name='수취인', recipient_phone='010',
                recipient_address='서울', ordered_at=timezone.now(),
            )
            OutboundOrderItem.objects.create(
                order=order, product=self.product, qty=5,
            )
        return wave

    def test_json_response(self):
        self._create_shipped_orders()
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/reports/shipment-summary/', {
            'date_from': self.date_from, 'date_to': self.date_to,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('daily', resp.data)
        self.assertIn('wave', resp.data)
        self.assertEqual(len(resp.data['daily']), 1)
        self.assertEqual(resp.data['daily'][0]['order_count'], 3)
        self.assertEqual(resp.data['daily'][0]['total_qty'], 15)

    def test_client_filter(self):
        self._create_shipped_orders()
        other = Client.objects.create(
            company_name='다른거래처', business_number='999-99-99999',
            contact_person='김', contact_phone='011',
            contact_email='o@o.com', invoice_email='oi@o.com',
        )
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/reports/shipment-summary/', {
            'date_from': self.date_from, 'date_to': self.date_to,
            'client_id': other.id,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['daily']), 0)

    def test_xlsx_response(self):
        self._create_shipped_orders()
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/reports/shipment-summary/', {
            'date_from': self.date_from, 'date_to': self.date_to,
            'export': 'xlsx',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('spreadsheetml', resp['Content-Type'])

    def test_empty_result(self):
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/reports/shipment-summary/', {
            'date_from': self.date_from, 'date_to': self.date_to,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['daily']), 0)


# ------------------------------------------------------------------
# 작업자 생산성 리포트
# ------------------------------------------------------------------

class WorkerProductivityTest(ReportTestMixin, TestCase):

    def _create_pick_data(self):
        wave = Wave.objects.create(
            wave_time='09:00', created_by=self.office_user,
        )
        pick_list = TotalPickList.objects.create(
            wave=wave, product=self.product, total_qty=20,
        )
        for i in range(5):
            TotalPickListDetail.objects.create(
                pick_list=pick_list,
                from_location=self.loc,
                to_location=self.loc_out,
                qty=4, picked_qty=4,
                picked_by=self.field_user,
                picked_at=timezone.now(),
            )

    def test_json_response(self):
        self._create_pick_data()
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/reports/worker-productivity/', {
            'date_from': self.date_from, 'date_to': self.date_to,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.data['count'], 1)

        worker = next(
            r for r in resp.data['results']
            if r['worker_id'] == self.field_user.id
        )
        self.assertEqual(worker['pick_count'], 5)
        self.assertEqual(worker['pick_qty'], 20)

    def test_xlsx_response(self):
        self._create_pick_data()
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/reports/worker-productivity/', {
            'date_from': self.date_from, 'date_to': self.date_to,
            'export': 'xlsx',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('spreadsheetml', resp['Content-Type'])

    def test_date_range_filter(self):
        self._create_pick_data()
        # 범위 밖 조회
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/reports/worker-productivity/', {
            'date_from': '2020-01-01', 'date_to': '2020-01-31',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['count'], 0)

    def test_permission_denied_for_client_role(self):
        self.api.force_authenticate(user=self.client_user)
        resp = self.api.get('/api/v1/reports/worker-productivity/', {
            'date_from': self.date_from, 'date_to': self.date_to,
        })
        self.assertEqual(resp.status_code, 403)


# ------------------------------------------------------------------
# 안전재고 미달 리포트
# ------------------------------------------------------------------

class SafetyStockAlertTest(ReportTestMixin, TestCase):

    def _create_safety_stock(self):
        SafetyStock.objects.create(
            product=self.product, client=self.client_obj,
            min_qty=50, alert_enabled=True,
        )
        InventoryBalance.objects.create(
            product=self.product, location=self.loc,
            client=self.client_obj, on_hand_qty=30,
        )

    def test_json_response(self):
        self._create_safety_stock()
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/reports/safety-stock-alert/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['count'], 1)

        row = resp.data['results'][0]
        self.assertEqual(row['sku'], 'SKU-001')
        self.assertEqual(row['min_qty'], 50)
        self.assertEqual(row['current_qty'], 30)
        self.assertEqual(row['shortage'], 20)

    def test_client_filter(self):
        self._create_safety_stock()
        other = Client.objects.create(
            company_name='다른거래처', business_number='999-99-99999',
            contact_person='김', contact_phone='011',
            contact_email='o@o.com', invoice_email='oi@o.com',
        )
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/reports/safety-stock-alert/', {
            'client_id': other.id,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['count'], 0)

    def test_xlsx_response(self):
        self._create_safety_stock()
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/reports/safety-stock-alert/', {
            'export': 'xlsx',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('spreadsheetml', resp['Content-Type'])


# ------------------------------------------------------------------
# 비동기 리포트
# ------------------------------------------------------------------

class AsyncReportTest(ReportTestMixin, TestCase):

    def test_report_file_status(self):
        rf = ReportFile.objects.create(
            report_type='INVENTORY_LEDGER',
            status='COMPLETED',
            row_count=100,
            created_by=self.office_user,
        )
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get(f'/api/v1/reports/files/{rf.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'COMPLETED')
        self.assertEqual(resp.data['row_count'], 100)

    @patch('apps.reports.views.ASYNC_THRESHOLD', 0)
    def test_async_threshold_returns_202(self):
        """데이터가 threshold 초과 시 202 반환"""
        log_transaction(
            client=self.client_obj, product=self.product,
            transaction_type='GR', to_location=self.loc,
            qty=10, balance_after=10,
            reference_type='INBOUND',
            performed_by=self.office_user,
        )
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/reports/inventory-ledger/', {
            'client_id': self.client_obj.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'export': 'xlsx',
        })
        self.assertEqual(resp.status_code, 202)
        self.assertIn('report_file_id', resp.data)

        rf = ReportFile.objects.get(pk=resp.data['report_file_id'])
        # CELERY_TASK_ALWAYS_EAGER=True이므로 동기 실행됨
        self.assertEqual(rf.status, 'COMPLETED')
        self.assertTrue(rf.file)

    def test_celery_task_generates_file(self):
        rf = ReportFile.objects.create(
            report_type='SAFETY_STOCK_ALERT',
            params={},
            created_by=self.office_user,
        )
        from apps.reports.tasks import generate_report_excel
        generate_report_excel(rf.id)

        rf.refresh_from_db()
        self.assertEqual(rf.status, 'COMPLETED')
        self.assertEqual(rf.row_count, 0)

    def test_report_file_not_found(self):
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/reports/files/99999/')
        self.assertEqual(resp.status_code, 404)
