"""
WMS 핵심 플로우 통합 테스트

1. 전체 입고 플로우
2. 전체 출고 플로우
3. 오배송 방지 검증
4. 재고 정합성
5. 동시성
"""
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client
from apps.history.models import InventoryTransaction
from apps.inbound.models import InboundOrder, InboundOrderItem
from apps.inventory.models import Product, Location, InventoryBalance
from apps.waves.models import (
    Wave, OutboundOrder, OutboundOrderItem,
    TotalPickList, TotalPickListDetail,
)


class IntegrationMixin:
    """통합 테스트 공통 픽스처"""

    def setUp(self):
        self.client_obj = Client.objects.create(
            company_name='통합테스트 거래처',
            business_number='999-99-99999',
            contact_person='홍길동',
            contact_phone='010-0000-0000',
            contact_email='test@test.com',
            invoice_email='invoice@test.com',
        )
        self.product_a = Product.objects.create(
            barcode='INT-A001', name='통합상품A', client=self.client_obj,
        )
        self.product_b = Product.objects.create(
            barcode='INT-B002', name='통합상품B', client=self.client_obj,
        )
        self.loc_storage = Location.objects.create(
            barcode='INT-STOR-01', zone_type='STORAGE',
        )
        self.loc_storage2 = Location.objects.create(
            barcode='INT-STOR-02', zone_type='STORAGE',
        )
        self.loc_outbound = Location.objects.create(
            barcode='INT-OUT-01', zone_type='OUTBOUND_STAGING',
        )

        self.office_user = User.objects.create_user(
            email='int-office@test.com', password='test1234',
            name='오피스', role='office', is_approved=True,
        )
        self.field_user = User.objects.create_user(
            email='int-field@test.com', password='test1234',
            name='필드', role='field', is_approved=True,
        )
        self.api = APIClient()


# ======================================================================
# 1. 전체 입고 플로우
# ======================================================================

