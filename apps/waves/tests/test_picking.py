"""
토탈피킹 PDA API 테스트
"""
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client
from apps.inventory.models import Product, Location, InventoryBalance
from apps.history.models import InventoryTransaction
from apps.waves.models import (
    Wave, OutboundOrder, OutboundOrderItem,
    TotalPickList, TotalPickListDetail,
)
from apps.waves.services import WaveService


class PickingTestMixin:
    """피킹 테스트 공통 데이터"""

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

    def _create_wave(self):
        """주문 + 웨이브 생성"""
        for i in range(2):
            order = OutboundOrder.objects.create(
                source='TEST', source_order_id=f'T-{i:03d}',
                client=self.client_obj, status='ALLOCATED',
                recipient_name=f'수취인{i}', recipient_phone='010-0000-0000',
                recipient_address='서울', ordered_at=timezone.now(),
            )
            OutboundOrderItem.objects.create(
                order=order, product=self.product, qty=5,
            )
            OutboundOrderItem.objects.create(
                order=order, product=self.product2, qty=3,
            )
        return WaveService.create_wave(
            wave_time='09:00', created_by=self.office_user,
        )

    def _pick_payload(self, **overrides):
        payload = {
            'from_location_code': 'STOR-01',
            'product_barcode': 'SKU-A001',
            'to_location_code': 'OUT-01',
            'qty': 5,
        }
        payload.update(overrides)
        return payload


# ------------------------------------------------------------------
# 피킹리스트 조회
# ------------------------------------------------------------------

