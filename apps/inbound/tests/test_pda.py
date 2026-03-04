"""
PDA 검수/적치 API 테스트
"""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client
from apps.inventory.models import (
    Product, ProductBarcode, Location, InventoryBalance,
)
from apps.inbound.models import InboundOrder, InboundOrderItem
from apps.history.models import InventoryTransaction


class PDATestMixin:
    """PDA 테스트 공통 데이터"""

    def setUp(self):
        self.client_obj = Client.objects.create(
            company_name='테스트 거래처',
            business_number='123-45-67890',
            contact_person='홍길동',
            contact_phone='010-1234-5678',
            contact_email='test@test.com',
            invoice_email='invoice@test.com',
        )
        self.product = Product.objects.create(barcode='P001', name='상품A')
        self.product2 = Product.objects.create(barcode='P002', name='상품B')

        # ProductBarcode 등록 (보조 바코드)
        ProductBarcode.objects.create(
            product=self.product, barcode='8801234567890', is_primary=True,
        )

        self.loc_storage = Location.objects.create(
            barcode='B9-A-03-02-01', zone_type='STORAGE',
        )
        self.loc_picking = Location.objects.create(
            barcode='B9-B-01-01-03', zone_type='PICKING',
        )
        self.loc_empty = Location.objects.create(
            barcode='B9-C-01-01-01', zone_type='STORAGE',
        )

        # FIELD 역할 유저
        self.field_user = User.objects.create_user(
            email='field@test.com', password='test1234',
            name='필드작업자', role='field', is_approved=True,
        )
        # CLIENT 역할 유저 (접근 불가)
        self.client_user = User.objects.create_user(
            email='client@test.com', password='test1234',
            name='거래처유저', role='client', is_approved=True,
        )

        self.order = InboundOrder.objects.create(
            client=self.client_obj,
            expected_date='2026-03-10',
            status='ARRIVED',
        )
        self.item1 = InboundOrderItem.objects.create(
            inbound_order=self.order, product=self.product,
            expected_qty=100,
        )
        self.item2 = InboundOrderItem.objects.create(
            inbound_order=self.order, product=self.product2,
            expected_qty=50,
        )

        self.api = APIClient()


