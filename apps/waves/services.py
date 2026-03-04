"""
웨이브 서비스 레이어
"""
import logging

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.inventory.models import Location, InventoryBalance
from apps.inventory.services import InventoryService

from .models import (
    Wave, OutboundOrder, OutboundOrderItem,
    TotalPickList, TotalPickListDetail,
)

logger = logging.getLogger(__name__)


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


class ShipmentService:

    @staticmethod
    @transaction.atomic
    def confirm_shipment(order, tracking_number=None, performed_by=None):
        """출고 확정

        1. 상태 검증: INSPECTED 상태만 출고 가능
        2. 각 OutboundOrderItem에 대해 InventoryService.ship_stock() 호출
        3. OutboundOrder 업데이트 (SHIPPED, tracking_number, shipped_at)
        4. Wave.shipped_count += 1
        5. 웨이브 내 모든 주문 출고 완료 시 웨이브 완료 처리
        """
        # 1. 상태 검증
        if order.status != 'INSPECTED':
            raise ValueError(
                f'INSPECTED 상태의 주문만 출고 가능합니다. '
                f'현재 상태: {order.get_status_display()}'
            )

        wave = order.wave
        if not wave:
            raise ValueError('웨이브에 배정되지 않은 주문입니다.')

        outbound_zone = wave.outbound_zone

        # 2. 각 품목 출고 처리 (출고존에서 차감)
        for item in order.items.select_related('product').all():
            if outbound_zone:
                InventoryService.ship_stock(
                    product=item.product,
                    location=outbound_zone,
                    client=order.client,
                    qty=item.qty,
                    reference_id=order.wms_order_id,
                    performed_by=performed_by,
                    brand=order.brand,
                )

        # 3. 주문 업데이트
        order.status = 'SHIPPED'
        if tracking_number:
            order.tracking_number = tracking_number
        order.shipped_at = timezone.now()
        order.save(update_fields=[
            'status', 'tracking_number', 'shipped_at', 'updated_at',
        ])

        # 4. Wave.shipped_count 증가
        wave = Wave.objects.select_for_update().get(pk=wave.pk)
        wave.shipped_count += 1

        if wave.status in ('DISTRIBUTING', 'INSPECTED'):
            wave.status = 'SHIPPING'

        wave.save(update_fields=['shipped_count', 'status'])

        # Webhook 이벤트 발행
        from apps.webhooks.services import publish_event
        from apps.webhooks.models import WebhookEvents
        publish_event(WebhookEvents.ORDER_SHIPPED, {
            'wms_order_id': order.wms_order_id,
            'source': order.source,
            'source_order_id': order.source_order_id,
            'tracking_number': order.tracking_number,
            'carrier': order.carrier.code if order.carrier else None,
            'shipped_at': str(order.shipped_at),
        })

        # 5. 웨이브 완료 확인
        all_shipped = not wave.orders.exclude(status='SHIPPED').exists()
        if all_shipped:
            ShipmentService._complete_wave(wave, performed_by=performed_by)

        return order

    @staticmethod
    def _complete_wave(wave, performed_by=None):
        """웨이브 완료 처리

        1. 출고존 잔여 재고 → 보관존 복귀
        2. Wave.status = COMPLETED
        """
        outbound_zone = wave.outbound_zone

        # 잔여 재고 복귀
        if outbound_zone:
            leftover_balances = InventoryBalance.objects.filter(
                location=outbound_zone,
                on_hand_qty__gt=0,
            ).select_related('product', 'client')

            # 복귀 대상 보관존 (첫 번째 활성 STORAGE)
            return_location = (
                Location.objects
                .filter(zone_type='STORAGE', is_active=True)
                .first()
            )

            if return_location:
                for balance in leftover_balances:
                    InventoryService.move_stock(
                        product=balance.product,
                        from_location=outbound_zone,
                        to_location=return_location,
                        client=balance.client,
                        qty=balance.on_hand_qty,
                        reference_id=wave.wave_id,
                        performed_by=performed_by,
                        transaction_type='WV_RTN',
                        reference_type='WAVE',
                    )

        wave.status = 'COMPLETED'
        wave.completed_at = timezone.now()
        wave.save(update_fields=['status', 'completed_at'])