class PickListViewTest(PickingTestMixin, TestCase):
    """GET /api/v1/waves/{wave_id}/picklist/"""

    def test_returns_pending_and_in_progress(self):
        wave = self._create_wave()
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.get(f'/api/v1/waves/{wave.wave_id}/picklist/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['wave_id'], wave.wave_id)
        # 2 SKU → 2 pick lists (모두 PENDING)
        self.assertEqual(len(resp.data['pick_lists']), 2)

    def test_excludes_completed(self):
        wave = self._create_wave()
        # 1개 COMPLETED로 변경
        pl = wave.pick_lists.first()
        pl.status = 'COMPLETED'
        pl.save()

        self.api.force_authenticate(user=self.field_user)
        resp = self.api.get(f'/api/v1/waves/{wave.wave_id}/picklist/')
        self.assertEqual(len(resp.data['pick_lists']), 1)

    def test_includes_details(self):
        wave = self._create_wave()
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.get(f'/api/v1/waves/{wave.wave_id}/picklist/')
        for pl in resp.data['pick_lists']:
            self.assertIn('details', pl)
            self.assertGreater(len(pl['details']), 0)

    def test_wave_not_found(self):
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.get('/api/v1/waves/WV-NOTFOUND/picklist/')
        self.assertEqual(resp.status_code, 404)

    def test_client_role_forbidden(self):
        wave = self._create_wave()
        self.api.force_authenticate(user=self.client_user)
        resp = self.api.get(f'/api/v1/waves/{wave.wave_id}/picklist/')
        self.assertEqual(resp.status_code, 403)


# ------------------------------------------------------------------
# 피킹 스캔
# ------------------------------------------------------------------

class PickScanTest(PickingTestMixin, TestCase):
    """POST /api/v1/waves/{wave_id}/pick/"""

    def test_pick_success(self):
        """정상 피킹"""
        wave = self._create_wave()
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(
            f'/api/v1/waves/{wave.wave_id}/pick/',
            self._pick_payload(qty=5),
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['success'])

    def test_pick_updates_detail(self):
        """피킹 후 detail.picked_qty 업데이트"""
        wave = self._create_wave()
        self.api.force_authenticate(user=self.field_user)
        self.api.post(
            f'/api/v1/waves/{wave.wave_id}/pick/',
            self._pick_payload(qty=3),
            format='json',
        )
        detail = TotalPickListDetail.objects.get(
            pick_list__wave=wave,
            pick_list__product=self.product,
            from_location=self.loc_storage,
        )
        self.assertEqual(detail.picked_qty, 3)
        self.assertEqual(detail.picked_by, self.field_user)
        self.assertIsNotNone(detail.picked_at)

    def test_pick_updates_pick_list(self):
        """피킹 후 TotalPickList.picked_qty 업데이트"""
        wave = self._create_wave()
        self.api.force_authenticate(user=self.field_user)
        self.api.post(
            f'/api/v1/waves/{wave.wave_id}/pick/',
            self._pick_payload(qty=5),
            format='json',
        )
        pl = TotalPickList.objects.get(wave=wave, product=self.product)
        self.assertEqual(pl.picked_qty, 5)
        self.assertEqual(pl.status, 'IN_PROGRESS')

    def test_pick_cumulative(self):
        """누적 피킹"""
        wave = self._create_wave()
        self.api.force_authenticate(user=self.field_user)
        self.api.post(
            f'/api/v1/waves/{wave.wave_id}/pick/',
            self._pick_payload(qty=3),
            format='json',
        )
        resp = self.api.post(
            f'/api/v1/waves/{wave.wave_id}/pick/',
            self._pick_payload(qty=2),
            format='json',
        )
        self.assertEqual(resp.data['detail_picked_qty'], 5)
        self.assertEqual(resp.data['detail_remaining'], 5)  # total 10, picked 5

    def test_pick_completes_pick_list(self):
        """전체 수량 피킹 → pick_list COMPLETED"""
        wave = self._create_wave()
        pl = TotalPickList.objects.get(wave=wave, product=self.product)
        self.api.force_authenticate(user=self.field_user)
        # 전체 수량 피킹
        self.api.post(
            f'/api/v1/waves/{wave.wave_id}/pick/',
            self._pick_payload(qty=pl.total_qty),
            format='json',
        )
        pl.refresh_from_db()
        self.assertEqual(pl.status, 'COMPLETED')

    def test_pick_creates_wave_mv_transaction(self):
        """WV_MV 트랜잭션 생성"""
        wave = self._create_wave()
        self.api.force_authenticate(user=self.field_user)
        self.api.post(
            f'/api/v1/waves/{wave.wave_id}/pick/',
            self._pick_payload(qty=5),
            format='json',
        )
        txn = InventoryTransaction.objects.filter(
            transaction_type='WV_MV', product=self.product,
        ).first()
        self.assertIsNotNone(txn)
        self.assertEqual(txn.qty, 5)
        self.assertIn(wave.wave_id, txn.reference_id)

    def test_pick_moves_inventory(self):
        """재고 이동 확인"""
        wave = self._create_wave()
        self.api.force_authenticate(user=self.field_user)
        self.api.post(
            f'/api/v1/waves/{wave.wave_id}/pick/',
            self._pick_payload(qty=5),
            format='json',
        )
        # 출발지 감소
        bal_from = InventoryBalance.objects.get(
            product=self.product, location=self.loc_storage,
        )
        self.assertEqual(bal_from.on_hand_qty, 95)
        # 도착지 증가
        bal_to = InventoryBalance.objects.get(
            product=self.product, location=self.loc_outbound,
        )
        self.assertEqual(bal_to.on_hand_qty, 5)

    def test_first_pick_changes_wave_to_picking(self):
        """첫 피킹 → CREATED → PICKING"""
        wave = self._create_wave()
        self.assertEqual(wave.status, 'CREATED')
        self.api.force_authenticate(user=self.field_user)
        self.api.post(
            f'/api/v1/waves/{wave.wave_id}/pick/',
            self._pick_payload(qty=1),
            format='json',
        )
        wave.refresh_from_db()
        self.assertEqual(wave.status, 'PICKING')

    def test_all_picked_transitions_to_distributing(self):
        """전체 피킹 완료 → DISTRIBUTING"""
        wave = self._create_wave()
        self.api.force_authenticate(user=self.field_user)

        # 상품A 전체 피킹
        pl_a = TotalPickList.objects.get(wave=wave, product=self.product)
        self.api.post(
            f'/api/v1/waves/{wave.wave_id}/pick/',
            self._pick_payload(
                from_location_code='STOR-01',
                product_barcode='SKU-A001',
                qty=pl_a.total_qty,
            ),
            format='json',
        )

        # 상품B 전체 피킹
        pl_b = TotalPickList.objects.get(wave=wave, product=self.product2)
        resp = self.api.post(
            f'/api/v1/waves/{wave.wave_id}/pick/',
            self._pick_payload(
                from_location_code='STOR-02',
                product_barcode='SKU-B002',
                qty=pl_b.total_qty,
            ),
            format='json',
        )
        self.assertTrue(resp.data['all_completed'])
        self.assertEqual(resp.data['wave_status'], 'DISTRIBUTING')

        wave.refresh_from_db()
        self.assertEqual(wave.status, 'DISTRIBUTING')
        self.assertEqual(wave.picked_count, 2)  # 2 pick lists completed


# ------------------------------------------------------------------
# 에러 케이스
# ------------------------------------------------------------------

class PickScanErrorTest(PickingTestMixin, TestCase):
    """피킹 스캔 에러 케이스"""

    def test_wrong_location_not_in_picklist(self):
        """WRONG_LOCATION: 피킹리스트에 없는 로케이션"""
        wave = self._create_wave()
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(
            f'/api/v1/waves/{wave.wave_id}/pick/',
            self._pick_payload(from_location_code='STOR-02'),  # 상품A는 STOR-01에 있음
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['error'], 'WRONG_LOCATION')

    def test_wrong_location_invalid_zone(self):
        """WRONG_LOCATION: OUTBOUND_STAGING 존은 출발지로 불가"""
        wave = self._create_wave()
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(
            f'/api/v1/waves/{wave.wave_id}/pick/',
            self._pick_payload(from_location_code='OUT-01'),
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['error'], 'WRONG_LOCATION')

    def test_wrong_product(self):
        """WRONG_PRODUCT: 미등록 바코드"""
        wave = self._create_wave()
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(
            f'/api/v1/waves/{wave.wave_id}/pick/',
            self._pick_payload(product_barcode='UNKNOWN-999'),
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['error'], 'WRONG_PRODUCT')

    def test_wrong_outbound_zone(self):
        """WRONG_OUTBOUND_ZONE: 웨이브 출고존이 아닌 곳"""
        wave = self._create_wave()
        other_outbound = Location.objects.create(
            barcode='OUT-99', zone_type='OUTBOUND_STAGING',
        )
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(
            f'/api/v1/waves/{wave.wave_id}/pick/',
            self._pick_payload(to_location_code='OUT-99'),
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['error'], 'WRONG_OUTBOUND_ZONE')
        self.assertIn('OUT-01', resp.data['message'])

    def test_qty_exceeded(self):
        """QTY_EXCEEDED: 남은 수량 초과"""
        wave = self._create_wave()
        pl = TotalPickList.objects.get(wave=wave, product=self.product)
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(
            f'/api/v1/waves/{wave.wave_id}/pick/',
            self._pick_payload(qty=pl.total_qty + 1),
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['error'], 'QTY_EXCEEDED')

    def test_already_completed_detail(self):
        """ALREADY_COMPLETED: 이미 피킹 완료된 항목"""
        wave = self._create_wave()
        detail = TotalPickListDetail.objects.get(
            pick_list__wave=wave,
            pick_list__product=self.product,
        )
        detail.picked_qty = detail.qty
        detail.save()

        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(
            f'/api/v1/waves/{wave.wave_id}/pick/',
            self._pick_payload(qty=1),
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['error'], 'ALREADY_COMPLETED')

    def test_already_completed_wave(self):
        """ALREADY_COMPLETED: 완료된 웨이브"""
        wave = self._create_wave()
        wave.status = 'DISTRIBUTING'
        wave.save()

        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(
            f'/api/v1/waves/{wave.wave_id}/pick/',
            self._pick_payload(qty=1),
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['error'], 'ALREADY_COMPLETED')

    def test_location_case_insensitive(self):
        """로케이션 코드 대소문자 무관"""
        wave = self._create_wave()
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(
            f'/api/v1/waves/{wave.wave_id}/pick/',
            self._pick_payload(
                from_location_code='stor-01',
                to_location_code='out-01',
            ),
            format='json',
        )
        self.assertEqual(resp.status_code, 200)


# ------------------------------------------------------------------
# 권한
# ------------------------------------------------------------------

class PickPermissionTest(PickingTestMixin, TestCase):

    def test_field_user_allowed(self):
        wave = self._create_wave()
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.get(f'/api/v1/waves/{wave.wave_id}/picklist/')
        self.assertEqual(resp.status_code, 200)

    def test_office_user_allowed(self):
        wave = self._create_wave()
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get(f'/api/v1/waves/{wave.wave_id}/picklist/')
        self.assertEqual(resp.status_code, 200)

    def test_client_user_forbidden_picklist(self):
        wave = self._create_wave()
        self.api.force_authenticate(user=self.client_user)
        resp = self.api.get(f'/api/v1/waves/{wave.wave_id}/picklist/')
        self.assertEqual(resp.status_code, 403)

    def test_client_user_forbidden_pick(self):
        wave = self._create_wave()
        self.api.force_authenticate(user=self.client_user)
        resp = self.api.post(
            f'/api/v1/waves/{wave.wave_id}/pick/',
            self._pick_payload(),
            format='json',
        )
        self.assertEqual(resp.status_code, 403)
