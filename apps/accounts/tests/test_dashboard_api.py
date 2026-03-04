from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Brand, Client
from apps.history.models import InventoryTransaction
from apps.inbound.models import InboundOrder
from apps.inventory.models import (
    InventoryBalance,
    Location,
    Product,
    SafetyStock,
)
from apps.waves.models import (
    OutboundOrder,
    TotalPickList,
    TotalPickListDetail,
    Wave,
)


class DashboardTestMixin:
    def setUp(self):
        self.api = APIClient()

        # Clients
        self.client_obj = Client.objects.create(
            company_name='테스트거래처',
            business_number='123-45-67890',
            contact_person='담당자',
            contact_phone='010-1234-5678',
            contact_email='test@test.com',
            invoice_email='invoice@test.com',
        )
        self.client_obj2 = Client.objects.create(
            company_name='다른거래처',
            business_number='987-65-43210',
            contact_person='담당자2',
            contact_phone='010-9876-5432',
            contact_email='test2@test.com',
            invoice_email='invoice2@test.com',
        )

        # Brands
        self.brand = Brand.objects.create(
            client=self.client_obj, name='테스트브랜드',
        )
        self.brand2 = Brand.objects.create(
            client=self.client_obj2, name='다른브랜드',
        )

        # Users
        self.office_user = User.objects.create_user(
            email='office@test.com', password='test1234',
            name='오피스유저', role='office', is_approved=True,
        )
        self.field_user = User.objects.create_user(
            email='field@test.com', password='test1234',
            name='필드유저', role='field', is_approved=True,
        )
        self.client_user = User.objects.create_user(
            email='client@test.com', password='test1234',
            name='거래처유저', role='client', is_approved=True,
        )
        self.client_user.clients.add(self.client_obj)

        # Products & Locations
        self.product = Product.objects.create(
            barcode='P001', name='상품1',
            client=self.client_obj, brand=self.brand,
        )
        self.product2 = Product.objects.create(
            barcode='P002', name='상품2',
            client=self.client_obj2, brand=self.brand2,
        )
        self.location = Location.objects.create(
            barcode='LOC-001', name='A-01',
        )


class OfficeDashboardTest(DashboardTestMixin, TestCase):
    def test_response_structure(self):
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/dashboard/office/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('today_summary', resp.data)
        self.assertIn('waves', resp.data)
        self.assertIn('safety_stock_alerts', resp.data)
        self.assertIn('pending_inbound', resp.data)

    def test_today_order_counts(self):
        now = timezone.now()
        OutboundOrder.objects.create(
            source='TEST', source_order_id='SO-001',
            client=self.client_obj, recipient_name='홍길동',
            recipient_phone='010-0000-0000', recipient_address='서울시',
            ordered_at=now, status='RECEIVED',
        )
        OutboundOrder.objects.create(
            source='TEST', source_order_id='SO-002',
            client=self.client_obj, recipient_name='김철수',
            recipient_phone='010-0000-0001', recipient_address='부산시',
            ordered_at=now, status='SHIPPED', shipped_at=now,
        )
        OutboundOrder.objects.create(
            source='TEST', source_order_id='SO-003',
            client=self.client_obj, recipient_name='이영희',
            recipient_phone='010-0000-0002', recipient_address='대구시',
            ordered_at=now, status='HELD',
        )

        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/dashboard/office/')
        summary = resp.data['today_summary']
        self.assertEqual(summary['total_orders_received'], 3)
        self.assertEqual(summary['total_orders_shipped'], 1)
        self.assertEqual(summary['orders_held'], 1)
        self.assertAlmostEqual(summary['shipment_rate'], 33.3, places=1)

    def test_wave_list(self):
        Wave.objects.create(
            wave_id='WV-20260304-01', status='PICKING',
            wave_time='09:00', total_orders=10, shipped_count=3,
        )
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/dashboard/office/')
        self.assertEqual(len(resp.data['waves']), 1)
        wave = resp.data['waves'][0]
        self.assertEqual(wave['wave_id'], 'WV-20260304-01')
        self.assertAlmostEqual(wave['progress'], 30.0, places=1)

    def test_safety_stock_alert_count(self):
        SafetyStock.objects.create(
            product=self.product, client=self.client_obj,
            min_qty=100, alert_enabled=True,
        )
        InventoryBalance.objects.create(
            product=self.product, location=self.location,
            client=self.client_obj, on_hand_qty=10,
        )
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/dashboard/office/')
        self.assertEqual(resp.data['safety_stock_alerts'], 1)

    def test_client_user_denied(self):
        self.api.force_authenticate(user=self.client_user)
        resp = self.api.get('/api/v1/dashboard/office/')
        self.assertEqual(resp.status_code, 403)


