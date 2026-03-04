"""
웨이브 모델, 서비스, API 테스트
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
    generate_wave_id,
)
from apps.waves.services import WaveService


# ------------------------------------------------------------------
# 채번
# ------------------------------------------------------------------

class GenerateWaveIdTest(TestCase):

    def test_first_of_day(self):
        wid = generate_wave_id()
        today = timezone.localtime(timezone.now()).strftime('%Y%m%d')
        self.assertEqual(wid, f'WV-{today}-01')

    def test_sequential(self):
        Wave.objects.create(wave_id=generate_wave_id(), wave_time='09:00')
        wid2 = generate_wave_id()
        self.assertTrue(wid2.endswith('-02'))

    def test_two_digit(self):
        wid = generate_wave_id()
        seq = wid.split('-')[-1]
        self.assertEqual(len(seq), 2)


# ------------------------------------------------------------------
# 공통 데이터
# ------------------------------------------------------------------

class WaveTestMixin:

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
        self.office_user = User.objects.create_user(
            email='office@test.com', password='test1234',
            name='오피스', role='office', is_approved=True,
        )
        self.field_user = User.objects.create_user(
            email='field@test.com', password='test1234',
            name='필드', role='field', is_approved=True,
        )
        self.client_user = User.objects.create_user(
            email='client@test.com', password='test1234',
            name='거래처', role='client', is_approved=True,
        )

        self.api = APIClient()

    def _create_allocated_orders(self, count=3):
        """ALLOCATED 주문 n개 생성"""
        orders = []
        for i in range(count):
            order = OutboundOrder.objects.create(
                source='TEST', source_order_id=f'T-{i:03d}',
                client=self.client_obj, status='ALLOCATED',
                recipient_name=f'수취인{i}', recipient_phone='010-0000-0000',
                recipient_address='서울', ordered_at=timezone.now(),
            )
            OutboundOrderItem.objects.create(
                order=order, product=self.product, qty=2,
            )
            OutboundOrderItem.objects.create(
                order=order, product=self.product2, qty=1,
            )
            orders.append(order)
        return orders


# ------------------------------------------------------------------
# WaveService 테스트
# ------------------------------------------------------------------

class WaveServiceTest(WaveTestMixin, TestCase):
    """WaveService.create_wave 테스트"""

    def test_create_wave_collects_allocated_orders(self):
        """ALLOCATED + wave=null 주문만 수집"""
        orders = self._create_allocated_orders(3)
        # HELD 주문은 제외
        OutboundOrder.objects.create(
            source='TEST', source_order_id='T-HELD',
            client=self.client_obj, status='HELD',
            recipient_name='보류', recipient_phone='010-0000-0000',
            recipient_address='서울', ordered_at=timezone.now(),
        )

        wave = WaveService.create_wave(
            wave_time='09:00', created_by=self.office_user,
        )
        self.assertEqual(wave.total_orders, 3)
        for o in orders:
            o.refresh_from_db()
            self.assertEqual(o.wave, wave)

    def test_wave_id_generated(self):
        self._create_allocated_orders(1)
        wave = WaveService.create_wave(
            wave_time='14:00', created_by=self.office_user,
        )
        self.assertTrue(wave.wave_id.startswith('WV-'))

    def test_wave_time_saved(self):
        self._create_allocated_orders(1)
        wave = WaveService.create_wave(
            wave_time='09:30', created_by=self.office_user,
        )
        self.assertEqual(wave.wave_time, '09:30')

    def test_total_skus_count(self):
        """SKU 2종 → total_skus=2"""
        self._create_allocated_orders(2)
        wave = WaveService.create_wave(
            wave_time='09:00', created_by=self.office_user,
        )
        self.assertEqual(wave.total_skus, 2)

    def test_pick_list_created(self):
        """SKU별 TotalPickList 생성"""
        self._create_allocated_orders(2)
        wave = WaveService.create_wave(
            wave_time='09:00', created_by=self.office_user,
        )
        pick_lists = TotalPickList.objects.filter(wave=wave)
        self.assertEqual(pick_lists.count(), 2)

        # 상품A: 2개 * 2주문 = 4개
        pl_a = pick_lists.get(product=self.product)
        self.assertEqual(pl_a.total_qty, 4)

        # 상품B: 1개 * 2주문 = 2개
        pl_b = pick_lists.get(product=self.product2)
        self.assertEqual(pl_b.total_qty, 2)

    def test_pick_list_detail_fifo(self):
        """FIFO 순으로 피킹 로케이션 할당"""
        self._create_allocated_orders(1)
        wave = WaveService.create_wave(
            wave_time='09:00', created_by=self.office_user,
        )
        pl = TotalPickList.objects.get(wave=wave, product=self.product)
        details = pl.details.all()
        self.assertEqual(details.count(), 1)
        self.assertEqual(details[0].from_location, self.loc_storage)
        self.assertEqual(details[0].qty, 2)

    def test_outbound_zone_assigned(self):
        """가용 OUTBOUND_STAGING 할당"""
        self._create_allocated_orders(1)
        wave = WaveService.create_wave(
            wave_time='09:00', created_by=self.office_user,
        )
        self.assertEqual(wave.outbound_zone, self.loc_outbound)

    def test_outbound_zone_excludes_active(self):
        """이미 사용 중인 출고존은 제외"""
        # 기존 웨이브에 출고존 사용
        Wave.objects.create(
            wave_id='WV-EXISTING-01', wave_time='08:00',
            status='PICKING', outbound_zone=self.loc_outbound,
        )
        self._create_allocated_orders(1)
        wave = WaveService.create_wave(
            wave_time='09:00', created_by=self.office_user,
        )
        # 다른 OUTBOUND_STAGING이 없으므로 None
        self.assertIsNone(wave.outbound_zone)

    def test_pick_detail_to_location_is_outbound_zone(self):
        """TotalPickListDetail.to_location = wave.outbound_zone"""
        self._create_allocated_orders(1)
        wave = WaveService.create_wave(
            wave_time='09:00', created_by=self.office_user,
        )
        detail = TotalPickListDetail.objects.filter(
            pick_list__wave=wave,
        ).first()
        self.assertEqual(detail.to_location, self.loc_outbound)

    def test_no_orders_raises(self):
        """ALLOCATED 주문 없으면 ValueError"""
        with self.assertRaises(ValueError):
            WaveService.create_wave(
                wave_time='09:00', created_by=self.office_user,
            )

    def test_already_waved_orders_excluded(self):
        """이미 wave가 배정된 주문은 제외"""
        orders = self._create_allocated_orders(2)
        existing_wave = Wave.objects.create(
            wave_id='WV-EXISTING-02', wave_time='08:00',
        )
        orders[0].wave = existing_wave
        orders[0].save()

        wave = WaveService.create_wave(
            wave_time='09:00', created_by=self.office_user,
        )
        self.assertEqual(wave.total_orders, 1)

    def test_pick_detail_multi_location(self):
        """여러 로케이션에 걸쳐 피킹"""
        # STOR-01에 상품A 3개, STOR-02에 상품A 5개
        InventoryBalance.objects.filter(product=self.product).update(on_hand_qty=3)
        InventoryBalance.objects.create(
            product=self.product, location=self.loc_storage2,
            client=self.client_obj, on_hand_qty=5,
        )
        # 주문: 상품A 6개 필요
        order = OutboundOrder.objects.create(
            source='TEST', source_order_id='T-MULTI',
            client=self.client_obj, status='ALLOCATED',
            recipient_name='멀티', recipient_phone='010-0000-0000',
            recipient_address='서울', ordered_at=timezone.now(),
        )
        OutboundOrderItem.objects.create(
            order=order, product=self.product, qty=6,
        )

        wave = WaveService.create_wave(
            wave_time='10:00', created_by=self.office_user,
        )
        pl = TotalPickList.objects.get(wave=wave, product=self.product)
        details = list(pl.details.order_by('id'))
        self.assertEqual(len(details), 2)
        self.assertEqual(details[0].qty, 3)  # STOR-01
        self.assertEqual(details[1].qty, 3)  # STOR-02 (나머지)


# ------------------------------------------------------------------
# 웨이브 API 테스트
# ------------------------------------------------------------------

class WaveCreateAPITest(WaveTestMixin, TestCase):
    """POST /api/v1/waves/create/"""

    def test_create_wave(self):
        self._create_allocated_orders(2)
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.post(
            '/api/v1/waves/create/',
            {'wave_time': '09:00'},
            format='json',
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.data['wave_id'].startswith('WV-'))
        self.assertEqual(resp.data['total_orders'], 2)
        self.assertEqual(resp.data['total_skus'], 2)

    def test_create_no_orders(self):
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.post(
            '/api/v1/waves/create/',
            {'wave_time': '09:00'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_invalid_wave_time_format(self):
        self._create_allocated_orders(1)
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.post(
            '/api/v1/waves/create/',
            {'wave_time': '9am'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_field_role_forbidden(self):
        """FIELD 역할은 웨이브 생성 불가"""
        self._create_allocated_orders(1)
        self.api.force_authenticate(user=self.field_user)
        resp = self.api.post(
            '/api/v1/waves/create/',
            {'wave_time': '09:00'},
            format='json',
        )
        self.assertEqual(resp.status_code, 403)

    def test_client_role_forbidden(self):
        self.api.force_authenticate(user=self.client_user)
        resp = self.api.post(
            '/api/v1/waves/create/',
            {'wave_time': '09:00'},
            format='json',
        )
        self.assertEqual(resp.status_code, 403)


class WaveListAPITest(WaveTestMixin, TestCase):
    """GET /api/v1/waves/"""

    def test_list_waves(self):
        self._create_allocated_orders(1)
        WaveService.create_wave(wave_time='09:00', created_by=self.office_user)

        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/waves/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)

    def test_filter_by_status(self):
        self._create_allocated_orders(1)
        WaveService.create_wave(wave_time='09:00', created_by=self.office_user)

        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/waves/', {'status': 'COMPLETED'})
        self.assertEqual(len(resp.data), 0)

        resp = self.api.get('/api/v1/waves/', {'status': 'CREATED'})
        self.assertEqual(len(resp.data), 1)


class WaveDetailAPITest(WaveTestMixin, TestCase):
    """GET /api/v1/waves/{wave_id}/"""

    def test_detail_includes_pick_lists_and_orders(self):
        self._create_allocated_orders(2)
        wave = WaveService.create_wave(
            wave_time='09:00', created_by=self.office_user,
        )
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get(f'/api/v1/waves/{wave.wave_id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['pick_lists']), 2)
        self.assertEqual(len(resp.data['orders']), 2)

    def test_not_found(self):
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/waves/WV-NOTFOUND/')
        self.assertEqual(resp.status_code, 404)


class WaveProgressAPITest(WaveTestMixin, TestCase):
    """GET /api/v1/waves/{wave_id}/progress/"""

    def test_progress_percentages(self):
        self._create_allocated_orders(2)
        wave = WaveService.create_wave(
            wave_time='09:00', created_by=self.office_user,
        )
        # 1/2 피킹 완료 시뮬레이션
        wave.picked_count = 1
        wave.save(update_fields=['picked_count'])

        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get(f'/api/v1/waves/{wave.wave_id}/progress/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['progress']['picking'], 50.0)
        self.assertEqual(resp.data['progress']['shipping'], 0.0)

    def test_progress_includes_pick_lists(self):
        self._create_allocated_orders(1)
        wave = WaveService.create_wave(
            wave_time='09:00', created_by=self.office_user,
        )
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get(f'/api/v1/waves/{wave.wave_id}/progress/')
        self.assertIn('pick_lists', resp.data)
