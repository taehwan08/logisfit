"""
재고 외부 제공 API 테스트
"""
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client
from apps.inventory.models import Product, Location, SafetyStock
from apps.inventory.services import InventoryService


class InventoryAPITestMixin:
    """테스트용 공통 데이터"""

    def setUp(self):
        self.client_obj = Client.objects.create(
            company_name='테스트 거래처',
            business_number='123-45-67890',
            contact_person='홍길동',
            contact_phone='010-1234-5678',
            contact_email='test@test.com',
            invoice_email='invoice@test.com',
        )
        self.client_obj2 = Client.objects.create(
            company_name='다른 거래처',
            business_number='987-65-43210',
            contact_person='김철수',
            contact_phone='010-9876-5432',
            contact_email='test2@test.com',
            invoice_email='invoice2@test.com',
        )
        self.product = Product.objects.create(
            barcode='SKU-A001', name='테스트 상품', client=self.client_obj,
        )
        self.product2 = Product.objects.create(
            barcode='SKU-A002', name='테스트 상품2', client=self.client_obj,
        )
        self.loc_storage = Location.objects.create(
            barcode='B9-A-03-02-01', zone_type='STORAGE',
        )
        self.loc_picking = Location.objects.create(
            barcode='B9-B-01-01-03', zone_type='PICKING',
        )

        # 재고 셋업
        InventoryService.receive_stock(
            product=self.product, location=self.loc_storage,
            client=self.client_obj, qty=300,
        )
        InventoryService.receive_stock(
            product=self.product, location=self.loc_picking,
            client=self.client_obj, qty=200,
        )
        InventoryService.allocate_stock(
            product=self.product, client=self.client_obj, qty=120,
        )

        # 안전재고
        SafetyStock.objects.create(
            product=self.product, client=self.client_obj, min_qty=100,
        )

        # 사용자
        self.admin_user = User.objects.create_user(
            email='admin@test.com', password='test1234',
            name='관리자', role='admin', is_approved=True,
        )
        self.client_user = User.objects.create_user(
            email='client@test.com', password='test1234',
            name='거래처유저', role='client', is_approved=True,
        )
        self.client_user.clients.add(self.client_obj)

        self.other_client_user = User.objects.create_user(
            email='other@test.com', password='test1234',
            name='다른거래처유저', role='client', is_approved=True,
        )
        self.other_client_user.clients.add(self.client_obj2)

        self.api = APIClient()


class InventoryDetailAPITest(InventoryAPITestMixin, TestCase):
    """GET /api/v1/inventory/ 테스트"""

    def test_requires_authentication(self):
        resp = self.api.get(reverse('inventory-detail'), {'client_id': self.client_obj.pk})
        self.assertIn(resp.status_code, [401, 403])

    def test_requires_client_id(self):
        self.api.force_authenticate(user=self.admin_user)
        resp = self.api.get(reverse('inventory-detail'))
        self.assertEqual(resp.status_code, 400)

    def test_admin_can_query_any_client(self):
        self.api.force_authenticate(user=self.admin_user)
        resp = self.api.get(reverse('inventory-detail'), {'client_id': self.client_obj.pk})
        self.assertEqual(resp.status_code, 200)
        results = resp.data['results']
        self.assertEqual(len(results), 1)

    def test_response_structure(self):
        self.api.force_authenticate(user=self.admin_user)
        resp = self.api.get(reverse('inventory-detail'), {'client_id': self.client_obj.pk})
        item = resp.data['results'][0]

        self.assertEqual(item['sku'], 'SKU-A001')
        self.assertEqual(item['product_name'], '테스트 상품')
        self.assertEqual(item['on_hand'], 500)
        self.assertEqual(item['allocated'], 120)
        self.assertEqual(item['available'], 380)
        self.assertEqual(item['safety_stock'], 100)
        self.assertFalse(item['is_below_safety'])
        self.assertEqual(len(item['locations']), 2)

    def test_locations_detail(self):
        self.api.force_authenticate(user=self.admin_user)
        resp = self.api.get(reverse('inventory-detail'), {'client_id': self.client_obj.pk})
        locations = resp.data['results'][0]['locations']
        loc_codes = {loc['location_code'] for loc in locations}
        self.assertIn('B9-A-03-02-01', loc_codes)
        self.assertIn('B9-B-01-01-03', loc_codes)

    def test_filter_by_sku(self):
        self.api.force_authenticate(user=self.admin_user)
        resp = self.api.get(reverse('inventory-detail'), {
            'client_id': self.client_obj.pk,
            'sku': 'SKU-A001',
        })
        self.assertEqual(len(resp.data['results']), 1)

        resp = self.api.get(reverse('inventory-detail'), {
            'client_id': self.client_obj.pk,
            'sku': 'NONEXIST',
        })
        self.assertEqual(len(resp.data['results']), 0)

    def test_client_user_can_query_own(self):
        self.api.force_authenticate(user=self.client_user)
        resp = self.api.get(reverse('inventory-detail'), {'client_id': self.client_obj.pk})
        self.assertEqual(resp.status_code, 200)

    def test_client_user_cannot_query_others(self):
        self.api.force_authenticate(user=self.client_user)
        resp = self.api.get(reverse('inventory-detail'), {'client_id': self.client_obj2.pk})
        self.assertEqual(resp.status_code, 403)

    def test_client_user_requires_client_id(self):
        self.api.force_authenticate(user=self.client_user)
        resp = self.api.get(reverse('inventory-detail'))
        self.assertEqual(resp.status_code, 403)

    def test_safety_stock_below(self):
        """실물재고가 안전재고 미만이면 is_below_safety=True"""
        SafetyStock.objects.filter(product=self.product).update(min_qty=9999)
        self.api.force_authenticate(user=self.admin_user)
        resp = self.api.get(reverse('inventory-detail'), {'client_id': self.client_obj.pk})
        self.assertTrue(resp.data['results'][0]['is_below_safety'])


class InventoryBulkAPITest(InventoryAPITestMixin, TestCase):
    """GET /api/v1/inventory/bulk/ 테스트"""

    def test_requires_client_id(self):
        self.api.force_authenticate(user=self.admin_user)
        resp = self.api.get(reverse('inventory-bulk'))
        self.assertEqual(resp.status_code, 400)

    def test_returns_paginated(self):
        self.api.force_authenticate(user=self.admin_user)
        resp = self.api.get(reverse('inventory-bulk'), {'client_id': self.client_obj.pk})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('results', resp.data)
        self.assertIn('count', resp.data)

    def test_no_locations_in_bulk(self):
        self.api.force_authenticate(user=self.admin_user)
        resp = self.api.get(reverse('inventory-bulk'), {'client_id': self.client_obj.pk})
        for item in resp.data['results']:
            self.assertNotIn('locations', item)

    def test_client_permission(self):
        self.api.force_authenticate(user=self.other_client_user)
        resp = self.api.get(reverse('inventory-bulk'), {'client_id': self.client_obj.pk})
        self.assertEqual(resp.status_code, 403)
