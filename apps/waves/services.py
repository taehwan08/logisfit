"""
웨이브 서비스 레이어
"""
from django.db import transaction
from django.db.models import Sum

from apps.inventory.models import Location, InventoryBalance

from .models import (
    Wave, OutboundOrder, OutboundOrderItem,
    TotalPickList, TotalPickListDetail,
)


class WaveService:

    @staticmethod
    @transaction.atomic
    def create_wave(*, wave_time, created_by):
        """웨이브 생성 프로세스

        1. ALLOCATED 상태의 OutboundOrder 수집 (wave=null)
        2. Wave 생성
        3. SKU별 합산 → TotalPickList
        4. SKU별 피킹 로케이션 FIFO 할당 → TotalPickListDetail
        5. 가용 출고존(OUTBOUND_STAGING, 비어있는) 할당
        6. OutboundOrder.wave 업데이트
        7. Wave 통계 업데이트
        """
        # 1. ALLOCATED + wave 미배정 주문 수집
        orders = OutboundOrder.objects.filter(
            status='ALLOCATED', wave__isnull=True,
        )
        if not orders.exists():
            raise ValueError('할당 완료된 주문이 없습니다.')

        order_ids = list(orders.values_list('id', flat=True))

        # 2. 가용 출고존 탐색 (활성 웨이브에 배정되지 않은 OUTBOUND_STAGING)
        active_zone_ids = (
            Wave.objects
            .filter(
                status__in=['CREATED', 'PICKING', 'DISTRIBUTING', 'SHIPPING'],
                outbound_zone__isnull=False,
            )
            .values_list('outbound_zone_id', flat=True)
        )
        outbound_zone = (
            Location.objects
            .filter(zone_type='OUTBOUND_STAGING', is_active=True)
            .exclude(id__in=active_zone_ids)
            .first()
        )

        # 3. Wave 생성
        wave = Wave.objects.create(
            wave_time=wave_time,
            outbound_zone=outbound_zone,
            created_by=created_by,
        )

        # 4. 주문 → Wave 연결
        orders.update(wave=wave)

        # 5. SKU별 합산 → TotalPickList
        sku_totals = list(
            OutboundOrderItem.objects
            .filter(order_id__in=order_ids)
            .values('product_id')
            .annotate(total=Sum('qty'))
        )

        for sku in sku_totals:
            pick_list = TotalPickList.objects.create(
                wave=wave,
                product_id=sku['product_id'],
                total_qty=sku['total'],
            )

            # 6. FIFO 피킹 로케이션 할당
            balances = (
                InventoryBalance.objects
                .filter(
                    product_id=sku['product_id'],
                    on_hand_qty__gt=0,
                    location__zone_type__in=['STORAGE', 'PICKING'],
                )
                .select_related('location')
                .order_by('id')
            )

            remaining = sku['total']
            for balance in balances:
                if remaining <= 0:
                    break
                pick_qty = min(balance.on_hand_qty, remaining)
                TotalPickListDetail.objects.create(
                    pick_list=pick_list,
                    from_location=balance.location,
                    to_location=outbound_zone,
                    qty=pick_qty,
                )
                remaining -= pick_qty

        # 7. 통계 업데이트
        wave.total_orders = len(order_ids)
        wave.total_skus = len(sku_totals)
        wave.save(update_fields=['total_orders', 'total_skus'])

        return wave
