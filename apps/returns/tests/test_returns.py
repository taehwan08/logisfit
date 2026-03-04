"""
반품 관리 테스트

모델, CRUD API, 검수 서비스, PDA 검수 API 테스트.
"""
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client
from apps.inventory.models import (
    Product, ProductBarcode, Location, InventoryBalance,
)
from apps.history.models import InventoryTransaction
from apps.returns.models import ReturnOrder, ReturnOrderItem
from apps.returns.services import ReturnInspectionService


class ReturnTestMixin:
    """반품 테스트 공통 데이터"""

    def setUp(self):
        self.client_obj = Client.objects.create(
            company_name='테스트거래처', business_number='123-45-67890',
            contact_person='홍', contact_phone='010',
            contact_email='t@t.com', invoice_email='i@t.com',
        )
        self.product = Product.objects.create(
            barcode='P001', name='상품A', client=self.client_obj,
        )
        self.product2 = Product.objects.create(
            barcode='P002', name='상품B', client=self.client_obj,
        )
        ProductBarcode.objects.create(
            product=self.product, barcode='8801234567890', is_primary=True,
        )

        self.loc_return = Location.objects.create(
            barcode='RTN-01', zone_type='RETURN',
        )
        self.loc_defect = Location.objects.create(
            barcode='DEF-01', zone_type='DEFECT',
        )
        self.loc_storage = Location.objects.create(
            barcode='STOR-01', zone_type='STORAGE',
        )

        self.field_user = User.objects.create_user(
            email='field@test.com', password='test1234',
            name='필드', role='field', is_approved=True,
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

    def _create_return_order(self, **kwargs):
        defaults = dict(
            client=self.client_obj,
            return_reason='CUSTOMER_CHANGE',
            status='RECEIVED',
        )
        defaults.update(kwargs)
        order = ReturnOrder.objects.create(**defaults)
        ReturnOrderItem.objects.create(
            return_order=order, product=self.product, qty=10,
        )
        ReturnOrderItem.objects.create(
            return_order=order, product=self.product2, qty=5,
        )
        return order


# ------------------------------------------------------------------
# 모델 테스트
# ------------------------------------------------------------------

class ReturnOrderModelTest(ReturnTestMixin, TestCase):

    def test_generate_return_id_format(self):
        order = self._create_return_order()
        self.assertRegex(order.return_id, r'^RT-\d{8}-\d{4}$')

    def test_generate_return_id_sequential(self):
        o1 = self._create_return_order()
        o2 = self._create_return_order()
        seq1 = int(o1.return_id.split('-')[-1])
        seq2 = int(o2.return_id.split('-')[-1])
        self.assertEqual(seq2, seq1 + 1)

    def test_auto_generate_on_save(self):
        order = ReturnOrder(
            client=self.client_obj, return_reason='DEFECT',
        )
        order.save()
        self.assertTrue(order.return_id.startswith('RT-'))


# ------------------------------------------------------------------
# CRUD API 테스트
# ------------------------------------------------------------------

class ReturnOrderCRUDTest(ReturnTestMixin, TestCase):

    def test_list_returns(self):
        self._create_return_order()
        self._create_return_order()

        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/returns/orders/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['results']), 2)

    def test_list_filter_by_client(self):
        self._create_return_order()
        other_client = Client.objects.create(
            company_name='다른거래처', business_number='999-99-99999',
            contact_person='김', contact_phone='011',
            contact_email='o@o.com', invoice_email='oi@o.com',
        )
        self._create_return_order(client=other_client)

        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get(
            '/api/v1/returns/orders/',
            {'client_id': self.client_obj.id},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['results']), 1)

    def test_list_filter_by_status(self):
        self._create_return_order(status='RECEIVED')
        self._create_return_order(status='COMPLETED')

        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/returns/orders/', {'status': 'RECEIVED'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['results']), 1)

    def test_create_return_with_items(self):
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.post('/api/v1/returns/orders/', {
            'client': self.client_obj.id,
            'return_reason': 'WRONG_DELIVERY',
            'notes': '오배송 반품',
            'items': [
                {'product': self.product.id, 'qty': 3},
                {'product': self.product2.id, 'qty': 2},
            ],
        }, format='json')

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(len(resp.data['items']), 2)
        self.assertTrue(
            ReturnOrder.objects.filter(return_reason='WRONG_DELIVERY').exists()
        )

    def test_detail_includes_items(self):
        order = self._create_return_order()
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get(f'/api/v1/returns/orders/{order.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('items', resp.data)
        self.assertEqual(len(resp.data['items']), 2)

    def test_create_auto_assigns_return_id(self):
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.post('/api/v1/returns/orders/', {
            'client': self.client_obj.id,
            'return_reason': 'OTHER',
            'items': [{'product': self.product.id, 'qty': 1}],
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertRegex(resp.data['return_id'], r'^RT-\d{8}-\d{4}$')


# ------------------------------------------------------------------
# 검수 서비스 테스트
# ------------------------------------------------------------------

class ReturnInspectionServiceTest(ReturnTestMixin, TestCase):

    def test_restock_creates_inventory(self):
        """RESTOCK → 반품존에 양품 재고 증가"""
        order = self._create_return_order()
        item = order.items.filter(product=self.product).first()

        ReturnInspectionService.inspect_item(
            return_order=order, item=item,
            good_qty=8, defect_qty=2, disposition='RESTOCK',
            location=self.loc_return, performed_by=self.field_user,
        )

        balance = InventoryBalance.objects.get(
            product=self.product, location=self.loc_return,
        )
        self.assertEqual(balance.on_hand_qty, 8)

        # RTN 트랜잭션 확인
        txn = InventoryTransaction.objects.filter(
            product=self.product, transaction_type='RTN',
        ).first()
        self.assertIsNotNone(txn)
        self.assertEqual(txn.qty, 8)

    def test_defect_zone_moves_to_defect(self):
        """DEFECT_ZONE → 전체 입고 후 불량분 DEFECT zone 이동"""
        order = self._create_return_order()
        item = order.items.filter(product=self.product).first()

        ReturnInspectionService.inspect_item(
            return_order=order, item=item,
            good_qty=7, defect_qty=3, disposition='DEFECT_ZONE',
            location=self.loc_return, performed_by=self.field_user,
        )

        # 반품존: 전체 10 입고 - 3 이동 = 7
        rtn_balance = InventoryBalance.objects.get(
            product=self.product, location=self.loc_return,
        )
        self.assertEqual(rtn_balance.on_hand_qty, 7)

        # 불량존: 3
        def_balance = InventoryBalance.objects.get(
            product=self.product, location=self.loc_defect,
        )
        self.assertEqual(def_balance.on_hand_qty, 3)

    def test_dispose_no_inventory_change(self):
        """DISPOSE → 재고 변동 없음"""
        order = self._create_return_order()
        item = order.items.filter(product=self.product).first()

        ReturnInspectionService.inspect_item(
            return_order=order, item=item,
            good_qty=0, defect_qty=10, disposition='DISPOSE',
            location=self.loc_return, performed_by=self.field_user,
        )

        self.assertFalse(
            InventoryBalance.objects.filter(product=self.product).exists()
        )

    def test_first_inspect_transitions_to_inspecting(self):
        """첫 검수 시 RECEIVED → INSPECTING"""
        order = self._create_return_order()
        item = order.items.filter(product=self.product).first()

        _, order_status, all_inspected = ReturnInspectionService.inspect_item(
            return_order=order, item=item,
            good_qty=10, defect_qty=0, disposition='RESTOCK',
            location=self.loc_return, performed_by=self.field_user,
        )

        self.assertFalse(all_inspected)  # product2 아직
        order.refresh_from_db()
        self.assertEqual(order.status, 'INSPECTING')

    def test_all_inspected_transitions_to_completed(self):
        """전 아이템 검수 완료 → COMPLETED"""
        order = self._create_return_order()
        item1 = order.items.filter(product=self.product).first()
        item2 = order.items.filter(product=self.product2).first()

        ReturnInspectionService.inspect_item(
            return_order=order, item=item1,
            good_qty=10, defect_qty=0, disposition='RESTOCK',
            location=self.loc_return, performed_by=self.field_user,
        )

        _, order_status, all_inspected = ReturnInspectionService.inspect_item(
            return_order=order, item=item2,
            good_qty=5, defect_qty=0, disposition='RESTOCK',
            location=self.loc_return, performed_by=self.field_user,
        )

        self.assertTrue(all_inspected)
        order.refresh_from_db()
        self.assertEqual(order.status, 'COMPLETED')


# ------------------------------------------------------------------
# PDA 반품 검수 API 테스트
# ------------------------------------------------------------------

class PDAReturnInspectAPITest(ReturnTestMixin, TestCase):

    def test_inspect_restock_success(self):
        order = self._create_return_order()
        self.api.force_authenticate(user=self.field_user)

        resp = self.api.post(
            f'/api/v1/returns/{order.return_id}/inspect/',
            {
                'product_barcode': '8801234567890',
                'good_qty': 9,
                'defect_qty': 1,
                'disposition': 'RESTOCK',
            },
            format='json',
        )

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['success'])
        self.assertEqual(resp.data['item']['good_qty'], 9)
        self.assertEqual(resp.data['item']['defect_qty'], 1)
        self.assertEqual(resp.data['order_status'], 'INSPECTING')

        # 재고 확인
        balance = InventoryBalance.objects.get(
            product=self.product, location=self.loc_return,
        )
        self.assertEqual(balance.on_hand_qty, 9)

    def test_inspect_defect_zone_success(self):
        order = self._create_return_order()
        self.api.force_authenticate(user=self.field_user)

        resp = self.api.post(
            f'/api/v1/returns/{order.return_id}/inspect/',
            {
                'product_barcode': 'P001',
                'good_qty': 6,
                'defect_qty': 4,
                'disposition': 'DEFECT_ZONE',
            },
            format='json',
        )

        self.assertEqual(resp.status_code, 200)

        # 반품존: 10 입고 - 4 이동 = 6
        rtn_bal = InventoryBalance.objects.get(
            product=self.product, location=self.loc_return,
        )
        self.assertEqual(rtn_bal.on_hand_qty, 6)

        # 불량존: 4
        def_bal = InventoryBalance.objects.get(
            product=self.product, location=self.loc_defect,
        )
        self.assertEqual(def_bal.on_hand_qty, 4)

    def test_inspect_wrong_status(self):
        order = self._create_return_order(status='COMPLETED')
        self.api.force_authenticate(user=self.field_user)

        resp = self.api.post(
            f'/api/v1/returns/{order.return_id}/inspect/',
            {
                'product_barcode': 'P001',
                'good_qty': 10,
                'defect_qty': 0,
                'disposition': 'RESTOCK',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_inspect_unknown_barcode(self):
        order = self._create_return_order()
        self.api.force_authenticate(user=self.field_user)

        resp = self.api.post(
            f'/api/v1/returns/{order.return_id}/inspect/',
            {
                'product_barcode': 'UNKNOWN',
                'good_qty': 1,
                'defect_qty': 0,
                'disposition': 'RESTOCK',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 404)

    def test_inspect_product_not_in_order(self):
        order = self._create_return_order()
        extra = Product.objects.create(
            barcode='P999', name='미포함상품', client=self.client_obj,
        )
        self.api.force_authenticate(user=self.field_user)

        resp = self.api.post(
            f'/api/v1/returns/{order.return_id}/inspect/',
            {
                'product_barcode': 'P999',
                'good_qty': 1,
                'defect_qty': 0,
                'disposition': 'RESTOCK',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 404)

    def test_client_role_forbidden(self):
        order = self._create_return_order()
        self.api.force_authenticate(user=self.client_user)

        resp = self.api.post(
            f'/api/v1/returns/{order.return_id}/inspect/',
            {
                'product_barcode': 'P001',
                'good_qty': 1,
                'defect_qty': 0,
                'disposition': 'RESTOCK',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 403)
