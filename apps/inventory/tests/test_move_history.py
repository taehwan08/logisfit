"""
로케이션 이동 → InventoryBalance + 히스토리 연동 테스트
"""
import json

from django.test import TestCase, RequestFactory
from django.contrib.sessions.backends.db import SessionStore

from apps.accounts.models import User
from apps.clients.models import Client
from apps.inventory.models import (
    Product, Location, InventorySession, InventoryRecord, InventoryBalance,
)
from apps.inventory.services import InventoryService
from apps.inventory.views import move_record
from apps.history.models import InventoryTransaction


class MoveRecordHistoryTest(TestCase):
    """move_record 뷰 호출 후 InventoryTransaction에 MV가 기록되는지 확인"""

    def setUp(self):
        self.factory = RequestFactory()

        self.user = User.objects.create_user(
            email='staff@test.com', password='test1234',
            name='작업자', role='office', is_approved=True,
        )
        self.client_obj = Client.objects.create(
            company_name='테스트 거래처',
            business_number='123-45-67890',
            contact_person='홍길동',
            contact_phone='010-1234-5678',
            contact_email='test@test.com',
            invoice_email='invoice@test.com',
        )
        self.product = Product.objects.create(
            barcode='P001', name='테스트 상품',
        )
        self.loc_a = Location.objects.create(barcode='LOC-A')
        self.loc_b = Location.objects.create(barcode='LOC-B')

        # InventorySession + InventoryRecord 셋업
        self.session = InventorySession.objects.create(name='테스트 세션')
        self.record = InventoryRecord.objects.create(
            session=self.session,
            location=self.loc_a,
            barcode='P001',
            product_name='테스트 상품',
            quantity=100,
        )

        # InventoryBalance 셋업
        InventoryService.receive_stock(
            product=self.product, location=self.loc_a,
            client=self.client_obj, qty=100,
        )

    def _make_move_request(self, record_id, target_location_id, move_quantity):
        """move_record 뷰를 직접 호출"""
        body = json.dumps({
            'record_id': record_id,
            'target_location_id': target_location_id,
            'move_quantity': move_quantity,
        })
        request = self.factory.post(
            '/inventory/api/records/move/',
            data=body, content_type='application/json',
        )
        request.user = self.user
        request.session = SessionStore()
        return move_record(request)

    def test_move_creates_mv_transaction(self):
        """이동 후 MV 트랜잭션이 기록된다"""
        resp = self._make_move_request(self.record.pk, self.loc_b.pk, 30)
        data = json.loads(resp.content)

        self.assertTrue(data['success'])
        self.assertEqual(data['source_location_barcode'], 'LOC-A')
        self.assertEqual(data['target_location_barcode'], 'LOC-B')

        # 히스토리 확인
        txn = InventoryTransaction.objects.filter(transaction_type='MV').first()
        self.assertIsNotNone(txn)
        self.assertEqual(txn.qty, 30)
        self.assertEqual(txn.from_location, self.loc_a)
        self.assertEqual(txn.to_location, self.loc_b)
        self.assertEqual(txn.product, self.product)
        self.assertEqual(txn.performed_by, self.user)

    def test_move_updates_inventory_balance(self):
        """이동 후 InventoryBalance가 갱신된다"""
        self._make_move_request(self.record.pk, self.loc_b.pk, 40)

        bal_a = InventoryBalance.objects.get(
            product=self.product, location=self.loc_a, client=self.client_obj,
        )
        bal_b = InventoryBalance.objects.get(
            product=self.product, location=self.loc_b, client=self.client_obj,
        )
        self.assertEqual(bal_a.on_hand_qty, 60)
        self.assertEqual(bal_b.on_hand_qty, 40)

    def test_full_move_creates_transaction(self):
        """전체 수량 이동 시에도 히스토리 기록"""
        self._make_move_request(self.record.pk, self.loc_b.pk, 100)

        txn = InventoryTransaction.objects.filter(transaction_type='MV').first()
        self.assertIsNotNone(txn)
        self.assertEqual(txn.qty, 100)

        bal_a = InventoryBalance.objects.get(
            product=self.product, location=self.loc_a, client=self.client_obj,
        )
        bal_b = InventoryBalance.objects.get(
            product=self.product, location=self.loc_b, client=self.client_obj,
        )
        self.assertEqual(bal_a.on_hand_qty, 0)
        self.assertEqual(bal_b.on_hand_qty, 100)

    def test_move_without_balance_still_succeeds(self):
        """InventoryBalance가 없는 상품도 InventoryRecord 이동은 성공"""
        # Balance 없는 별도 레코드
        record2 = InventoryRecord.objects.create(
            session=self.session,
            location=self.loc_a,
            barcode='UNKNOWN-BARCODE',
            product_name='미등록 상품',
            quantity=50,
        )
        resp = self._make_move_request(record2.pk, self.loc_b.pk, 20)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])

        # MV 트랜잭션은 생성되지 않음 (상품 미매칭)
        mv_count = InventoryTransaction.objects.filter(
            transaction_type='MV',
        ).count()
        # 기존 테스트에서 생성된 것이 없으므로 0
        self.assertEqual(mv_count, 0)

    def test_response_format_unchanged(self):
        """기존 응답 포맷이 유지된다"""
        resp = self._make_move_request(self.record.pk, self.loc_b.pk, 10)
        data = json.loads(resp.content)

        # 기존 응답 필드 확인
        self.assertIn('success', data)
        self.assertIn('message', data)
        self.assertIn('source_location_barcode', data)
        self.assertIn('target_location_barcode', data)
        self.assertIn('source_record', data)
        self.assertIn('target_record', data)
