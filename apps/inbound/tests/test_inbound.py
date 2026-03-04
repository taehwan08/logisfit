"""
입고 관리 테스트
"""
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client
from apps.inventory.models import Product, Location, InventoryBalance
from apps.inbound.models import InboundOrder, InboundOrderItem, generate_inbound_id
from apps.history.models import InventoryTransaction


class GenerateInboundIdTest(TestCase):
    """입고번호 자동 채번 테스트"""

    def test_first_of_day(self):
        iid = generate_inbound_id()
        today = timezone.localtime(timezone.now()).strftime('%Y%m%d')
        self.assertEqual(iid, f'IB-{today}-0001')

    def test_sequential(self):
        InboundOrder.objects.create(
            inbound_id=generate_inbound_id(),
            client=Client.objects.create(
                company_name='테스트', business_number='123-45-67890',
                contact_person='A', contact_phone='010-1234-5678',
                contact_email='a@a.com', invoice_email='a@a.com',
            ),
            expected_date=timezone.now().date(),
        )
        iid2 = generate_inbound_id()
        self.assertTrue(iid2.endswith('-0002'))


class InboundOrderViewSetTest(TestCase):
    """입고예정 ViewSet 테스트"""

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
        self.location = Location.objects.create(barcode='LOC-A', zone_type='STORAGE')
        self.user = User.objects.create_user(
            email='admin@test.com', password='test1234',
            name='관리자', role='admin', is_approved=True,
        )
        self.api = APIClient()
        self.api.force_authenticate(user=self.user)

    def _create_order(self, **kwargs):
        defaults = {
            'client': self.client_obj.pk,
            'expected_date': '2026-03-10',
            'items': [
                {'product': self.product.pk, 'expected_qty': 100},
                {'product': self.product2.pk, 'expected_qty': 50},
            ],
        }
        defaults.update(kwargs)
        return self.api.post('/api/v1/inbound/orders/', defaults, format='json')

    @patch('apps.inbound.views.send_inbound_order_notification_async')
    def test_create_order(self, mock_slack):
        resp = self._create_order()
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.data['inbound_id'].startswith('IB-'))
        self.assertEqual(resp.data['status'], 'PLANNED')
        mock_slack.assert_called_once()

    @patch('apps.inbound.views.send_inbound_order_notification_async')
    def test_create_order_with_items(self, mock_slack):
        resp = self._create_order()
        order = InboundOrder.objects.get(pk=resp.data['id'])
        self.assertEqual(order.items.count(), 2)

    def test_list_orders(self):
        InboundOrder.objects.create(
            client=self.client_obj,
            expected_date='2026-03-10',
            created_by=self.user,
        )
        resp = self.api.get('/api/v1/inbound/orders/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['results']), 1)

    def test_filter_by_status(self):
        InboundOrder.objects.create(
            client=self.client_obj, expected_date='2026-03-10',
            status='PLANNED',
        )
        InboundOrder.objects.create(
            client=self.client_obj, expected_date='2026-03-10',
            status='ARRIVED',
        )
        resp = self.api.get('/api/v1/inbound/orders/', {'status': 'PLANNED'})
        self.assertEqual(len(resp.data['results']), 1)

    def test_detail(self):
        order = InboundOrder.objects.create(
            client=self.client_obj, expected_date='2026-03-10',
        )
        InboundOrderItem.objects.create(
            inbound_order=order, product=self.product, expected_qty=100,
        )
        resp = self.api.get(f'/api/v1/inbound/orders/{order.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['items']), 1)


class InboundStatusTransitionTest(TestCase):
    """입고 상태 전이 테스트"""

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
        self.location = Location.objects.create(barcode='LOC-A', zone_type='STORAGE')
        self.user = User.objects.create_user(
            email='admin@test.com', password='test1234',
            name='관리자', role='admin', is_approved=True,
        )
        self.order = InboundOrder.objects.create(
            client=self.client_obj, expected_date='2026-03-10',
        )
        InboundOrderItem.objects.create(
            inbound_order=self.order, product=self.product,
            expected_qty=100,
        )
        self.api = APIClient()
        self.api.force_authenticate(user=self.user)

    def test_arrive(self):
        resp = self.api.post(f'/api/v1/inbound/orders/{self.order.pk}/arrive/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'ARRIVED')

    def test_invalid_transition(self):
        resp = self.api.post(f'/api/v1/inbound/orders/{self.order.pk}/start_inspect/')
        self.assertEqual(resp.status_code, 400)

    def test_full_flow(self):
        """PLANNED → ARRIVED → INSPECTING → INSPECTED → PUTAWAY_COMPLETE"""
        # arrive
        self.api.post(f'/api/v1/inbound/orders/{self.order.pk}/arrive/')

        # start_inspect
        self.api.post(f'/api/v1/inbound/orders/{self.order.pk}/start_inspect/')

        # complete_inspect (검수 수량 업데이트)
        self.api.post(
            f'/api/v1/inbound/orders/{self.order.pk}/complete_inspect/',
            {'items': [{'item_id': self.order.items.first().pk, 'inspected_qty': 95, 'defect_qty': 5}]},
            format='json',
        )
        item = self.order.items.first()
        item.refresh_from_db()
        self.assertEqual(item.inspected_qty, 95)
        self.assertEqual(item.defect_qty, 5)

        # complete_putaway (적치 — 재고 입고)
        resp = self.api.post(
            f'/api/v1/inbound/orders/{self.order.pk}/complete_putaway/',
            {'items': [{'item_id': item.pk, 'putaway_location_id': self.location.pk}]},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'PUTAWAY_COMPLETE')

        # InventoryBalance 확인 (양품: 95 - 5 = 90)
        balance = InventoryBalance.objects.get(
            product=self.product, location=self.location, client=self.client_obj,
        )
        self.assertEqual(balance.on_hand_qty, 90)

        # InventoryTransaction 확인
        txn = InventoryTransaction.objects.filter(
            transaction_type='GR', product=self.product,
        ).first()
        self.assertIsNotNone(txn)
        self.assertEqual(txn.qty, 90)
        self.assertEqual(txn.reference_type, 'INBOUND')
        self.assertIn(self.order.inbound_id, txn.reference_id)
