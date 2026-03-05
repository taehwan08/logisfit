"""
inspection → waves 브릿지 로직 테스트

OutboundOrder가 있으면 waves 검수 로직, 없으면 기존 inspection Order fallback.
"""
import json
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.clients.models import Client
from apps.inventory.models import Product, Location, InventoryBalance
from apps.waves.models import Wave, OutboundOrder, OutboundOrderItem
from apps.waves.services import WaveService
from apps.inspection.models import Order, OrderProduct, InspectionLog


class BridgeTestMixin:
    """브릿지 테스트 공통 데이터"""

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

        InventoryBalance.objects.create(
            product=self.product, location=self.loc_storage,
            client=self.client_obj, on_hand_qty=100, allocated_qty=10,
        )
        InventoryBalance.objects.create(
            product=self.product2, location=self.loc_storage2,
            client=self.client_obj, on_hand_qty=50, allocated_qty=5,
        )

        self.user = User.objects.create_user(
            email='field@test.com', password='test1234',
            name='작업자', role='field', is_approved=True,
        )
        self.office_user = User.objects.create_user(
            email='office@test.com', password='test1234',
            name='오피스', role='office', is_approved=True,
        )

    def _create_outbound_order(self, tracking_number='TRK-001', status='ALLOCATED'):
        """OutboundOrder + items 생성 (상품A x2, 상품B x1)"""
        order = OutboundOrder.objects.create(
            source='TEST', source_order_id='T-001',
            client=self.client_obj, status=status,
            recipient_name='수취인', recipient_phone='010-0000-0000',
            recipient_address='서울 강남구', ordered_at=timezone.now(),
            tracking_number=tracking_number,
        )
        OutboundOrderItem.objects.create(
            order=order, product=self.product, qty=2,
        )
        OutboundOrderItem.objects.create(
            order=order, product=self.product2, qty=1,
        )
        return order

    def _create_outbound_in_wave(self, tracking_number='TRK-001'):
        """웨이브에 배정된 OutboundOrder 생성"""
        order = OutboundOrder.objects.create(
            source='TEST', source_order_id='T-001',
            client=self.client_obj, status='ALLOCATED',
            recipient_name='수취인', recipient_phone='010-0000-0000',
            recipient_address='서울 강남구', ordered_at=timezone.now(),
            tracking_number=tracking_number,
        )
        OutboundOrderItem.objects.create(
            order=order, product=self.product, qty=2,
        )
        OutboundOrderItem.objects.create(
            order=order, product=self.product2, qty=1,
        )
        wave = WaveService.create_wave(
            wave_time='09:00', created_by=self.office_user,
        )
        order.refresh_from_db()
        return order, wave

    def _create_legacy_order(self, tracking_number='TRK-LEGACY'):
        """기존 inspection Order 생성"""
        order = Order.objects.create(
            tracking_number=tracking_number,
            seller='레거시판매처',
            receiver_name='수령인',
            receiver_phone='010-1111-1111',
            receiver_address='서울',
        )
        OrderProduct.objects.create(
            order=order, barcode='SKU-A001',
            product_name='상품A', quantity=1,
        )
        return order


# ------------------------------------------------------------------
# get_order 브릿지 테스트
# ------------------------------------------------------------------

