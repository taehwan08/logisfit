"""
InventoryService 단위 테스트
"""
from django.test import TestCase

from apps.inventory.models import Product, Location, InventoryBalance
from apps.inventory.services import InventoryService
from apps.inventory.exceptions import InsufficientStockError
from apps.clients.models import Client
from apps.history.models import InventoryTransaction


class InventoryServiceTestMixin:
    """테스트용 공통 데이터 생성"""

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
            barcode='P001', name='테스트 상품',
        )
        self.loc_a = Location.objects.create(barcode='LOC-A')
        self.loc_b = Location.objects.create(barcode='LOC-B')


class ReceiveStockTest(InventoryServiceTestMixin, TestCase):
    """입고 테스트"""

    def test_receive_creates_balance(self):
        balance = InventoryService.receive_stock(
            product=self.product, location=self.loc_a,
            client=self.client_obj, qty=100,
        )
        self.assertEqual(balance.on_hand_qty, 100)
        self.assertEqual(balance.allocated_qty, 0)
        self.assertEqual(balance.available_qty, 100)

    def test_receive_increments_existing(self):
        InventoryService.receive_stock(
            product=self.product, location=self.loc_a,
            client=self.client_obj, qty=50,
        )
        balance = InventoryService.receive_stock(
            product=self.product, location=self.loc_a,
            client=self.client_obj, qty=30,
        )
        self.assertEqual(balance.on_hand_qty, 80)

    def test_receive_logs_transaction(self):
        InventoryService.receive_stock(
            product=self.product, location=self.loc_a,
            client=self.client_obj, qty=10,
            reference_id='INB-001',
        )
        txn = InventoryTransaction.objects.first()
        self.assertEqual(txn.transaction_type, 'GR')
        self.assertEqual(txn.qty, 10)
        self.assertEqual(txn.reference_id, 'INB-001')
        self.assertEqual(txn.reference_type, 'INBOUND')


class AllocateStockTest(InventoryServiceTestMixin, TestCase):
    """할당 테스트"""

    def setUp(self):
        super().setUp()
        InventoryService.receive_stock(
            product=self.product, location=self.loc_a,
            client=self.client_obj, qty=100,
        )

    def test_allocate_decreases_available(self):
        InventoryService.allocate_stock(
            product=self.product, client=self.client_obj, qty=40,
        )
        balance = InventoryBalance.objects.get(
            product=self.product, location=self.loc_a,
            client=self.client_obj,
        )
        self.assertEqual(balance.on_hand_qty, 100)
        self.assertEqual(balance.allocated_qty, 40)
        self.assertEqual(balance.available_qty, 60)

    def test_allocate_insufficient_raises(self):
        with self.assertRaises(InsufficientStockError):
            InventoryService.allocate_stock(
                product=self.product, client=self.client_obj, qty=200,
            )

    def test_allocate_fifo_across_locations(self):
        """여러 로케이션에 재고가 있을 때 FIFO(ID순) 할당"""
        InventoryService.receive_stock(
            product=self.product, location=self.loc_b,
            client=self.client_obj, qty=50,
        )
        # loc_a: 100, loc_b: 50 → 총 150 중 120 할당
        InventoryService.allocate_stock(
            product=self.product, client=self.client_obj, qty=120,
        )
        bal_a = InventoryBalance.objects.get(
            product=self.product, location=self.loc_a, client=self.client_obj,
        )
        bal_b = InventoryBalance.objects.get(
            product=self.product, location=self.loc_b, client=self.client_obj,
        )
        # FIFO: loc_a(id가 더 작음) 먼저 100 할당, 나머지 20은 loc_b
        self.assertEqual(bal_a.allocated_qty, 100)
        self.assertEqual(bal_b.allocated_qty, 20)


class DeallocateStockTest(InventoryServiceTestMixin, TestCase):
    """할당 해제 테스트"""

    def setUp(self):
        super().setUp()
        InventoryService.receive_stock(
            product=self.product, location=self.loc_a,
            client=self.client_obj, qty=100,
        )
        InventoryService.allocate_stock(
            product=self.product, client=self.client_obj, qty=40,
        )

    def test_deallocate_restores_available(self):
        InventoryService.deallocate_stock(
            product=self.product, client=self.client_obj, qty=40,
        )
        balance = InventoryBalance.objects.get(
            product=self.product, location=self.loc_a,
            client=self.client_obj,
        )
        self.assertEqual(balance.allocated_qty, 0)
        self.assertEqual(balance.available_qty, 100)

    def test_deallocate_insufficient_raises(self):
        with self.assertRaises(InsufficientStockError):
            InventoryService.deallocate_stock(
                product=self.product, client=self.client_obj, qty=100,
            )

    def test_deallocate_logs_transaction(self):
        InventoryService.deallocate_stock(
            product=self.product, client=self.client_obj, qty=20,
        )
        txn = InventoryTransaction.objects.filter(
            transaction_type='ALC_R',
        ).first()
        self.assertIsNotNone(txn)
        self.assertEqual(txn.qty, 20)