class FieldDashboardTest(DashboardTestMixin, TestCase):
    def test_response_structure(self):
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.get('/api/v1/dashboard/field/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('current_wave', resp.data)
        self.assertIn('inspection_pending', resp.data)
        self.assertIn('my_today', resp.data)

    def test_current_wave_progress(self):
        Wave.objects.create(
            wave_id='WV-20260304-01', status='PICKING',
            wave_time='09:00', total_orders=20, picked_count=8,
        )
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.get('/api/v1/dashboard/field/')
        wave = resp.data['current_wave']
        self.assertIsNotNone(wave)
        self.assertEqual(wave['pick_total'], 20)
        self.assertEqual(wave['pick_done'], 8)
        self.assertAlmostEqual(wave['progress'], 40.0, places=1)

    def test_my_picking_stats(self):
        now = timezone.now()
        wave = Wave.objects.create(
            wave_id='WV-20260304-01', status='PICKING',
            wave_time='09:00', total_orders=10,
        )
        pick_list = TotalPickList.objects.create(
            wave=wave, product=self.product,
            total_qty=5, status='IN_PROGRESS',
        )
        TotalPickListDetail.objects.create(
            pick_list=pick_list, from_location=self.location,
            qty=3, picked_qty=3,
            picked_by=self.field_user, picked_at=now,
        )
        TotalPickListDetail.objects.create(
            pick_list=pick_list, from_location=self.location,
            qty=2, picked_qty=2,
            picked_by=self.field_user, picked_at=now,
        )

        self.api.force_authenticate(user=self.field_user)
        resp = self.api.get('/api/v1/dashboard/field/')
        my = resp.data['my_today']
        self.assertEqual(my['pick_count'], 2)
        self.assertEqual(my['pick_qty'], 5)

    def test_inspection_pending_count(self):
        wave = Wave.objects.create(
            wave_id='WV-20260304-01', status='PICKING',
            wave_time='09:00', total_orders=5,
        )
        OutboundOrder.objects.create(
            source='TEST', source_order_id='SO-001',
            client=self.client_obj, recipient_name='홍길동',
            recipient_phone='010-0000-0000', recipient_address='서울시',
            ordered_at=timezone.now(), status='PICKING', wave=wave,
        )
        OutboundOrder.objects.create(
            source='TEST', source_order_id='SO-002',
            client=self.client_obj, recipient_name='김철수',
            recipient_phone='010-0000-0001', recipient_address='부산시',
            ordered_at=timezone.now(), status='PICKING', wave=wave,
        )

        self.api.force_authenticate(user=self.field_user)
        resp = self.api.get('/api/v1/dashboard/field/')
        self.assertEqual(resp.data['inspection_pending'], 2)

    def test_client_user_denied(self):
        self.api.force_authenticate(user=self.client_user)
        resp = self.api.get('/api/v1/dashboard/field/')
        self.assertEqual(resp.status_code, 403)


class ClientDashboardTest(DashboardTestMixin, TestCase):
    def test_response_structure(self):
        self.api.force_authenticate(user=self.client_user)
        resp = self.api.get('/api/v1/dashboard/client/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('inventory_summary', resp.data)
        self.assertIn('today_inbound', resp.data)
        self.assertIn('today_outbound', resp.data)
        self.assertIn('safety_stock_alerts', resp.data)

    def test_inventory_by_brand(self):
        InventoryBalance.objects.create(
            product=self.product, location=self.location,
            client=self.client_obj, on_hand_qty=100, allocated_qty=20,
        )
        self.api.force_authenticate(user=self.client_user)
        resp = self.api.get('/api/v1/dashboard/client/')
        summary = resp.data['inventory_summary']
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]['total_on_hand'], 100)
        self.assertEqual(summary[0]['total_allocated'], 20)

    def test_today_inbound_outbound(self):
        now = timezone.now()
        InventoryTransaction.objects.create(
            client=self.client_obj, product=self.product,
            transaction_type='GR', qty=50, balance_after=50,
            reference_type='INBOUND', timestamp=now,
        )
        InventoryTransaction.objects.create(
            client=self.client_obj, product=self.product,
            transaction_type='GI', qty=10, balance_after=40,
            reference_type='OUTBOUND', timestamp=now,
        )

        self.api.force_authenticate(user=self.client_user)
        resp = self.api.get('/api/v1/dashboard/client/')
        self.assertEqual(resp.data['today_inbound']['count'], 1)
        self.assertEqual(resp.data['today_inbound']['qty'], 50)
        self.assertEqual(resp.data['today_outbound']['count'], 1)
        self.assertEqual(resp.data['today_outbound']['qty'], 10)

    def test_safety_stock_alerts_filtered(self):
        SafetyStock.objects.create(
            product=self.product, client=self.client_obj,
            min_qty=100, alert_enabled=True,
        )
        SafetyStock.objects.create(
            product=self.product2, client=self.client_obj2,
            min_qty=50, alert_enabled=True,
        )
        InventoryBalance.objects.create(
            product=self.product, location=self.location,
            client=self.client_obj, on_hand_qty=10,
        )
        InventoryBalance.objects.create(
            product=self.product2, location=self.location,
            client=self.client_obj2, on_hand_qty=5,
        )

        self.api.force_authenticate(user=self.client_user)
        resp = self.api.get('/api/v1/dashboard/client/')
        alerts = resp.data['safety_stock_alerts']
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['product_name'], '상품1')

    def test_field_user_denied(self):
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.get('/api/v1/dashboard/client/')
        self.assertEqual(resp.status_code, 403)