class GetOrderBridgeTest(BridgeTestMixin, TestCase):
    """get_order: OutboundOrder 우선, fallback to inspection Order"""

    def test_outbound_order_found(self):
        """1. OutboundOrder가 있으면 WMS 데이터로 응답"""
        self._create_outbound_order('TRK-WMS')
        self.client.force_login(self.user)

        resp = self.client.get('/inspection/api/orders/TRK-WMS/')
        data = resp.json()

        self.assertTrue(data['success'])
        self.assertEqual(data['alert_code'], '정상')
        self.assertEqual(data['source'], 'wms')
        self.assertEqual(data['order']['tracking_number'], 'TRK-WMS')
        self.assertEqual(data['order']['seller'], 'TEST')
        self.assertEqual(data['order']['receiver_name'], '수취인')
        self.assertEqual(data['order']['status'], '대기중')
        self.assertEqual(len(data['products']), 2)

    def test_outbound_order_inspected_returns_already_done(self):
        """2. OutboundOrder가 INSPECTED이면 기처리배송"""
        self._create_outbound_order('TRK-DONE', status='INSPECTED')
        self.client.force_login(self.user)

        resp = self.client.get('/inspection/api/orders/TRK-DONE/')
        data = resp.json()

        self.assertTrue(data['success'])
        self.assertEqual(data['alert_code'], '기처리배송')
        self.assertEqual(data['order']['status'], '완료')

    def test_fallback_to_legacy_order(self):
        """3. OutboundOrder 없으면 inspection Order fallback"""
        self._create_legacy_order('TRK-LEGACY')
        self.client.force_login(self.user)

        resp = self.client.get('/inspection/api/orders/TRK-LEGACY/')
        data = resp.json()

        self.assertTrue(data['success'])
        self.assertEqual(data['alert_code'], '정상')
        self.assertNotIn('source', data)  # legacy에는 source 없음
        self.assertEqual(data['order']['seller'], '레거시판매처')

    def test_not_found_returns_unregistered(self):
        """4. 둘 다 없으면 송장번호미등록"""
        self.client.force_login(self.user)

        resp = self.client.get('/inspection/api/orders/UNKNOWN/')
        data = resp.json()

        self.assertFalse(data['success'])
        self.assertEqual(data['alert_code'], '송장번호미등록')

    def test_inspection_log_created_for_outbound(self):
        """12. OutboundOrder 경로에서도 InspectionLog 생성"""
        self._create_outbound_order('TRK-LOG')
        self.client.force_login(self.user)

        self.client.get('/inspection/api/orders/TRK-LOG/')

        log = InspectionLog.objects.filter(tracking_number='TRK-LOG').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.scan_type, '송장')
        self.assertEqual(log.alert_code, '정상')


# ------------------------------------------------------------------
# scan_product 브릿지 테스트
# ------------------------------------------------------------------

