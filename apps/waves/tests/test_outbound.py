"""
출고 주문 모델 및 API 테스트
"""
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client, Brand
from apps.inventory.models import Product, Location, InventoryBalance
from apps.history.models import InventoryTransaction
from apps.waves.models import OutboundOrder, OutboundOrderItem, generate_wms_order_id


# ------------------------------------------------------------------
# 채번 테스트
# ------------------------------------------------------------------

class GenerateWmsOrderIdTest(TestCase):
    """WMS 주문번호 자동 채번"""

    def test_first_of_day(self):
        oid = generate_wms_order_id()
        today = timezone.localtime(timezone.now()).strftime('%Y%m%d')
        self.assertEqual(oid, f'WO-{today}-00001')

    def test_sequential(self):
        client = Client.objects.create(
            company_name='테스트', business_number='123-45-67890',
            contact_person='A', contact_phone='010-1234-5678',
            contact_email='a@a.com', invoice_email='a@a.com',
        )
        OutboundOrder.objects.create(
            wms_order_id=generate_wms_order_id(),
            source='TEST', source_order_id='T-001',
            client=client,
            recipient_name='홍길동', recipient_phone='010-0000-0000',
            recipient_address='서울', ordered_at=timezone.now(),
        )
        oid2 = generate_wms_order_id()
        self.assertTrue(oid2.endswith('-00002'))

    def test_five_digit_seq(self):
        """5자리 시퀀스 확인"""
        oid = generate_wms_order_id()
        seq_part = oid.split('-')[-1]
        self.assertEqual(len(seq_part), 5)


# ------------------------------------------------------------------
# 주문 수신 API 테스트
# ------------------------------------------------------------------

class OrderReceiveTestMixin:
    """공통 테스트 데이터"""

    def setUp(self):
        self.client_obj = Client.objects.create(
            company_name='테스트 거래처',
            business_number='123-45-67890',
            contact_person='홍길동',
            contact_phone='010-1234-5678',
            contact_email='test@test.com',
            invoice_email='invoice@test.com',
        )
        self.brand = Brand.objects.create(
            client=self.client_obj, name='테스트 브랜드',
        )
        self.product = Product.objects.create(
            barcode='SKU-A001', name='상품A', client=self.client_obj,
        )
        self.product2 = Product.objects.create(
            barcode='SKU-B002', name='상품B', client=self.client_obj,
        )
        self.location = Location.objects.create(
            barcode='LOC-A', zone_type='STORAGE',
        )
        # 재고 생성 (상품A: 100, 상품B: 50)
        InventoryBalance.objects.create(
            product=self.product, location=self.location,
            client=self.client_obj, on_hand_qty=100,
        )
        InventoryBalance.objects.create(
            product=self.product2, location=self.location,
            client=self.client_obj, on_hand_qty=50,
        )
        self.user = User.objects.create_user(
            email='admin@test.com', password='test1234',
            name='관리자', role='admin', is_approved=True,
        )
        self.api = APIClient()
        self.api.force_authenticate(user=self.user)

    def _order_payload(self, **overrides):
        payload = {
            'source': 'SABANGNET',
            'source_order_id': 'SB-20260303-001',
            'client_id': self.client_obj.pk,
            'brand_id': self.brand.pk,
            'order_type': 'B2C',
            'ordered_at': '2026-03-03T09:00:00+09:00',
            'shipping': {
                'recipient_name': '홍길동',
                'recipient_phone': '010-1234-5678',
                'recipient_address': '서울시 강남구 테헤란로 123',
                'recipient_zip': '06234',
                'shipping_memo': '부재시 경비실',
            },
            'items': [
                {'sku': 'SKU-A001', 'qty': 2, 'source_item_id': 'SB-ITEM-001'},
            ],
        }
        payload.update(overrides)
        return payload


