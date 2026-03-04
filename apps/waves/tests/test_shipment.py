"""
출고 확정 API 테스트
"""
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client
from apps.inventory.models import Product, Location, InventoryBalance
from apps.inventory.services import InventoryService
from apps.history.models import InventoryTransaction
from apps.waves.models import (
    Wave, OutboundOrder, OutboundOrderItem,
    TotalPickList, TotalPickListDetail,
)
from apps.waves.services import WaveService, ShipmentService


class ShipmentTestMixin:
    """출고 테스트 공통 데이터"""

    def setUp(self):
        self.client_obj = Client.objects.create(
            company_name='테스트 거래처',
            business_number='123-45-67890',
            contact_person='홍길동',
            contact_phone='010-1234-5678',
            contact_email='test@test.com',
            invoice_email='invoice@test.com',
        )
        self.product = Product.objects.create(
            barcode='SKU-A001', name='상품A', client=self.client_obj,
        )
        self.product2 = Product.objects.create(
            barcode='SKU-B002', name='상품B', client=self.client_obj,
        )
        self.loc_storage = Location.objects.create(
            barcode='STOR-01', zone_type='STORAGE',
        )
        self.loc_storage2 = Location.objects.create(
            barcode='STOR-02', zone_type='STORAGE',
        )
        self.loc_outbound = Location.objects.create(
            barcode='OUT-01', zone_type='OUTBOUND_STAGING',
        )

        # 보관존 재고
        InventoryBalance.objects.create(
            product=self.product, location=self.loc_storage,
            client=self.client_obj, on_hand_qty=100, allocated_qty=10,
        )
        InventoryBalance.objects.create(
            product=self.product2, location=self.loc_storage2,
            client=self.client_obj, on_hand_qty=50, allocated_qty=5,
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

        self.api = APIClient()

    def _create_wave_with_orders(self, num_orders=2):
        """주문 + 웨이브 생성 (각 주문: 상품A x3, 상품B x2)"""
        for i in range(num_orders):
            order = OutboundOrder.objects.create(
                source='TEST', source_order_id=f'T-{i:03d}',
                client=self.client_obj, status='ALLOCATED',
                recipient_name=f'수취인{i}', recipient_phone='010-0000-0000',
                recipient_address='서울', ordered_at=timezone.now(),
            )
            OutboundOrderItem.objects.create(
                order=order, product=self.product, qty=3,
            )
            OutboundOrderItem.objects.create(
                order=order, product=self.product2, qty=2,
            )
        return WaveService.create_wave(
            wave_time='09:00', created_by=self.office_user,
        )

    def _setup_outbound_stock(self, wave):
        """출고존에 재고 배치 (피킹 완료 상태 시뮬레이션)"""
        total_a = sum(
            item.qty for order in wave.orders.all()
            for item in order.items.filter(product=self.product)
        )
        total_b = sum(
            item.qty for order in wave.orders.all()
            for item in order.items.filter(product=self.product2)
        )

        if total_a > 0:
            InventoryBalance.objects.update_or_create(
                product=self.product, location=wave.outbound_zone,
                client=self.client_obj,
                defaults={'on_hand_qty': total_a},
            )
        if total_b > 0:
            InventoryBalance.objects.update_or_create(
                product=self.product2, location=wave.outbound_zone,
                client=self.client_obj,
                defaults={'on_hand_qty': total_b},
            )

    def _make_inspected(self, order):
        """주문을 INSPECTED 상태로 변경"""
        order.status = 'INSPECTED'
        order.save(update_fields=['status'])


# ------------------------------------------------------------------
# ShipmentService 단위 테스트
# ------------------------------------------------------------------

class ShipmentServiceTest(ShipmentTestMixin, TestCase):
    """ShipmentService.confirm_shipment() 테스트"""

    def test_confirm_shipment_basic(self):
        wave = self._create_wave_with_orders(num_orders=1)
        self._setup_outbound_stock(wave)
        order = wave.orders.first()
        self._make_inspected(order)

        result = ShipmentService.confirm_shipment(
            order=order,
            tracking_number='TRACK-001',
            performed_by=self.field_user,
        )

        result.refresh_from_db()
        self.assertEqual(result.status, 'SHIPPED')
        self.assertEqual(result.tracking_number, 'TRACK-001')
        self.assertIsNotNone(result.shipped_at)

    def test_shipped_count_incremented(self):
        wave = self._create_wave_with_orders(num_orders=2)
        self._setup_outbound_stock(wave)
        order = wave.orders.first()
        self._make_inspected(order)

        ShipmentService.confirm_shipment(order=order, performed_by=self.field_user)

        wave.refresh_from_db()
        self.assertEqual(wave.shipped_count, 1)

    def test_outbound_stock_decreased(self):
        """출고존 재고 차감 확인"""
        wave = self._create_wave_with_orders(num_orders=1)
        self._setup_outbound_stock(wave)
        order = wave.orders.first()
        self._make_inspected(order)

        # 출고 전 재고
        bal_a_before = InventoryBalance.objects.get(
            product=self.product, location=wave.outbound_zone,
        ).on_hand_qty

        ShipmentService.confirm_shipment(order=order, performed_by=self.field_user)

        bal_a = InventoryBalance.objects.get(
            product=self.product, location=wave.outbound_zone,
        )
        self.assertEqual(bal_a.on_hand_qty, bal_a_before - 3)

    def test_ship_stock_creates_gi_transaction(self):
        """GI 트랜잭션 생성 확인"""
        wave = self._create_wave_with_orders(num_orders=1)
        self._setup_outbound_stock(wave)
        order = wave.orders.first()
        self._make_inspected(order)

        gi_before = InventoryTransaction.objects.filter(
            transaction_type='GI',
        ).count()

        ShipmentService.confirm_shipment(order=order, performed_by=self.field_user)

        gi_after = InventoryTransaction.objects.filter(
            transaction_type='GI',
        ).count()
        # 2 items → 2 GI transactions
        self.assertEqual(gi_after - gi_before, 2)

    def test_error_not_inspected(self):
        """INSPECTED 아닌 주문 → ValueError"""
        wave = self._create_wave_with_orders(num_orders=1)
        order = wave.orders.first()
        # ALLOCATED 상태 그대로

        with self.assertRaises(ValueError) as ctx:
            ShipmentService.confirm_shipment(order=order)
        self.assertIn('INSPECTED', str(ctx.exception))

    def test_error_no_wave(self):
        """웨이브 미배정 주문 → ValueError"""
        order = OutboundOrder.objects.create(
            source='TEST', source_order_id='NO-WAVE',
            client=self.client_obj, status='INSPECTED',
            recipient_name='테스트', recipient_phone='010-0000-0000',
            recipient_address='서울', ordered_at=timezone.now(),
        )
        with self.assertRaises(ValueError) as ctx:
            ShipmentService.confirm_shipment(order=order)
        self.assertIn('웨이브', str(ctx.exception))

    def test_tracking_number_optional(self):
        """tracking_number 미제공 시에도 정상 처리"""
        wave = self._create_wave_with_orders(num_orders=1)
        self._setup_outbound_stock(wave)
        order = wave.orders.first()
        self._make_inspected(order)

        ShipmentService.confirm_shipment(order=order, performed_by=self.field_user)

        order.refresh_from_db()
        self.assertEqual(order.status, 'SHIPPED')
        self.assertEqual(order.tracking_number, '')


# ------------------------------------------------------------------
# 웨이브 완료 테스트
# ------------------------------------------------------------------

class WaveCompletionTest(ShipmentTestMixin, TestCase):
    """웨이브 완료 + 잔여 재고 복귀 테스트"""

    def test_wave_completed_when_all_shipped(self):
        wave = self._create_wave_with_orders(num_orders=2)
        self._setup_outbound_stock(wave)

        for order in wave.orders.all():
            self._make_inspected(order)
            ShipmentService.confirm_shipment(
                order=order, performed_by=self.field_user,
            )

        wave.refresh_from_db()
        self.assertEqual(wave.status, 'COMPLETED')
        self.assertIsNotNone(wave.completed_at)
        self.assertEqual(wave.shipped_count, 2)

    def test_wave_not_completed_if_partial(self):
        wave = self._create_wave_with_orders(num_orders=2)
        self._setup_outbound_stock(wave)

        # 1건만 출고
        order = wave.orders.first()
        self._make_inspected(order)
        ShipmentService.confirm_shipment(
            order=order, performed_by=self.field_user,
        )

        wave.refresh_from_db()
        self.assertNotEqual(wave.status, 'COMPLETED')

    def test_leftover_stock_returned_to_storage(self):
        """출고존 잔여 재고 → 보관존 복귀"""
        wave = self._create_wave_with_orders(num_orders=1)
        # 출고존에 주문수량보다 넉넉하게 재고 배치 (잉여분 발생)
        InventoryBalance.objects.update_or_create(
            product=self.product, location=wave.outbound_zone,
            client=self.client_obj,
            defaults={'on_hand_qty': 10},  # 주문은 3개인데 10개
        )
        InventoryBalance.objects.update_or_create(
            product=self.product2, location=wave.outbound_zone,
            client=self.client_obj,
            defaults={'on_hand_qty': 5},  # 주문은 2개인데 5개
        )

        order = wave.orders.first()
        self._make_inspected(order)
        ShipmentService.confirm_shipment(
            order=order, performed_by=self.field_user,
        )

        wave.refresh_from_db()
        self.assertEqual(wave.status, 'COMPLETED')

        # 출고존 잔여 → 0
        outbound_a = InventoryBalance.objects.get(
            product=self.product, location=wave.outbound_zone,
        )
        self.assertEqual(outbound_a.on_hand_qty, 0)

        # 보관존에 잔여분 복귀 확인 (원래 100 + 복귀 7)
        storage_a = InventoryBalance.objects.get(
            product=self.product, location=self.loc_storage,
        )
        self.assertEqual(storage_a.on_hand_qty, 107)

    def test_leftover_creates_wv_rtn_transaction(self):
        """잔여 재고 복귀 시 WV_RTN 트랜잭션 생성"""
        wave = self._create_wave_with_orders(num_orders=1)
        InventoryBalance.objects.update_or_create(
            product=self.product, location=wave.outbound_zone,
            client=self.client_obj,
            defaults={'on_hand_qty': 5},
        )
        InventoryBalance.objects.update_or_create(
            product=self.product2, location=wave.outbound_zone,
            client=self.client_obj,
            defaults={'on_hand_qty': 2},
        )

        order = wave.orders.first()
        self._make_inspected(order)
        ShipmentService.confirm_shipment(
            order=order, performed_by=self.field_user,
        )

        rtn_txns = InventoryTransaction.objects.filter(
            transaction_type='WV_RTN',
            reference_type='WAVE',
        )
        # 상품A: 5-3=2 잔여 → 복귀 1건, 상품B: 2-2=0 잔여 → 복귀 없음
        self.assertEqual(rtn_txns.count(), 1)


# ------------------------------------------------------------------
# ShipConfirmView API 테스트
# ------------------------------------------------------------------

class ShipConfirmViewTest(ShipmentTestMixin, TestCase):
    """POST /api/v1/waves/orders/{wms_order_id}/ship/"""

    def test_ship_single_order(self):
        wave = self._create_wave_with_orders(num_orders=1)
        self._setup_outbound_stock(wave)
        order = wave.orders.first()
        self._make_inspected(order)

        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(
            f'/api/v1/waves/orders/{order.wms_order_id}/ship/',
            {'tracking_number': 'TRACK-123'},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['success'])
        self.assertEqual(resp.data['status'], 'SHIPPED')
        self.assertEqual(resp.data['tracking_number'], 'TRACK-123')

    def test_ship_without_tracking_number(self):
        wave = self._create_wave_with_orders(num_orders=1)
        self._setup_outbound_stock(wave)
        order = wave.orders.first()
        self._make_inspected(order)

        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(
            f'/api/v1/waves/orders/{order.wms_order_id}/ship/', {},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['success'])

    def test_error_not_inspected(self):
        wave = self._create_wave_with_orders(num_orders=1)
        order = wave.orders.first()
        # ALLOCATED 상태

        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(
            f'/api/v1/waves/orders/{order.wms_order_id}/ship/', {},
        )
        self.assertEqual(resp.status_code, 400)

    def test_error_not_found(self):
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post('/api/v1/waves/orders/WO-INVALID/ship/', {})
        self.assertEqual(resp.status_code, 404)

    def test_permission_denied_for_client_role(self):
        wave = self._create_wave_with_orders(num_orders=1)
        order = wave.orders.first()
        self._make_inspected(order)

        self.api.force_authenticate(user=self.client_user)
        resp = self.api.post(
            f'/api/v1/waves/orders/{order.wms_order_id}/ship/', {},
        )
        self.assertEqual(resp.status_code, 403)


# ------------------------------------------------------------------
# BulkShipView API 테스트
# ------------------------------------------------------------------

class BulkShipViewTest(ShipmentTestMixin, TestCase):
    """POST /api/v1/waves/{wave_id}/bulk-ship/"""

    def test_bulk_ship_all_inspected(self):
        wave = self._create_wave_with_orders(num_orders=2)
        self._setup_outbound_stock(wave)

        for order in wave.orders.all():
            self._make_inspected(order)

        self.api.force_authenticate(user=self.office_user)
        resp = self.api.post(f'/api/v1/waves/{wave.wave_id}/bulk-ship/')

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['success'])
        self.assertEqual(resp.data['shipped_count'], 2)
        self.assertEqual(len(resp.data['errors']), 0)
        self.assertEqual(resp.data['wave_status'], 'COMPLETED')

    def test_bulk_ship_partial(self):
        """일부만 INSPECTED → 해당 건만 출고"""
        wave = self._create_wave_with_orders(num_orders=2)
        self._setup_outbound_stock(wave)

        # 1건만 INSPECTED
        order = wave.orders.first()
        self._make_inspected(order)

        self.api.force_authenticate(user=self.office_user)
        resp = self.api.post(f'/api/v1/waves/{wave.wave_id}/bulk-ship/')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['shipped_count'], 1)

    def test_bulk_ship_no_inspected_orders(self):
        wave = self._create_wave_with_orders(num_orders=1)

        self.api.force_authenticate(user=self.office_user)
        resp = self.api.post(f'/api/v1/waves/{wave.wave_id}/bulk-ship/')

        self.assertEqual(resp.status_code, 400)
        self.assertIn('INSPECTED', resp.data['detail'])

    def test_wave_not_found(self):
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.post('/api/v1/waves/WV-INVALID/bulk-ship/')
        self.assertEqual(resp.status_code, 404)

    def test_permission_denied_for_field_user(self):
        """일괄 출고는 OFFICE 이상만 가능"""
        wave = self._create_wave_with_orders(num_orders=1)

        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(f'/api/v1/waves/{wave.wave_id}/bulk-ship/')
        self.assertEqual(resp.status_code, 403)

    def test_permission_allowed_for_office_user(self):
        wave = self._create_wave_with_orders(num_orders=1)
        self._setup_outbound_stock(wave)
        order = wave.orders.first()
        self._make_inspected(order)

        self.api.force_authenticate(user=self.office_user)
        resp = self.api.post(f'/api/v1/waves/{wave.wave_id}/bulk-ship/')
        self.assertEqual(resp.status_code, 200)
