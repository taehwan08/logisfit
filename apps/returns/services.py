"""
반품 검수 서비스
"""
import logging

from django.db import transaction

from apps.inventory.models import Location
from apps.inventory.services import InventoryService

logger = logging.getLogger(__name__)


class ReturnInspectionService:

    @staticmethod
    @transaction.atomic
    def inspect_item(*, return_order, item, good_qty, defect_qty,
                     disposition, location, performed_by=None):
        """반품 품목 검수 처리

        1) ReturnOrderItem 검수 결과 기록
        2) 재고 처리:
           - RESTOCK: return_stock() → location(반품존)에 양품 입고
           - DEFECT_ZONE: return_stock()로 전체 입고 후
             move_stock()로 불량분 DEFECT zone 이동
           - DISPOSE: 재고 변동 없음
        3) RECEIVED → INSPECTING 자동 전환
        4) 전 아이템 검수 완료 시 → COMPLETED

        Returns:
            (item, order_status, all_inspected)
        """
        # 1. 검수 결과 기록
        item.good_qty = good_qty
        item.defect_qty = defect_qty
        item.disposition = disposition
        item.save(update_fields=['good_qty', 'defect_qty', 'disposition'])

        # 2. 재고 처리
        if disposition == 'RESTOCK' and good_qty > 0:
            InventoryService.return_stock(
                product=item.product,
                location=location,
                client=return_order.client,
                qty=good_qty,
                reference_id=return_order.return_id,
                performed_by=performed_by,
                brand=return_order.brand,
            )

        elif disposition == 'DEFECT_ZONE':
            total = good_qty + defect_qty
            # 전체를 반품존에 입고
            if total > 0:
                InventoryService.return_stock(
                    product=item.product,
                    location=location,
                    client=return_order.client,
                    qty=total,
                    reference_id=return_order.return_id,
                    performed_by=performed_by,
                    brand=return_order.brand,
                )
            # 불량분을 불량존으로 이동
            if defect_qty > 0:
                defect_location = Location.objects.filter(
                    zone_type='DEFECT', is_active=True,
                ).first()
                if defect_location:
                    InventoryService.move_stock(
                        product=item.product,
                        from_location=location,
                        to_location=defect_location,
                        client=return_order.client,
                        qty=defect_qty,
                        reason='반품 불량 이동',
                        reference_id=return_order.return_id,
                        performed_by=performed_by,
                        brand=return_order.brand,
                        transaction_type='MV',
                        reference_type='RETURN',
                    )

        # DISPOSE: 재고 변동 없음

        # 3. 상태 전환
        if return_order.status == 'RECEIVED':
            return_order.status = 'INSPECTING'
            return_order.save(update_fields=['status', 'updated_at'])

        # 4. 전 아이템 검수 완료 확인
        all_inspected = all(
            i.disposition != ''
            for i in return_order.items.all()
        )
        if all_inspected and return_order.status == 'INSPECTING':
            return_order.status = 'COMPLETED'
            return_order.save(update_fields=['status', 'updated_at'])

        return item, return_order.status, all_inspected