class PDAInspectTest(PDATestMixin, TestCase):
    """검수 API 테스트"""

    def test_inspect_by_product_barcode(self):
        """ProductBarcode 테이블 바코드로 검수"""
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(
            f'/api/v1/inbound/{self.order.inbound_id}/inspect/',
            {'product_barcode': '8801234567890', 'qty': 30, 'defect_qty': 2},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['success'])

        self.item1.refresh_from_db()
        self.assertEqual(self.item1.inspected_qty, 30)
        self.assertEqual(self.item1.defect_qty, 2)

    def test_inspect_by_product_barcode_fallback(self):
        """Product.barcode 폴백 검수"""
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(
            f'/api/v1/inbound/{self.order.inbound_id}/inspect/',
            {'product_barcode': 'P002', 'qty': 20},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.item2.refresh_from_db()
        self.assertEqual(self.item2.inspected_qty, 20)

    def test_inspect_cumulative(self):
        """검수 수량 누적"""
        self.api.force_authenticate(user=self.field_user)
        self.api.post(
            f'/api/v1/inbound/{self.order.inbound_id}/inspect/',
            {'product_barcode': 'P001', 'qty': 40},
            format='json',
        )
        self.api.post(
            f'/api/v1/inbound/{self.order.inbound_id}/inspect/',
            {'product_barcode': 'P001', 'qty': 30, 'defect_qty': 1},
            format='json',
        )
        self.item1.refresh_from_db()
        self.assertEqual(self.item1.inspected_qty, 70)
        self.assertEqual(self.item1.defect_qty, 1)

    def test_first_inspect_changes_status_to_inspecting(self):
        """첫 검수 시 ARRIVED → INSPECTING"""
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(
            f'/api/v1/inbound/{self.order.inbound_id}/inspect/',
            {'product_barcode': 'P001', 'qty': 10},
            format='json',
        )
        self.assertEqual(resp.data['order_status'], 'INSPECTING')

    def test_all_inspected_auto_transition(self):
        """모든 아이템 검수 완료 시 → INSPECTED 자동 전환"""
        self.api.force_authenticate(user=self.field_user)
        self.api.post(
            f'/api/v1/inbound/{self.order.inbound_id}/inspect/',
            {'product_barcode': 'P001', 'qty': 100},
            format='json',
        )
        resp = self.api.post(
            f'/api/v1/inbound/{self.order.inbound_id}/inspect/',
            {'product_barcode': 'P002', 'qty': 50},
            format='json',
        )
        self.assertEqual(resp.data['order_status'], 'INSPECTED')
        self.assertTrue(resp.data['all_inspected'])

    def test_client_role_forbidden(self):
        """CLIENT 역할 접근 불가"""
        self.api.force_authenticate(user=self.client_user)
        resp = self.api.post(
            f'/api/v1/inbound/{self.order.inbound_id}/inspect/',
            {'product_barcode': 'P001', 'qty': 10},
            format='json',
        )
        self.assertEqual(resp.status_code, 403)

    def test_inspect_wrong_status(self):
        """PLANNED 상태에서는 검수 불가"""
        self.order.status = 'PLANNED'
        self.order.save()
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(
            f'/api/v1/inbound/{self.order.inbound_id}/inspect/',
            {'product_barcode': 'P001', 'qty': 10},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_inspect_unknown_barcode(self):
        """미등록 바코드"""
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(
            f'/api/v1/inbound/{self.order.inbound_id}/inspect/',
            {'product_barcode': 'UNKNOWN-999', 'qty': 10},
            format='json',
        )
        self.assertEqual(resp.status_code, 404)


class PDAPutawayTest(PDATestMixin, TestCase):
    """적치 API 테스트"""

    def setUp(self):
        super().setUp()
        # 검수 완료 상태로 변경
        self.order.status = 'INSPECTED'
        self.order.save()
        self.item1.inspected_qty = 95
        self.item1.defect_qty = 5
        self.item1.save()
        self.item2.inspected_qty = 50
        self.item2.save()

    def test_putaway_creates_balance_and_transaction(self):
        """적치 시 InventoryBalance + GR 트랜잭션 생성"""
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(
            f'/api/v1/inbound/{self.order.inbound_id}/putaway/',
            {
                'product_barcode': '8801234567890',
                'location_code': 'B9-A-03-02-01',
                'qty': 90,
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['success'])

        # Balance 확인
        bal = InventoryBalance.objects.get(
            product=self.product, location=self.loc_storage,
            client=self.client_obj,
        )
        self.assertEqual(bal.on_hand_qty, 90)

        # 트랜잭션 확인
        txn = InventoryTransaction.objects.filter(
            transaction_type='GR', product=self.product,
        ).first()
        self.assertIsNotNone(txn)
        self.assertEqual(txn.qty, 90)
        self.assertIn(self.order.inbound_id, txn.reference_id)

    def test_putaway_updates_item_location(self):
        """적치 로케이션이 InboundOrderItem에 기록"""
        self.api.force_authenticate(user=self.field_user)
        self.api.post(
            f'/api/v1/inbound/{self.order.inbound_id}/putaway/',
            {'product_barcode': 'P001', 'location_code': 'B9-A-03-02-01', 'qty': 50},
            format='json',
        )
        self.item1.refresh_from_db()
        self.assertEqual(self.item1.putaway_location, self.loc_storage)

    def test_putaway_all_completes_order(self):
        """모든 아이템 적치 완료 시 → PUTAWAY_COMPLETE"""
        self.api.force_authenticate(user=self.field_user)
        self.api.post(
            f'/api/v1/inbound/{self.order.inbound_id}/putaway/',
            {'product_barcode': 'P001', 'location_code': 'B9-A-03-02-01', 'qty': 90},
            format='json',
        )
        resp = self.api.post(
            f'/api/v1/inbound/{self.order.inbound_id}/putaway/',
            {'product_barcode': 'P002', 'location_code': 'B9-B-01-01-03', 'qty': 50},
            format='json',
        )
        self.assertEqual(resp.data['order_status'], 'PUTAWAY_COMPLETE')
        self.assertTrue(resp.data['all_putaway'])

    def test_putaway_location_case_insensitive(self):
        """로케이션 코드 대소문자 무관"""
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(
            f'/api/v1/inbound/{self.order.inbound_id}/putaway/',
            {'product_barcode': 'P001', 'location_code': 'b9-a-03-02-01', 'qty': 10},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)

    def test_putaway_wrong_status(self):
        """ARRIVED 상태에서는 적치 불가"""
        self.order.status = 'ARRIVED'
        self.order.save()
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(
            f'/api/v1/inbound/{self.order.inbound_id}/putaway/',
            {'product_barcode': 'P001', 'location_code': 'B9-A-03-02-01', 'qty': 10},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_client_role_forbidden(self):
        self.api.force_authenticate(user=self.client_user)
        resp = self.api.post(
            f'/api/v1/inbound/{self.order.inbound_id}/putaway/',
            {'product_barcode': 'P001', 'location_code': 'B9-A-03-02-01', 'qty': 10},
            format='json',
        )
        self.assertEqual(resp.status_code, 403)


class SuggestLocationTest(PDATestMixin, TestCase):
    """로케이션 추천 API 테스트"""

    def test_suggest_existing_sku_location(self):
        """동일 SKU 보관 로케이션 반환"""
        # 기존 재고 생성
        InventoryBalance.objects.create(
            product=self.product, location=self.loc_storage,
            client=self.client_obj, on_hand_qty=100,
        )
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.get(
            '/api/v1/inbound/suggest-location/',
            {'product_id': self.product.pk},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['suggestions']), 1)
        self.assertEqual(resp.data['suggestions'][0]['location_code'], 'B9-A-03-02-01')
        self.assertEqual(resp.data['suggestions'][0]['reason'], 'same_sku')

    def test_suggest_empty_storage(self):
        """빈 STORAGE 로케이션 반환"""
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.get(
            '/api/v1/inbound/suggest-location/',
            {'product_id': self.product.pk},
        )
        self.assertEqual(resp.status_code, 200)
        # 3개 STORAGE/PICKING 로케이션 중 빈 것들
        self.assertGreater(len(resp.data['suggestions']), 0)
        for s in resp.data['suggestions']:
            self.assertEqual(s['reason'], 'empty')

    def test_suggest_requires_product_id(self):
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.get('/api/v1/inbound/suggest-location/')
        self.assertEqual(resp.status_code, 400)

    def test_client_role_forbidden(self):
        self.api.force_authenticate(user=self.client_user)
        resp = self.api.get(
            '/api/v1/inbound/suggest-location/',
            {'product_id': self.product.pk},
        )
        self.assertEqual(resp.status_code, 403)