class ShipStockTest(InventoryServiceTestMixin, TestCase):
    """출고 테스트"""

    def setUp(self):
        super().setUp()
        InventoryService.receive_stock(
            product=self.product, location=self.loc_a,
            client=self.client_obj, qty=100,
        )
        InventoryService.allocate_stock(
            product=self.product, client=self.client_obj, qty=50,
        )

    def test_ship_decreases_on_hand_and_allocated(self):
        balance = InventoryService.ship_stock(
            product=self.product, location=self.loc_a,
            client=self.client_obj, qty=30,
        )
        self.assertEqual(balance.on_hand_qty, 70)
        self.assertEqual(balance.allocated_qty, 20)

    def test_ship_insufficient_raises(self):
        with self.assertRaises(InsufficientStockError):
            InventoryService.ship_stock(
                product=self.product, location=self.loc_a,
                client=self.client_obj, qty=200,
            )

    def test_ship_nonexistent_location_raises(self):
        loc_c = Location.objects.create(barcode='LOC-C')
        with self.assertRaises(InsufficientStockError):
            InventoryService.ship_stock(
                product=self.product, location=loc_c,
                client=self.client_obj, qty=10,
            )

    def test_ship_logs_gi_transaction(self):
        InventoryService.ship_stock(
            product=self.product, location=self.loc_a,
            client=self.client_obj, qty=10,
            reference_id='OUT-001',
        )
        txn = InventoryTransaction.objects.filter(
            transaction_type='GI',
        ).first()
        self.assertIsNotNone(txn)
        self.assertEqual(txn.qty, -10)
        self.assertEqual(txn.reference_id, 'OUT-001')


class MoveStockTest(InventoryServiceTestMixin, TestCase):
    """로케이션 이동 테스트"""

    def setUp(self):
        super().setUp()
        InventoryService.receive_stock(
            product=self.product, location=self.loc_a,
            client=self.client_obj, qty=100,
        )

    def test_move_adjusts_both_locations(self):
        from_bal, to_bal = InventoryService.move_stock(
            product=self.product, from_location=self.loc_a,
            to_location=self.loc_b, client=self.client_obj, qty=30,
        )
        self.assertEqual(from_bal.on_hand_qty, 70)
        self.assertEqual(to_bal.on_hand_qty, 30)

    def test_move_insufficient_raises(self):
        with self.assertRaises(InsufficientStockError):
            InventoryService.move_stock(
                product=self.product, from_location=self.loc_a,
                to_location=self.loc_b, client=self.client_obj, qty=200,
            )

    def test_move_logs_mv_transaction(self):
        InventoryService.move_stock(
            product=self.product, from_location=self.loc_a,
            to_location=self.loc_b, client=self.client_obj, qty=10,
        )
        txn = InventoryTransaction.objects.filter(
            transaction_type='MV',
        ).first()
        self.assertIsNotNone(txn)
        self.assertEqual(txn.qty, 10)


class AdjustStockTest(InventoryServiceTestMixin, TestCase):
    """재고 조정 테스트"""

    def setUp(self):
        super().setUp()
        InventoryService.receive_stock(
            product=self.product, location=self.loc_a,
            client=self.client_obj, qty=100,
        )

    def test_adjust_positive(self):
        balance = InventoryService.adjust_stock(
            product=self.product, location=self.loc_a,
            client=self.client_obj, qty=20, reason='실사 차이',
        )
        self.assertEqual(balance.on_hand_qty, 120)

    def test_adjust_negative(self):
        balance = InventoryService.adjust_stock(
            product=self.product, location=self.loc_a,
            client=self.client_obj, qty=-30, reason='파손',
        )
        self.assertEqual(balance.on_hand_qty, 70)

    def test_adjust_negative_insufficient_raises(self):
        with self.assertRaises(InsufficientStockError):
            InventoryService.adjust_stock(
                product=self.product, location=self.loc_a,
                client=self.client_obj, qty=-200,
            )

    def test_adjust_logs_correct_type(self):
        InventoryService.adjust_stock(
            product=self.product, location=self.loc_a,
            client=self.client_obj, qty=5,
        )
        InventoryService.adjust_stock(
            product=self.product, location=self.loc_a,
            client=self.client_obj, qty=-3,
        )
        types = list(
            InventoryTransaction.objects.filter(
                reference_type='ADJUSTMENT',
            ).values_list('transaction_type', flat=True).order_by('id')
        )
        self.assertEqual(types, ['ADJ_PLUS', 'ADJ_MINUS'])


class ReturnStockTest(InventoryServiceTestMixin, TestCase):
    """반품 재입고 테스트"""

    def test_return_increases_on_hand(self):
        balance = InventoryService.return_stock(
            product=self.product, location=self.loc_a,
            client=self.client_obj, qty=25,
            reference_id='RTN-001',
        )
        self.assertEqual(balance.on_hand_qty, 25)

    def test_return_logs_rtn_transaction(self):
        InventoryService.return_stock(
            product=self.product, location=self.loc_a,
            client=self.client_obj, qty=10,
        )
        txn = InventoryTransaction.objects.filter(
            transaction_type='RTN',
        ).first()
        self.assertIsNotNone(txn)
        self.assertEqual(txn.qty, 10)
        self.assertEqual(txn.reference_type, 'RETURN')