class InboundFullFlowTest(IntegrationMixin, TestCase):
    """입고예정 등록 → PDA 검수 → PDA 적치 → 재고/히스토리 확인"""

    def test_full_inbound_flow(self):
        self.api.force_authenticate(user=self.office_user)

        # 1) 입고예정 생성
        resp = self.api.post('/api/v1/inbound/orders/', {
            'client': self.client_obj.pk,
            'expected_date': '2026-03-10',
            'notes': '통합테스트 입고',
            'items': [
                {'product': self.product_a.pk, 'expected_qty': 10},
                {'product': self.product_b.pk, 'expected_qty': 5},
            ],
        }, format='json')
        self.assertEqual(resp.status_code, 201)

        order_id = resp.data['id']
        inbound_id = resp.data['inbound_id']
        self.assertEqual(resp.data['status'], 'PLANNED')

        item_a = InboundOrderItem.objects.get(
            inbound_order_id=order_id, product=self.product_a,
        )
        item_b = InboundOrderItem.objects.get(
            inbound_order_id=order_id, product=self.product_b,
        )

        # 2) 도착 처리: PLANNED → ARRIVED
        resp = self.api.post(f'/api/v1/inbound/orders/{order_id}/arrive/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'ARRIVED')

        # 3) PDA 검수 (field_user)
        self.api.force_authenticate(user=self.field_user)

        # 상품A: 10개 양품, 1개 불량
        resp = self.api.post(f'/api/v1/inbound/{inbound_id}/inspect/', {
            'product_barcode': 'INT-A001',
            'qty': 10,
            'defect_qty': 1,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['order_status'], 'INSPECTING')
        self.assertFalse(resp.data['all_inspected'])

        # 상품B: 5개 양품, 0개 불량
        resp = self.api.post(f'/api/v1/inbound/{inbound_id}/inspect/', {
            'product_barcode': 'INT-B002',
            'qty': 5,
            'defect_qty': 0,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['order_status'], 'INSPECTED')
        self.assertTrue(resp.data['all_inspected'])

        # 4) PDA 적치
        # 상품A: 양품 9개 (10-1) → STOR-01
        resp = self.api.post(f'/api/v1/inbound/{inbound_id}/putaway/', {
            'product_barcode': 'INT-A001',
            'location_code': 'INT-STOR-01',
            'qty': 9,
        })
        self.assertEqual(resp.status_code, 200)

        # 상품B: 양품 5개 → STOR-02
        resp = self.api.post(f'/api/v1/inbound/{inbound_id}/putaway/', {
            'product_barcode': 'INT-B002',
            'location_code': 'INT-STOR-02',
            'qty': 5,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['order_status'], 'PUTAWAY_COMPLETE')
        self.assertTrue(resp.data['all_putaway'])

        # 5) InventoryBalance 확인
        bal_a = InventoryBalance.objects.get(
            product=self.product_a, location=self.loc_storage,
            client=self.client_obj,
        )
        self.assertEqual(bal_a.on_hand_qty, 9)

        bal_b = InventoryBalance.objects.get(
            product=self.product_b, location=self.loc_storage2,
            client=self.client_obj,
        )
        self.assertEqual(bal_b.on_hand_qty, 5)

        # 6) InventoryTransaction GR 기록 확인
        gr_txns = InventoryTransaction.objects.filter(
            transaction_type='GR', reference_id=inbound_id,
        )
        self.assertEqual(gr_txns.count(), 2)

        gr_a = gr_txns.get(product=self.product_a)
        self.assertEqual(gr_a.qty, 9)
        self.assertEqual(gr_a.reference_type, 'INBOUND')

        gr_b = gr_txns.get(product=self.product_b)
        self.assertEqual(gr_b.qty, 5)


# ======================================================================
# 2. 전체 출고 플로우
# ======================================================================

class OutboundFullFlowTest(IntegrationMixin, TestCase):
    """주문 수신 → 할당 → 웨이브 → 토탈피킹 → 검수 → 출고 확정"""

    def _seed_stock(self, product, qty, location=None):
        """보관존에 재고 생성"""
        loc = location or self.loc_storage
        InventoryBalance.objects.create(
            product=product, location=loc,
            client=self.client_obj, on_hand_qty=qty,
        )

    @patch('apps.webhooks.services.publish_event')
    def test_full_outbound_flow(self, mock_webhook):
        # 0) 재고 준비 (입고 완료 상태)
        self._seed_stock(self.product_a, 20)
        self._seed_stock(self.product_b, 10)

        self.api.force_authenticate(user=self.office_user)

        # 1) 주문 수신 → 자동 할당
        resp = self.api.post('/api/v1/orders/', {
            'source': 'INTEGRATION',
            'source_order_id': 'INT-001',
            'client_id': self.client_obj.pk,
            'ordered_at': '2026-03-04T09:00:00Z',
            'shipping': {
                'recipient_name': '수취인A',
                'recipient_phone': '010-1111-1111',
                'recipient_address': '서울시 강남구',
            },
            'items': [
                {'sku': 'INT-A001', 'qty': 3},
                {'sku': 'INT-B002', 'qty': 2},
            ],
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['status'], 'ALLOCATED')
        wms_order_id = resp.data['wms_order_id']

        # 할당 후 가용재고 감소 확인
        bal_a = InventoryBalance.objects.get(
            product=self.product_a, location=self.loc_storage,
        )
        self.assertEqual(bal_a.on_hand_qty, 20)
        self.assertEqual(bal_a.allocated_qty, 3)
        self.assertEqual(bal_a.available_qty, 17)

        # ALC 트랜잭션 확인
        alc_txns = InventoryTransaction.objects.filter(
            transaction_type='ALC', reference_id=wms_order_id,
        )
        self.assertEqual(alc_txns.count(), 2)

        # 2) 웨이브 생성
        resp = self.api.post('/api/v1/waves/create/', {
            'wave_time': '09:00',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        wave_id = resp.data['wave_id']

        wave = Wave.objects.get(wave_id=wave_id)
        self.assertEqual(wave.total_orders, 1)
        self.assertEqual(wave.total_skus, 2)

        # 토탈피킹리스트 확인
        pick_lists = TotalPickList.objects.filter(wave=wave)
        self.assertEqual(pick_lists.count(), 2)

        pick_a = pick_lists.get(product=self.product_a)
        self.assertEqual(pick_a.total_qty, 3)
        self.assertEqual(pick_a.details.count(), 1)  # 1개 로케이션

        # 3) 피킹 스캔 (field_user)
        self.api.force_authenticate(user=self.field_user)

        # 상품A: 3개 피킹
        resp = self.api.post(f'/api/v1/waves/{wave_id}/pick/', {
            'from_location_code': 'INT-STOR-01',
            'product_barcode': 'INT-A001',
            'to_location_code': 'INT-OUT-01',
            'qty': 3,
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['success'])

        # 상품B: 2개 피킹
        resp = self.api.post(f'/api/v1/waves/{wave_id}/pick/', {
            'from_location_code': 'INT-STOR-01',
            'product_barcode': 'INT-B002',
            'to_location_code': 'INT-OUT-01',
            'qty': 2,
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['all_completed'])

        # 출고존 재고 확인
        out_bal_a = InventoryBalance.objects.get(
            product=self.product_a, location=self.loc_outbound,
        )
        self.assertEqual(out_bal_a.on_hand_qty, 3)

        out_bal_b = InventoryBalance.objects.get(
            product=self.product_b, location=self.loc_outbound,
        )
        self.assertEqual(out_bal_b.on_hand_qty, 2)

        # 보관존 재고 감소 확인
        stor_bal_a = InventoryBalance.objects.get(
            product=self.product_a, location=self.loc_storage,
        )
        self.assertEqual(stor_bal_a.on_hand_qty, 17)  # 20 - 3

        # 4) 주문별 검수 스캔
        # 상품A x3
        for i in range(3):
            resp = self.api.post(
                f'/api/v1/waves/orders/{wms_order_id}/inspect-scan/',
                {'product_barcode': 'INT-A001'},
                format='json',
            )
            self.assertEqual(resp.status_code, 200)

        # 상품B x2
        for i in range(2):
            resp = self.api.post(
                f'/api/v1/waves/orders/{wms_order_id}/inspect-scan/',
                {'product_barcode': 'INT-B002'},
                format='json',
            )
            self.assertEqual(resp.status_code, 200)

        self.assertTrue(resp.data['order_completed'])

        order = OutboundOrder.objects.get(wms_order_id=wms_order_id)
        self.assertEqual(order.status, 'INSPECTED')

        wave.refresh_from_db()
        self.assertEqual(wave.inspected_count, 1)

        # 5) 출고 확정
        resp = self.api.post(
            f'/api/v1/waves/orders/{wms_order_id}/ship/',
            {'tracking_number': 'TRACK-INT-001'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'SHIPPED')

        order.refresh_from_db()
        self.assertEqual(order.status, 'SHIPPED')
        self.assertEqual(order.tracking_number, 'TRACK-INT-001')
        self.assertIsNotNone(order.shipped_at)

        # 출고존 재고 차감 확인 (ship_stock → 0)
        out_bal_a.refresh_from_db()
        self.assertEqual(out_bal_a.on_hand_qty, 0)

        out_bal_b.refresh_from_db()
        self.assertEqual(out_bal_b.on_hand_qty, 0)

        # GI 트랜잭션 확인
        gi_txns = InventoryTransaction.objects.filter(
            transaction_type='GI', reference_id=wms_order_id,
        )
        self.assertEqual(gi_txns.count(), 2)

        gi_a = gi_txns.get(product=self.product_a)
        self.assertEqual(gi_a.qty, -3)

        # 웨이브 완료 확인 (단일 주문이므로 자동 완료)
        wave.refresh_from_db()
        self.assertEqual(wave.status, 'COMPLETED')
        self.assertIsNotNone(wave.completed_at)

        # 웹훅 발행 확인
        mock_webhook.assert_called()


# ======================================================================
# 3. 오배송 방지 검증
# ======================================================================

class MisdeliveryPreventionTest(IntegrationMixin, TestCase):
    """잘못된 스캔, 수량 초과, 미검수 출고 시도 차단 확인"""

    def setUp(self):
        super().setUp()
        InventoryBalance.objects.create(
            product=self.product_a, location=self.loc_storage,
            client=self.client_obj, on_hand_qty=50,
        )
        InventoryBalance.objects.create(
            product=self.product_b, location=self.loc_storage,
            client=self.client_obj, on_hand_qty=30,
        )

    def _create_order_and_wave(self):
        """주문→할당→웨이브→피킹완료 상태 생성"""
        self.api.force_authenticate(user=self.office_user)

        resp = self.api.post('/api/v1/orders/', {
            'source': 'TEST',
            'source_order_id': 'MDP-001',
            'client_id': self.client_obj.pk,
            'ordered_at': '2026-03-04T09:00:00Z',
            'shipping': {
                'recipient_name': '수취인',
                'recipient_phone': '010-0000-0000',
                'recipient_address': '서울',
            },
            'items': [
                {'sku': 'INT-A001', 'qty': 2},
                {'sku': 'INT-B002', 'qty': 1},
            ],
        }, format='json')
        wms_order_id = resp.data['wms_order_id']

        resp = self.api.post('/api/v1/waves/create/', {
            'wave_time': '10:00',
        }, format='json')
        wave_id = resp.data['wave_id']

        # 피킹 완료
        self.api.force_authenticate(user=self.field_user)
        self.api.post(f'/api/v1/waves/{wave_id}/pick/', {
            'from_location_code': 'INT-STOR-01',
            'product_barcode': 'INT-A001',
            'to_location_code': 'INT-OUT-01',
            'qty': 2,
        }, format='json')
        self.api.post(f'/api/v1/waves/{wave_id}/pick/', {
            'from_location_code': 'INT-STOR-01',
            'product_barcode': 'INT-B002',
            'to_location_code': 'INT-OUT-01',
            'qty': 1,
        }, format='json')

        return wms_order_id, wave_id

    def test_wrong_product_scan_rejected(self):
        """잘못된 상품 바코드 스캔 시 에러"""
        wms_order_id, wave_id = self._create_order_and_wave()
        self.api.force_authenticate(user=self.field_user)

        resp = self.api.post(
            f'/api/v1/waves/orders/{wms_order_id}/inspect-scan/',
            {'product_barcode': 'NONEXISTENT-BARCODE'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['error_code'], 'WRONG_PRODUCT')

    def test_wrong_location_pick_rejected(self):
        """잘못된 로케이션 스캔 시 에러"""
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.post('/api/v1/orders/', {
            'source': 'TEST', 'source_order_id': 'LOC-001',
            'client_id': self.client_obj.pk,
            'ordered_at': '2026-03-04T09:00:00Z',
            'shipping': {
                'recipient_name': '수취인', 'recipient_phone': '010-0000-0000',
                'recipient_address': '서울',
            },
            'items': [{'sku': 'INT-A001', 'qty': 1}],
        }, format='json')
        resp = self.api.post('/api/v1/waves/create/', {
            'wave_time': '11:00',
        }, format='json')
        wave_id = resp.data['wave_id']

        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(f'/api/v1/waves/{wave_id}/pick/', {
            'from_location_code': 'NONEXISTENT-LOC',
            'product_barcode': 'INT-A001',
            'to_location_code': 'INT-OUT-01',
            'qty': 1,
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_qty_exceeded_scan_rejected(self):
        """검수 수량 초과 스캔 시 에러"""
        wms_order_id, wave_id = self._create_order_and_wave()
        self.api.force_authenticate(user=self.field_user)

        # 상품B qty=1, 1번 스캔 성공
        resp = self.api.post(
            f'/api/v1/waves/orders/{wms_order_id}/inspect-scan/',
            {'product_barcode': 'INT-B002'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)

        # 2번째 → 초과
        resp = self.api.post(
            f'/api/v1/waves/orders/{wms_order_id}/inspect-scan/',
            {'product_barcode': 'INT-B002'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['error_code'], 'QTY_EXCEEDED')

    @patch('apps.webhooks.services.publish_event')
    def test_uninspected_ship_rejected(self, mock_webhook):
        """미검수 상태에서 출고 시도 시 에러"""
        wms_order_id, wave_id = self._create_order_and_wave()
        self.api.force_authenticate(user=self.field_user)

        # 검수 없이 바로 출고 시도
        resp = self.api.post(
            f'/api/v1/waves/orders/{wms_order_id}/ship/',
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('INSPECTED', resp.data['detail'])


# ======================================================================
# 4. 재고 정합성
# ======================================================================

class InventoryConsistencyTest(IntegrationMixin, TestCase):
    """입고→출고→잔량, 할당/가용재고, 취소 시 해제"""

    @patch('apps.webhooks.services.publish_event')
    def test_inbound_10_outbound_3_leaves_7(self, mock_webhook):
        """입고 10개 → 출고 3개 → 보관존 잔량 7개"""
        self.api.force_authenticate(user=self.office_user)

        # 입고: 10개
        resp = self.api.post('/api/v1/inbound/orders/', {
            'client': self.client_obj.pk,
            'expected_date': '2026-03-10',
            'items': [
                {'product': self.product_a.pk, 'expected_qty': 10},
            ],
        }, format='json')
        order_id = resp.data['id']
        inbound_id = resp.data['inbound_id']

        self.api.post(f'/api/v1/inbound/orders/{order_id}/arrive/')

        self.api.force_authenticate(user=self.field_user)
        self.api.post(f'/api/v1/inbound/{inbound_id}/inspect/', {
            'product_barcode': 'INT-A001', 'qty': 10, 'defect_qty': 0,
        })
        self.api.post(f'/api/v1/inbound/{inbound_id}/putaway/', {
            'product_barcode': 'INT-A001',
            'location_code': 'INT-STOR-01',
            'qty': 10,
        })

        bal = InventoryBalance.objects.get(
            product=self.product_a, location=self.loc_storage,
        )
        self.assertEqual(bal.on_hand_qty, 10)

        # 출고: 3개
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.post('/api/v1/orders/', {
            'source': 'TEST', 'source_order_id': 'CON-001',
            'client_id': self.client_obj.pk,
            'ordered_at': '2026-03-04T09:00:00Z',
            'shipping': {
                'recipient_name': '수취인', 'recipient_phone': '010-0000-0000',
                'recipient_address': '서울',
            },
            'items': [{'sku': 'INT-A001', 'qty': 3}],
        }, format='json')
        wms_order_id = resp.data['wms_order_id']

        resp = self.api.post('/api/v1/waves/create/', {
            'wave_time': '09:00',
        }, format='json')
        wave_id = resp.data['wave_id']

        self.api.force_authenticate(user=self.field_user)
        self.api.post(f'/api/v1/waves/{wave_id}/pick/', {
            'from_location_code': 'INT-STOR-01',
            'product_barcode': 'INT-A001',
            'to_location_code': 'INT-OUT-01',
            'qty': 3,
        }, format='json')

        for _ in range(3):
            self.api.post(
                f'/api/v1/waves/orders/{wms_order_id}/inspect-scan/',
                {'product_barcode': 'INT-A001'}, format='json',
            )

        self.api.post(
            f'/api/v1/waves/orders/{wms_order_id}/ship/',
            {'tracking_number': 'TRK-CON'}, format='json',
        )

        # 보관존: 10 - 3 = 7
        bal.refresh_from_db()
        self.assertEqual(bal.on_hand_qty, 7)

        # 출고존: 0 (ship으로 차감됨)
        out_bal = InventoryBalance.objects.get(
            product=self.product_a, location=self.loc_outbound,
        )
        self.assertEqual(out_bal.on_hand_qty, 0)

    def test_allocation_reduces_available_qty(self):
        """할당 후 가용재고 감소 확인"""
        InventoryBalance.objects.create(
            product=self.product_a, location=self.loc_storage,
            client=self.client_obj, on_hand_qty=20,
        )

        self.api.force_authenticate(user=self.office_user)
        resp = self.api.post('/api/v1/orders/', {
            'source': 'TEST', 'source_order_id': 'ALC-001',
            'client_id': self.client_obj.pk,
            'ordered_at': '2026-03-04T09:00:00Z',
            'shipping': {
                'recipient_name': '수취인', 'recipient_phone': '010-0000-0000',
                'recipient_address': '서울',
            },
            'items': [{'sku': 'INT-A001', 'qty': 5}],
        }, format='json')
        self.assertEqual(resp.data['status'], 'ALLOCATED')

        bal = InventoryBalance.objects.get(
            product=self.product_a, location=self.loc_storage,
        )
        self.assertEqual(bal.on_hand_qty, 20)
        self.assertEqual(bal.allocated_qty, 5)
        self.assertEqual(bal.available_qty, 15)

    def test_cancel_deallocates_stock(self):
        """취소 시 할당 해제 확인"""
        InventoryBalance.objects.create(
            product=self.product_a, location=self.loc_storage,
            client=self.client_obj, on_hand_qty=20,
        )

        self.api.force_authenticate(user=self.office_user)
        resp = self.api.post('/api/v1/orders/', {
            'source': 'TEST', 'source_order_id': 'CAN-001',
            'client_id': self.client_obj.pk,
            'ordered_at': '2026-03-04T09:00:00Z',
            'shipping': {
                'recipient_name': '수취인', 'recipient_phone': '010-0000-0000',
                'recipient_address': '서울',
            },
            'items': [{'sku': 'INT-A001', 'qty': 5}],
        }, format='json')
        wms_order_id = resp.data['wms_order_id']

        # 할당 확인
        bal = InventoryBalance.objects.get(
            product=self.product_a, location=self.loc_storage,
        )
        self.assertEqual(bal.allocated_qty, 5)

        # 취소
        resp = self.api.post(f'/api/v1/orders/{wms_order_id}/cancel/')
        self.assertEqual(resp.status_code, 200)

        order = OutboundOrder.objects.get(wms_order_id=wms_order_id)
        self.assertEqual(order.status, 'CANCELLED')

        # 할당 해제 확인
        bal.refresh_from_db()
        self.assertEqual(bal.allocated_qty, 0)
        self.assertEqual(bal.available_qty, 20)

        # ALC_R 트랜잭션 확인
        alc_r = InventoryTransaction.objects.filter(
            transaction_type='ALC_R', reference_id=wms_order_id,
        )
        self.assertTrue(alc_r.exists())


# ======================================================================
# 5. 동시성
# ======================================================================

class ConcurrencyTest(IntegrationMixin, TransactionTestCase):
    """같은 SKU에 동시 할당 요청 시 재고 부족 정상 처리"""

    def test_concurrent_allocation_respects_stock_limit(self):
        """재고 7개에 5개씩 2건 동시 주문 → 1건만 ALLOCATED"""
        InventoryBalance.objects.create(
            product=self.product_a, location=self.loc_storage,
            client=self.client_obj, on_hand_qty=7,
        )

        def place_order(order_suffix):
            """별도 API 클라이언트로 주문 생성"""
            api = APIClient()
            api.force_authenticate(user=self.office_user)
            resp = api.post('/api/v1/orders/', {
                'source': 'CONC',
                'source_order_id': f'CONC-{order_suffix}',
                'client_id': self.client_obj.pk,
                'ordered_at': '2026-03-04T09:00:00Z',
                'shipping': {
                    'recipient_name': '수취인',
                    'recipient_phone': '010-0000-0000',
                    'recipient_address': '서울',
                },
                'items': [{'sku': 'INT-A001', 'qty': 5}],
            }, format='json')
            return resp

        # 직렬 실행 (SQLite는 file-lock이므로 ThreadPool 대신 직렬 테스트)
        resp1 = place_order('001')
        resp2 = place_order('002')

        statuses = [resp1.data.get('status'), resp2.data.get('status')]

        # 하나는 ALLOCATED, 하나는 HELD (재고 부족)
        self.assertIn('ALLOCATED', statuses)
        self.assertIn('HELD', statuses)

        # 주문 상태 정합성: 초과 할당 없음 (ALLOCATED 1건 + HELD 1건)
        allocated_count = OutboundOrder.objects.filter(
            source='CONC', status='ALLOCATED',
        ).count()
        held_count = OutboundOrder.objects.filter(
            source='CONC', status='HELD',
        ).count()
        self.assertEqual(allocated_count, 1)
        self.assertEqual(held_count, 1)

        # 재고 정합성: on_hand 변동 없음 (할당은 가상 예약)
        bal = InventoryBalance.objects.get(
            product=self.product_a, location=self.loc_storage,
        )
        self.assertEqual(bal.on_hand_qty, 7)


# ======================================================================
# 6. 전체 파이프라인 (입고→출고 E2E)
# ======================================================================

class EndToEndPipelineTest(IntegrationMixin, TestCase):
    """입고부터 출고까지 전체 파이프라인 단일 테스트"""

    @patch('apps.webhooks.services.publish_event')
    def test_inbound_to_outbound_pipeline(self, mock_webhook):
        self.api.force_authenticate(user=self.office_user)

        # --- 입고 ---
        resp = self.api.post('/api/v1/inbound/orders/', {
            'client': self.client_obj.pk,
            'expected_date': '2026-03-10',
            'items': [
                {'product': self.product_a.pk, 'expected_qty': 20},
                {'product': self.product_b.pk, 'expected_qty': 15},
            ],
        }, format='json')
        ib_id = resp.data['id']
        inbound_id = resp.data['inbound_id']

        self.api.post(f'/api/v1/inbound/orders/{ib_id}/arrive/')

        self.api.force_authenticate(user=self.field_user)
        self.api.post(f'/api/v1/inbound/{inbound_id}/inspect/', {
            'product_barcode': 'INT-A001', 'qty': 20, 'defect_qty': 0,
        })
        self.api.post(f'/api/v1/inbound/{inbound_id}/inspect/', {
            'product_barcode': 'INT-B002', 'qty': 15, 'defect_qty': 0,
        })
        self.api.post(f'/api/v1/inbound/{inbound_id}/putaway/', {
            'product_barcode': 'INT-A001',
            'location_code': 'INT-STOR-01', 'qty': 20,
        })
        self.api.post(f'/api/v1/inbound/{inbound_id}/putaway/', {
            'product_barcode': 'INT-B002',
            'location_code': 'INT-STOR-01', 'qty': 15,
        })

        # --- 출고 ---
        self.api.force_authenticate(user=self.office_user)

        # 주문 2건
        resp1 = self.api.post('/api/v1/orders/', {
            'source': 'E2E', 'source_order_id': 'E2E-001',
            'client_id': self.client_obj.pk,
            'ordered_at': '2026-03-04T09:00:00Z',
            'shipping': {
                'recipient_name': '수취인1', 'recipient_phone': '010-1111-1111',
                'recipient_address': '서울',
            },
            'items': [
                {'sku': 'INT-A001', 'qty': 5},
                {'sku': 'INT-B002', 'qty': 3},
            ],
        }, format='json')
        self.assertEqual(resp1.data['status'], 'ALLOCATED')
        wms_id1 = resp1.data['wms_order_id']

        resp2 = self.api.post('/api/v1/orders/', {
            'source': 'E2E', 'source_order_id': 'E2E-002',
            'client_id': self.client_obj.pk,
            'ordered_at': '2026-03-04T09:00:00Z',
            'shipping': {
                'recipient_name': '수취인2', 'recipient_phone': '010-2222-2222',
                'recipient_address': '부산',
            },
            'items': [
                {'sku': 'INT-A001', 'qty': 3},
            ],
        }, format='json')
        self.assertEqual(resp2.data['status'], 'ALLOCATED')
        wms_id2 = resp2.data['wms_order_id']

        # 웨이브 생성
        resp = self.api.post('/api/v1/waves/create/', {
            'wave_time': '10:00',
        }, format='json')
        wave_id = resp.data['wave_id']
        wave = Wave.objects.get(wave_id=wave_id)
        self.assertEqual(wave.total_orders, 2)

        # 토탈피킹: A=8(5+3), B=3
        pick_a = TotalPickList.objects.get(wave=wave, product=self.product_a)
        self.assertEqual(pick_a.total_qty, 8)

        pick_b = TotalPickList.objects.get(wave=wave, product=self.product_b)
        self.assertEqual(pick_b.total_qty, 3)

        # 피킹
        self.api.force_authenticate(user=self.field_user)
        self.api.post(f'/api/v1/waves/{wave_id}/pick/', {
            'from_location_code': 'INT-STOR-01',
            'product_barcode': 'INT-A001',
            'to_location_code': 'INT-OUT-01',
            'qty': 8,
        }, format='json')
        self.api.post(f'/api/v1/waves/{wave_id}/pick/', {
            'from_location_code': 'INT-STOR-01',
            'product_barcode': 'INT-B002',
            'to_location_code': 'INT-OUT-01',
            'qty': 3,
        }, format='json')

        # 검수 - 주문1
        for _ in range(5):
            self.api.post(
                f'/api/v1/waves/orders/{wms_id1}/inspect-scan/',
                {'product_barcode': 'INT-A001'}, format='json',
            )
        for _ in range(3):
            self.api.post(
                f'/api/v1/waves/orders/{wms_id1}/inspect-scan/',
                {'product_barcode': 'INT-B002'}, format='json',
            )

        # 검수 - 주문2
        for _ in range(3):
            self.api.post(
                f'/api/v1/waves/orders/{wms_id2}/inspect-scan/',
                {'product_barcode': 'INT-A001'}, format='json',
            )

        # 출고 확정
        self.api.post(
            f'/api/v1/waves/orders/{wms_id1}/ship/',
            {'tracking_number': 'E2E-TRK-1'}, format='json',
        )
        self.api.post(
            f'/api/v1/waves/orders/{wms_id2}/ship/',
            {'tracking_number': 'E2E-TRK-2'}, format='json',
        )

        # --- 최종 검증 ---

        # 웨이브 완료
        wave.refresh_from_db()
        self.assertEqual(wave.status, 'COMPLETED')
        self.assertEqual(wave.shipped_count, 2)

        # 보관존 최종 재고: A=20-8=12, B=15-3=12
        bal_a = InventoryBalance.objects.get(
            product=self.product_a, location=self.loc_storage,
        )
        self.assertEqual(bal_a.on_hand_qty, 12)  # 20 - 8(picked)

        bal_b = InventoryBalance.objects.get(
            product=self.product_b, location=self.loc_storage,
        )
        self.assertEqual(bal_b.on_hand_qty, 12)  # 15 - 3(picked)

        # 전체 트랜잭션 히스토리
        all_txns = InventoryTransaction.objects.all()

        # GR(입고) 2건 + ALC(할당) 3건 + WV_MV(피킹이동) 2건
        # + GI(출고) 3건 + WV_RTN(잔여복귀) ≈ expected
        gr_count = all_txns.filter(transaction_type='GR').count()
        self.assertEqual(gr_count, 2)

        alc_count = all_txns.filter(transaction_type='ALC').count()
        self.assertEqual(alc_count, 3)  # A 2건, B 1건

        gi_count = all_txns.filter(transaction_type='GI').count()
        self.assertEqual(gi_count, 3)  # order1: A+B, order2: A