class ScanProductBridgeTest(BridgeTestMixin, TestCase):
    """scan_product: OutboundOrder 우선, fallback to inspection Order"""

    def _scan(self, tracking_number, barcode):
        return self.client.post(
            '/inspection/api/scan/product/',
            json.dumps({'tracking_number': tracking_number, 'barcode': barcode}),
            content_type='application/json',
        )

    def test_outbound_scan_success(self):
        """5. OutboundOrder 바코드 스캔 → inspected_qty 증가"""
        order, wave = self._create_outbound_in_wave('TRK-SCAN')
        self.client.force_login(self.user)

        resp = self._scan('TRK-SCAN', 'SKU-A001')
        data = resp.json()

        self.assertTrue(data['success'])
        self.assertIn(data['alert_code'], ('숫자', '정상'))
        self.assertEqual(data['source'], 'wms')
        self.assertFalse(data['all_completed'])

        # inspected_qty 확인
        item = order.items.get(product=self.product)
        item.refresh_from_db()
        self.assertEqual(item.inspected_qty, 1)

    @patch('apps.waves.signals.order_inspected.send')
    def test_outbound_scan_complete(self, mock_signal):
        """6. 전체 완료 시 INSPECTED + order_inspected 시그널"""
        order, wave = self._create_outbound_in_wave('TRK-COMP')
        self.client.force_login(self.user)

        # 상품A x2
        self._scan('TRK-COMP', 'SKU-A001')
        self._scan('TRK-COMP', 'SKU-A001')
        # 상품B x1
        resp = self._scan('TRK-COMP', 'SKU-B002')
        data = resp.json()

        self.assertTrue(data['success'])
        self.assertEqual(data['alert_code'], '완료')
        self.assertTrue(data['all_completed'])

        order.refresh_from_db()
        self.assertEqual(order.status, 'INSPECTED')

        # 시그널 발행 확인
        self.assertTrue(mock_signal.called)

        # wave inspected_count 증가 확인
        wave.refresh_from_db()
        self.assertEqual(wave.inspected_count, 1)

    def test_outbound_scan_wrong_barcode(self):
        """7. 잘못된 바코드 → 상품오류"""
        self._create_outbound_in_wave('TRK-WRONG')
        self.client.force_login(self.user)

        resp = self._scan('TRK-WRONG', 'NONEXISTENT')
        data = resp.json()

        self.assertFalse(data['success'])
        self.assertEqual(data['alert_code'], '상품오류')

    def test_outbound_scan_qty_exceeded(self):
        """8. 수량 초과 → 중복스캔"""
        order, wave = self._create_outbound_in_wave('TRK-DUP')
        self.client.force_login(self.user)

        # 상품B qty=1, 2번 스캔
        self._scan('TRK-DUP', 'SKU-B002')
        resp = self._scan('TRK-DUP', 'SKU-B002')
        data = resp.json()

        self.assertFalse(data['success'])
        self.assertEqual(data['alert_code'], '중복스캔')

    def test_fallback_to_legacy_scan(self):
        """9. OutboundOrder 없으면 inspection Order fallback"""
        legacy = self._create_legacy_order('TRK-LEG')
        self.client.force_login(self.user)

        resp = self._scan('TRK-LEG', 'SKU-A001')
        data = resp.json()

        self.assertTrue(data['success'])
        self.assertNotIn('source', data)  # legacy에는 source 없음

        # scanned_quantity 증가 확인
        op = legacy.products.first()
        op.refresh_from_db()
        self.assertEqual(op.scanned_quantity, 1)

    def test_scan_creates_inspection_log(self):
        """InspectionLog가 OutboundOrder 스캔에서도 생성"""
        self._create_outbound_in_wave('TRK-SLOG')
        self.client.force_login(self.user)

        self._scan('TRK-SLOG', 'SKU-A001')

        log = InspectionLog.objects.filter(
            tracking_number='TRK-SLOG', scan_type='상품',
        ).first()
        self.assertIsNotNone(log)
        self.assertIn(log.alert_code, ('숫자', '정상'))


# ------------------------------------------------------------------
# complete_inspection 브릿지 테스트
# ------------------------------------------------------------------

class CompleteInspectionBridgeTest(BridgeTestMixin, TestCase):
    """complete_inspection: OutboundOrder 우선, fallback to inspection Order"""

    def _complete(self, tracking_number):
        return self.client.post(
            '/inspection/api/scan/complete/',
            json.dumps({'tracking_number': tracking_number}),
            content_type='application/json',
        )

    @patch('apps.waves.signals.order_inspected.send')
    def test_outbound_complete_success(self, mock_signal):
        """10. OutboundOrder 완료 처리"""
        order, wave = self._create_outbound_in_wave('TRK-FIN')
        self.client.force_login(self.user)

        # 모든 품목 수량 채우기
        for item in order.items.all():
            item.inspected_qty = item.qty
            item.save(update_fields=['inspected_qty'])

        resp = self._complete('TRK-FIN')
        data = resp.json()

        self.assertTrue(data['success'])
        self.assertIn('검수가 완료', data['message'])

        order.refresh_from_db()
        self.assertEqual(order.status, 'INSPECTED')

        # 시그널 발행 확인
        self.assertTrue(mock_signal.called)

    def test_outbound_complete_incomplete_items(self):
        """11. 미완료 상품 있으면 실패"""
        self._create_outbound_in_wave('TRK-INC')
        self.client.force_login(self.user)

        resp = self._complete('TRK-INC')
        data = resp.json()

        self.assertFalse(data['success'])
        self.assertIn('스캔하지 않은 상품', data['message'])
