"""
주문별 바코드 검수 PDA API 테스트
"""
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client
from apps.inventory.models import Product, Location, InventoryBalance
from apps.waves.models import (
    Wave, OutboundOrder, OutboundOrderItem,
    TotalPickList, TotalPickListDetail,
)
from apps.waves.services import WaveService


class InspectionTestMixin:
    """검수 테스트 공통 데이터"""

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

        # 재고 생성
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
        self.client_user = User.objects.create_user(
            email='client@test.com', password='test1234',
            name='거래처유저', role='client', is_approved=True,
        )
        self.office_user = User.objects.create_user(
            email='office@test.com', password='test1234',
            name='오피스', role='office', is_approved=True,
        )

        self.api = APIClient()

    def _create_wave_with_orders(self):
        """주문 2건 + 웨이브 생성 (각 주문: 상품A x3, 상품B x2)"""
        for i in range(2):
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


# ------------------------------------------------------------------
# 검수 대기 주문 목록
# ------------------------------------------------------------------

class InspectionListViewTest(InspectionTestMixin, TestCase):
    """GET /api/v1/waves/{wave_id}/inspection/"""

    def test_returns_allocated_orders(self):
        wave = self._create_wave_with_orders()
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.get(f'/api/v1/waves/{wave.wave_id}/inspection/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['wave_id'], wave.wave_id)
        self.assertEqual(len(resp.data['orders']), 2)

    def test_excludes_inspected_orders(self):
        wave = self._create_wave_with_orders()
        # 한 주문을 INSPECTED로 변경
        order = wave.orders.first()
        order.status = 'INSPECTED'
        order.save(update_fields=['status'])

        self.api.force_authenticate(user=self.field_user)
        resp = self.api.get(f'/api/v1/waves/{wave.wave_id}/inspection/')
        self.assertEqual(len(resp.data['orders']), 1)

    def test_returns_order_qty_info(self):
        wave = self._create_wave_with_orders()
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.get(f'/api/v1/waves/{wave.wave_id}/inspection/')
        order_data = resp.data['orders'][0]
        self.assertIn('total_qty', order_data)
        self.assertIn('inspected_total', order_data)
        self.assertEqual(order_data['total_qty'], 5)  # 3 + 2
        self.assertEqual(order_data['inspected_total'], 0)

    def test_404_for_invalid_wave(self):
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.get('/api/v1/waves/WV-INVALID/inspection/')
        self.assertEqual(resp.status_code, 404)

    def test_permission_denied_for_client_role(self):
        wave = self._create_wave_with_orders()
        self.api.force_authenticate(user=self.client_user)
        resp = self.api.get(f'/api/v1/waves/{wave.wave_id}/inspection/')
        self.assertEqual(resp.status_code, 403)


# ------------------------------------------------------------------
# 검수 상세
# ------------------------------------------------------------------

class InspectionDetailViewTest(InspectionTestMixin, TestCase):
    """GET /api/v1/waves/orders/{wms_order_id}/inspection-detail/"""

    def test_returns_order_items(self):
        wave = self._create_wave_with_orders()
        order = wave.orders.first()
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.get(
            f'/api/v1/waves/orders/{order.wms_order_id}/inspection-detail/',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['wms_order_id'], order.wms_order_id)
        self.assertEqual(len(resp.data['items']), 2)

    def test_items_show_remaining(self):
        wave = self._create_wave_with_orders()
        order = wave.orders.first()
        # 상품A 1개 검수
        item = order.items.filter(product=self.product).first()
        item.inspected_qty = 1
        item.save(update_fields=['inspected_qty'])

        self.api.force_authenticate(user=self.field_user)
        resp = self.api.get(
            f'/api/v1/waves/orders/{order.wms_order_id}/inspection-detail/',
        )
        items = resp.data['items']
        product_a = next(i for i in items if i['product_barcode'] == 'SKU-A001')
        self.assertEqual(product_a['inspected_qty'], 1)
        self.assertEqual(product_a['remaining'], 2)  # 3 - 1

    def test_404_for_invalid_order(self):
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.get(
            '/api/v1/waves/orders/WO-INVALID/inspection-detail/',
        )
        self.assertEqual(resp.status_code, 404)

    def test_error_order_not_in_wave(self):
        """웨이브 미배정 주문"""
        order = OutboundOrder.objects.create(
            source='TEST', source_order_id='NO-WAVE',
            client=self.client_obj, status='ALLOCATED',
            recipient_name='테스트', recipient_phone='010-0000-0000',
            recipient_address='서울', ordered_at=timezone.now(),
        )
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.get(
            f'/api/v1/waves/orders/{order.wms_order_id}/inspection-detail/',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['error_code'], 'ORDER_NOT_IN_WAVE')


# ------------------------------------------------------------------
# 검수 스캔
# ------------------------------------------------------------------

class InspectScanViewTest(InspectionTestMixin, TestCase):
    """POST /api/v1/waves/orders/{wms_order_id}/inspect-scan/"""

    def _scan(self, wms_order_id, barcode='SKU-A001'):
        return self.api.post(
            f'/api/v1/waves/orders/{wms_order_id}/inspect-scan/',
            {'product_barcode': barcode},
        )

    def test_scan_increments_inspected_qty(self):
        wave = self._create_wave_with_orders()
        order = wave.orders.first()
        self.api.force_authenticate(user=self.field_user)

        resp = self._scan(order.wms_order_id)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['success'])
        self.assertEqual(resp.data['inspected_qty'], 1)
        self.assertEqual(resp.data['remaining'], 2)  # 3 - 1
        self.assertFalse(resp.data['order_completed'])

    def test_multiple_scans(self):
        """동일 상품 3개 → 3번 스캔"""
        wave = self._create_wave_with_orders()
        order = wave.orders.first()
        self.api.force_authenticate(user=self.field_user)

        for i in range(3):
            resp = self._scan(order.wms_order_id)
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.data['inspected_qty'], i + 1)

        # 3번째 스캔 후 remaining = 0
        self.assertEqual(resp.data['remaining'], 0)

    def test_order_completed_all_items_inspected(self):
        """전체 품목 검수 완료 → INSPECTED"""
        wave = self._create_wave_with_orders()
        order = wave.orders.first()
        self.api.force_authenticate(user=self.field_user)

        # 상품A x3
        for _ in range(3):
            self._scan(order.wms_order_id, 'SKU-A001')

        # 상품B x2
        for i in range(2):
            resp = self._scan(order.wms_order_id, 'SKU-B002')

        self.assertTrue(resp.data['order_completed'])

        order.refresh_from_db()
        self.assertEqual(order.status, 'INSPECTED')

    def test_wave_inspected_count_incremented(self):
        wave = self._create_wave_with_orders()
        order = wave.orders.first()
        self.api.force_authenticate(user=self.field_user)

        # 주문 전체 검수
        for _ in range(3):
            self._scan(order.wms_order_id, 'SKU-A001')
        for _ in range(2):
            self._scan(order.wms_order_id, 'SKU-B002')

        wave.refresh_from_db()
        self.assertEqual(wave.inspected_count, 1)

    def test_error_wrong_product(self):
        """주문에 없는 상품 바코드"""
        wave = self._create_wave_with_orders()
        order = wave.orders.first()
        Product.objects.create(
            barcode='SKU-UNKNOWN', name='미포함상품', client=self.client_obj,
        )
        self.api.force_authenticate(user=self.field_user)

        resp = self._scan(order.wms_order_id, 'SKU-UNKNOWN')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['error_code'], 'WRONG_PRODUCT')

    def test_error_nonexistent_barcode(self):
        """존재하지 않는 바코드"""
        wave = self._create_wave_with_orders()
        order = wave.orders.first()
        self.api.force_authenticate(user=self.field_user)

        resp = self._scan(order.wms_order_id, 'NO-SUCH-BARCODE')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['error_code'], 'WRONG_PRODUCT')

    def test_error_already_complete(self):
        """이미 검수 완료된 주문"""
        wave = self._create_wave_with_orders()
        order = wave.orders.first()
        order.status = 'INSPECTED'
        order.save(update_fields=['status'])

        self.api.force_authenticate(user=self.field_user)
        resp = self._scan(order.wms_order_id)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['error_code'], 'ALREADY_COMPLETE')

    def test_error_qty_exceeded(self):
        """검수수량 초과"""
        wave = self._create_wave_with_orders()
        order = wave.orders.first()
        # 상품A qty=3, inspected_qty=3 으로 세팅
        item = order.items.filter(product=self.product).first()
        item.inspected_qty = 3
        item.save(update_fields=['inspected_qty'])

        self.api.force_authenticate(user=self.field_user)
        resp = self._scan(order.wms_order_id, 'SKU-A001')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['error_code'], 'QTY_EXCEEDED')

    def test_error_order_not_in_wave(self):
        """웨이브 미배정 주문"""
        order = OutboundOrder.objects.create(
            source='TEST', source_order_id='NO-WAVE',
            client=self.client_obj, status='ALLOCATED',
            recipient_name='테스트', recipient_phone='010-0000-0000',
            recipient_address='서울', ordered_at=timezone.now(),
        )
        OutboundOrderItem.objects.create(
            order=order, product=self.product, qty=3,
        )
        self.api.force_authenticate(user=self.field_user)
        resp = self._scan(order.wms_order_id)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['error_code'], 'ORDER_NOT_IN_WAVE')

    def test_error_order_not_found(self):
        self.api.force_authenticate(user=self.field_user)
        resp = self._scan('WO-INVALID')
        self.assertEqual(resp.status_code, 404)

    def test_permission_denied_for_client_role(self):
        wave = self._create_wave_with_orders()
        order = wave.orders.first()
        self.api.force_authenticate(user=self.client_user)
        resp = self._scan(order.wms_order_id)
        self.assertEqual(resp.status_code, 403)

    def test_signal_sent_on_completion(self):
        """검수 완료 시 order_inspected 시그널 발행"""
        from apps.waves.signals import order_inspected

        signal_received = []

        def handler(sender, **kwargs):
            signal_received.append({
                'order': kwargs['order'],
                'user': kwargs['user'],
            })

        order_inspected.connect(handler)
        try:
            wave = self._create_wave_with_orders()
            order = wave.orders.first()
            self.api.force_authenticate(user=self.field_user)

            # 전체 검수
            for _ in range(3):
                self._scan(order.wms_order_id, 'SKU-A001')
            for _ in range(2):
                self._scan(order.wms_order_id, 'SKU-B002')

            self.assertEqual(len(signal_received), 1)
            self.assertEqual(signal_received[0]['order'].pk, order.pk)
            self.assertEqual(signal_received[0]['user'].pk, self.field_user.pk)
        finally:
            order_inspected.disconnect(handler)

    def test_signal_not_sent_before_completion(self):
        """검수 미완료 시 시그널 미발행"""
        from apps.waves.signals import order_inspected

        signal_received = []

        def handler(sender, **kwargs):
            signal_received.append(True)

        order_inspected.connect(handler)
        try:
            wave = self._create_wave_with_orders()
            order = wave.orders.first()
            self.api.force_authenticate(user=self.field_user)

            # 상품A 1번만 스캔 (미완료)
            self._scan(order.wms_order_id, 'SKU-A001')

            self.assertEqual(len(signal_received), 0)
        finally:
            order_inspected.disconnect(handler)