class OrderReceiveTest(OrderReceiveTestMixin, TestCase):
    """주문 수신 API"""

    def test_receive_creates_order(self):
        """정상 주문 수신 → OutboundOrder 생성"""
        resp = self.api.post(
            '/api/v1/orders/', self._order_payload(), format='json',
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.data['wms_order_id'].startswith('WO-'))
        self.assertEqual(resp.data['source'], 'SABANGNET')
        self.assertEqual(resp.data['recipient_name'], '홍길동')

    def test_receive_creates_items(self):
        """주문 품목 생성 확인"""
        resp = self.api.post(
            '/api/v1/orders/',
            self._order_payload(items=[
                {'sku': 'SKU-A001', 'qty': 2},
                {'sku': 'SKU-B002', 'qty': 3},
            ]),
            format='json',
        )
        self.assertEqual(resp.status_code, 201)
        order = OutboundOrder.objects.get(pk=resp.data['id'])
        self.assertEqual(order.items.count(), 2)

    def test_receive_with_allocation_success(self):
        """재고 충분 → ALLOCATED 상태"""
        resp = self.api.post(
            '/api/v1/orders/', self._order_payload(), format='json',
        )
        self.assertEqual(resp.data['status'], 'ALLOCATED')

        # 할당 트랜잭션 확인
        txn = InventoryTransaction.objects.filter(
            transaction_type='ALC', product=self.product,
        ).first()
        self.assertIsNotNone(txn)
        self.assertEqual(txn.qty, 2)

        # InventoryBalance 할당 확인
        bal = InventoryBalance.objects.get(
            product=self.product, location=self.location,
        )
        self.assertEqual(bal.allocated_qty, 2)

    def test_receive_with_allocation_failure(self):
        """재고 부족 → HELD 상태"""
        resp = self.api.post(
            '/api/v1/orders/',
            self._order_payload(items=[
                {'sku': 'SKU-A001', 'qty': 999},
            ]),
            format='json',
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['status'], 'HELD')
        self.assertIn('상품A', resp.data['hold_reason'])

    def test_receive_held_no_partial_allocation(self):
        """재고 부족 시 부분 할당 없음 (전체 롤백)"""
        resp = self.api.post(
            '/api/v1/orders/',
            self._order_payload(items=[
                {'sku': 'SKU-A001', 'qty': 2},      # 가용 100 — OK
                {'sku': 'SKU-B002', 'qty': 999},     # 가용 50 — FAIL
            ]),
            format='json',
        )
        self.assertEqual(resp.data['status'], 'HELD')

        # 상품A 할당도 롤백되어야 함
        bal_a = InventoryBalance.objects.get(product=self.product)
        self.assertEqual(bal_a.allocated_qty, 0)

    def test_receive_unknown_sku(self):
        """미등록 SKU"""
        resp = self.api.post(
            '/api/v1/orders/',
            self._order_payload(items=[
                {'sku': 'UNKNOWN-SKU', 'qty': 1},
            ]),
            format='json',
        )
        self.assertEqual(resp.status_code, 404)

    def test_receive_unknown_client(self):
        resp = self.api.post(
            '/api/v1/orders/',
            self._order_payload(client_id=99999),
            format='json',
        )
        self.assertEqual(resp.status_code, 404)

    def test_receive_brand_mismatch(self):
        """다른 거래처의 브랜드"""
        other_client = Client.objects.create(
            company_name='다른 거래처', business_number='999-99-99999',
            contact_person='A', contact_phone='010-0000-0000',
            contact_email='o@o.com', invoice_email='o@o.com',
        )
        other_brand = Brand.objects.create(
            client=other_client, name='다른 브랜드',
        )
        resp = self.api.post(
            '/api/v1/orders/',
            self._order_payload(brand_id=other_brand.pk),
            format='json',
        )
        self.assertEqual(resp.status_code, 404)

    def test_receive_without_brand(self):
        """브랜드 없이 주문 수신"""
        payload = self._order_payload()
        payload.pop('brand_id')
        resp = self.api.post('/api/v1/orders/', payload, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertIsNone(resp.data['brand'])

    def test_receive_missing_items(self):
        """품목 없는 요청"""
        resp = self.api.post(
            '/api/v1/orders/',
            self._order_payload(items=[]),
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_wms_order_id_auto_generated(self):
        """wms_order_id 자동 생성"""
        resp = self.api.post(
            '/api/v1/orders/', self._order_payload(), format='json',
        )
        order = OutboundOrder.objects.get(pk=resp.data['id'])
        today = timezone.localtime(timezone.now()).strftime('%Y%m%d')
        self.assertTrue(order.wms_order_id.startswith(f'WO-{today}-'))


# ------------------------------------------------------------------
# 주문 취소 API 테스트
# ------------------------------------------------------------------

class OrderCancelTest(OrderReceiveTestMixin, TestCase):
    """주문 취소 API"""

    def _create_allocated_order(self):
        """할당 완료 주문 생성"""
        resp = self.api.post(
            '/api/v1/orders/', self._order_payload(), format='json',
        )
        self.assertEqual(resp.data['status'], 'ALLOCATED')
        return resp.data['wms_order_id']

    def test_cancel_deallocates_stock(self):
        """취소 시 할당 해제"""
        wms_id = self._create_allocated_order()

        # 할당 확인
        bal = InventoryBalance.objects.get(product=self.product)
        self.assertEqual(bal.allocated_qty, 2)

        # 취소
        resp = self.api.post(f'/api/v1/orders/{wms_id}/cancel/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'CANCELLED')

        # 할당 해제 확인
        bal.refresh_from_db()
        self.assertEqual(bal.allocated_qty, 0)

    def test_cancel_held_order(self):
        """HELD 주문 취소"""
        resp = self.api.post(
            '/api/v1/orders/',
            self._order_payload(items=[
                {'sku': 'SKU-A001', 'qty': 999},
            ]),
            format='json',
        )
        wms_id = resp.data['wms_order_id']

        resp = self.api.post(f'/api/v1/orders/{wms_id}/cancel/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'CANCELLED')

    def test_cancel_already_shipped(self):
        """출고완료 상태 취소 불가"""
        wms_id = self._create_allocated_order()
        order = OutboundOrder.objects.get(wms_order_id=wms_id)
        order.status = 'SHIPPED'
        order.save()

        resp = self.api.post(f'/api/v1/orders/{wms_id}/cancel/')
        self.assertEqual(resp.status_code, 400)

    def test_cancel_already_cancelled(self):
        """이미 취소된 주문"""
        wms_id = self._create_allocated_order()
        self.api.post(f'/api/v1/orders/{wms_id}/cancel/')

        resp = self.api.post(f'/api/v1/orders/{wms_id}/cancel/')
        self.assertEqual(resp.status_code, 400)

    def test_cancel_not_found(self):
        resp = self.api.post('/api/v1/orders/WO-99999999-00000/cancel/')
        self.assertEqual(resp.status_code, 404)

    def test_cancel_creates_dealloc_transaction(self):
        """취소 시 ALC_R 트랜잭션 생성"""
        wms_id = self._create_allocated_order()
        self.api.post(f'/api/v1/orders/{wms_id}/cancel/')

        txn = InventoryTransaction.objects.filter(
            transaction_type='ALC_R', product=self.product,
        ).first()
        self.assertIsNotNone(txn)
        self.assertEqual(txn.qty, 2)
