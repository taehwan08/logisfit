"""
재고 서비스 레이어

모든 재고 변동은 이 서비스를 통해서만 수행합니다.
각 메서드는 atomic 트랜잭션 내에서 InventoryBalance를 갱신하고
InventoryTransaction(히스토리)을 자동으로 기록합니다.
"""
from django.db import transaction
from django.db.models import F

from .models import InventoryBalance
from .exceptions import InsufficientStockError
from apps.history.models import log_transaction


class InventoryService:

    # ------------------------------------------------------------------
    # 입고
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def receive_stock(*, product, location, client, qty, lot_number='',
                      expiry_date=None, reference_id='', performed_by=None,
                      brand=None):
        """입고 처리: 실물재고 증가 + GR 트랜잭션"""
        balance, _created = InventoryBalance.objects.select_for_update().get_or_create(
            product=product, location=location, client=client,
            lot_number=lot_number,
            defaults={'on_hand_qty': 0, 'expiry_date': expiry_date},
        )
        balance.on_hand_qty = F('on_hand_qty') + qty
        balance.save(update_fields=['on_hand_qty', 'updated_at'])
        balance.refresh_from_db()

        log_transaction(
            client=client, brand=brand, product=product,
            transaction_type='GR', to_location=location,
            qty=qty, balance_after=balance.on_hand_qty,
            reference_type='INBOUND', reference_id=reference_id,
            performed_by=performed_by,
        )
        return balance

    # ------------------------------------------------------------------
    # 할당
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def allocate_stock(*, product, client, qty, reference_id='',
                       performed_by=None, brand=None):
        """할당: 가용재고 → 할당재고

        Client.allocation_rule에 따라 FIFO 또는 LOCATION_PRIORITY로
        밸런스 레코드를 순회하며 필요 수량만큼 할당합니다.
        """
        rule = getattr(client, 'allocation_rule', 'FIFO')

        if rule == 'LOCATION_PRIORITY':
            ordering = ['location__barcode', 'id']
        else:  # FIFO
            ordering = ['id']

        balances = list(
            InventoryBalance.objects.select_for_update()
            .filter(product=product, client=client)
            .order_by(*ordering)
        )

        total_available = sum(b.available_qty for b in balances)
        if total_available < qty:
            raise InsufficientStockError(
                product=product, requested=qty, available=total_available,
                detail='할당 가능 재고 부족',
            )

        remaining = qty
        for balance in balances:
            if remaining <= 0:
                break
            avail = balance.available_qty
            if avail <= 0:
                continue
            alloc = min(avail, remaining)
            balance.allocated_qty = F('allocated_qty') + alloc
            balance.save(update_fields=['allocated_qty', 'updated_at'])
            balance.refresh_from_db()
            remaining -= alloc

            log_transaction(
                client=client, brand=brand, product=product,
                transaction_type='ALC', to_location=balance.location,
                qty=alloc, balance_after=balance.on_hand_qty,
                reference_type='OUTBOUND', reference_id=reference_id,
                performed_by=performed_by,
            )

    # ------------------------------------------------------------------
    # 할당 해제
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def deallocate_stock(*, product, client, qty, reference_id='',
                         performed_by=None, brand=None):
        """할당 해제: 할당재고 → 가용재고"""
        balances = list(
            InventoryBalance.objects.select_for_update()
            .filter(product=product, client=client, allocated_qty__gt=0)
            .order_by('-allocated_qty')
        )

        total_allocated = sum(b.allocated_qty for b in balances)
        if total_allocated < qty:
            raise InsufficientStockError(
                product=product, requested=qty, available=total_allocated,
                detail='할당 해제 가능 수량 부족',
            )

        remaining = qty
        for balance in balances:
            if remaining <= 0:
                break
            dealloc = min(balance.allocated_qty, remaining)
            balance.allocated_qty = F('allocated_qty') - dealloc
            balance.save(update_fields=['allocated_qty', 'updated_at'])
            balance.refresh_from_db()
            remaining -= dealloc

            log_transaction(
                client=client, brand=brand, product=product,
                transaction_type='ALC_R', to_location=balance.location,
                qty=dealloc, balance_after=balance.on_hand_qty,
                reference_type='OUTBOUND', reference_id=reference_id,
                performed_by=performed_by,
            )

    # ------------------------------------------------------------------
    # 출고
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def ship_stock(*, product, location, client, qty, lot_number='',
                   reference_id='', performed_by=None, brand=None):
        """출고 확정: 실물재고 감소 + 할당재고 감소 + GI 트랜잭션"""
        try:
            balance = (
                InventoryBalance.objects.select_for_update()
                .get(product=product, location=location, client=client,
                     lot_number=lot_number)
            )
        except InventoryBalance.DoesNotExist:
            raise InsufficientStockError(
                product=product, requested=qty, available=0,
                detail=f'로케이션 {location}에 재고 없음',
            )

        if balance.on_hand_qty < qty:
            raise InsufficientStockError(
                product=product, requested=qty, available=balance.on_hand_qty,
                detail='실물재고 부족',
            )

        # 할당재고 감소 (할당된 만큼만)
        alloc_decrease = min(balance.allocated_qty, qty)

        balance.on_hand_qty = F('on_hand_qty') - qty
        if alloc_decrease > 0:
            balance.allocated_qty = F('allocated_qty') - alloc_decrease
            balance.save(update_fields=['on_hand_qty', 'allocated_qty', 'updated_at'])
        else:
            balance.save(update_fields=['on_hand_qty', 'updated_at'])
        balance.refresh_from_db()

        log_transaction(
            client=client, brand=brand, product=product,
            transaction_type='GI', from_location=location,
            qty=-qty, balance_after=balance.on_hand_qty,
            reference_type='OUTBOUND', reference_id=reference_id,
            performed_by=performed_by,
        )
        return balance

    # ------------------------------------------------------------------
    # 로케이션 이동
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def move_stock(*, product, from_location, to_location, client, qty,
                   lot_number='', reason='', reference_id='',
                   performed_by=None, brand=None,
                   transaction_type='MV', reference_type='MANUAL'):
        """로케이션 이동: from 감소 + to 증가 + MV 트랜잭션"""
        # 출발지 차감
        try:
            from_balance = (
                InventoryBalance.objects.select_for_update()
                .get(product=product, location=from_location, client=client,
                     lot_number=lot_number)
            )
        except InventoryBalance.DoesNotExist:
            raise InsufficientStockError(
                product=product, requested=qty, available=0,
                detail=f'출발 로케이션 {from_location}에 재고 없음',
            )

        if from_balance.on_hand_qty < qty:
            raise InsufficientStockError(
                product=product, requested=qty,
                available=from_balance.on_hand_qty,
                detail='이동 가능 수량 부족',
            )

        from_balance.on_hand_qty = F('on_hand_qty') - qty
        from_balance.save(update_fields=['on_hand_qty', 'updated_at'])
        from_balance.refresh_from_db()

        # 도착지 증가
        to_balance, _created = InventoryBalance.objects.select_for_update().get_or_create(
            product=product, location=to_location, client=client,
            lot_number=lot_number,
            defaults={'on_hand_qty': 0},
        )
        to_balance.on_hand_qty = F('on_hand_qty') + qty
        to_balance.save(update_fields=['on_hand_qty', 'updated_at'])
        to_balance.refresh_from_db()

        log_transaction(
            client=client, brand=brand, product=product,
            transaction_type=transaction_type,
            from_location=from_location, to_location=to_location,
            qty=qty, balance_after=to_balance.on_hand_qty,
            reference_type=reference_type, reference_id=reference_id,
            reason=reason, performed_by=performed_by,
        )
        return from_balance, to_balance

    # ------------------------------------------------------------------
    # 재고 조정
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def adjust_stock(*, product, location, client, qty, lot_number='',
                     reason='', reference_id='', performed_by=None,
                     brand=None):
        """재고 조정: +면 ADJ_PLUS, -면 ADJ_MINUS"""
        balance, _created = InventoryBalance.objects.select_for_update().get_or_create(
            product=product, location=location, client=client,
            lot_number=lot_number,
            defaults={'on_hand_qty': 0},
        )

        if qty < 0 and balance.on_hand_qty < abs(qty):
            raise InsufficientStockError(
                product=product, requested=abs(qty),
                available=balance.on_hand_qty,
                detail='조정 감소 수량이 실물재고 초과',
            )

        txn_type = 'ADJ_PLUS' if qty >= 0 else 'ADJ_MINUS'

        balance.on_hand_qty = F('on_hand_qty') + qty
        balance.save(update_fields=['on_hand_qty', 'updated_at'])
        balance.refresh_from_db()

        log_transaction(
            client=client, brand=brand, product=product,
            transaction_type=txn_type, to_location=location,
            qty=qty, balance_after=balance.on_hand_qty,
            reference_type='ADJUSTMENT', reference_id=reference_id,
            reason=reason, performed_by=performed_by,
        )
        return balance

    # ------------------------------------------------------------------
    # 반품 재입고
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def return_stock(*, product, location, client, qty, lot_number='',
                     reference_id='', performed_by=None, brand=None):
        """반품 재입고: 실물재고 증가 + RTN 트랜잭션"""
        balance, _created = InventoryBalance.objects.select_for_update().get_or_create(
            product=product, location=location, client=client,
            lot_number=lot_number,
            defaults={'on_hand_qty': 0},
        )
        balance.on_hand_qty = F('on_hand_qty') + qty
        balance.save(update_fields=['on_hand_qty', 'updated_at'])
        balance.refresh_from_db()

        log_transaction(
            client=client, brand=brand, product=product,
            transaction_type='RTN', to_location=location,
            qty=qty, balance_after=balance.on_hand_qty,
            reference_type='RETURN', reference_id=reference_id,
            performed_by=performed_by,
        )
        return balance
