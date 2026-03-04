"""
사방넷 주문 수집 (Celery periodic task에서 호출)

주기적으로 사방넷 API를 폴링하여 신규 주문을 WMS에 등록합니다.
"""
import logging

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import get_config
from apps.clients.models import Client
from apps.inventory.models import Product
from apps.inventory.services import InventoryService
from apps.inventory.exceptions import InsufficientStockError
from apps.waves.models import OutboundOrder, OutboundOrderItem

from .client import SabangnetClient
from .mappers import map_order

logger = logging.getLogger(__name__)


class SabangnetOrderPoller:
    """사방넷 주문 수집기"""

    def __init__(self):
        self.client = SabangnetClient()

    def poll_orders(self):
        """신규 주문 수집 → WMS 주문 생성

        1. SabangnetClient로 신규 주문 조회
        2. mappers.py로 표준 포맷 변환
        3. 중복 체크 (source + source_order_id)
        4. OutboundOrder 생성 + 재고 할당

        Returns:
            dict: 처리 결과 요약
        """
        client_id = get_config('sabangnet_client_id')
        if not client_id:
            logger.warning('sabangnet_client_id 미설정')
            return {'error': 'sabangnet_client_id 미설정'}

        try:
            wms_client = Client.objects.get(pk=client_id)
        except Client.DoesNotExist:
            logger.error('거래처를 찾을 수 없습니다: %s', client_id)
            return {'error': f'거래처 미존재: {client_id}'}

        # 1. 주문 조회 (최근 1일)
        now = timezone.localtime(timezone.now())
        from_date = (now - timezone.timedelta(days=1)).strftime('%Y-%m-%d')
        to_date = now.strftime('%Y-%m-%d')

        raw_orders = self.client.fetch_new_orders(from_date, to_date)
        if not raw_orders:
            return {'fetched': 0, 'created': 0, 'skipped': 0, 'failed': 0}

        created = 0
        skipped = 0
        failed = 0

        for raw_order in raw_orders:
            # 2. 표준 포맷 변환
            order_data = map_order(raw_order, client_id)
            source_order_id = order_data['source_order_id']

            # 3. 중복 체크
            if OutboundOrder.objects.filter(
                source='SABANGNET',
                source_order_id=source_order_id,
            ).exists():
                skipped += 1
                continue

            # 4. 주문 생성
            try:
                self._create_order(order_data, wms_client)
                created += 1
            except Exception as e:
                failed += 1
                logger.error(
                    '사방넷 주문 생성 실패: order_id=%s error=%s',
                    source_order_id, e,
                )

        result = {
            'fetched': len(raw_orders),
            'created': created,
            'skipped': skipped,
            'failed': failed,
        }
        logger.info('사방넷 주문 수집 완료: %s', result)
        return result

    @transaction.atomic
    def _create_order(self, order_data, wms_client):
        """표준 포맷 데이터로 OutboundOrder 생성 + 재고 할당"""
        shipping = order_data['shipping']
        items_data = order_data['items']

        # 상품 조회
        resolved_items = []
        for item in items_data:
            product = self._resolve_product(item['sku'])
            if not product:
                raise ValueError(f"상품을 찾을 수 없습니다: {item['sku']}")
            resolved_items.append({
                'product': product,
                'qty': item['qty'],
                'source_item_id': item.get('source_item_id', ''),
            })

        # OutboundOrder 생성
        order = OutboundOrder.objects.create(
            source=order_data['source'],
            source_order_id=order_data['source_order_id'],
            client=wms_client,
            order_type=order_data.get('order_type', 'B2C'),
            ordered_at=order_data['ordered_at'],
            recipient_name=shipping['recipient_name'],
            recipient_phone=shipping['recipient_phone'],
            recipient_address=shipping['recipient_address'],
            recipient_zip=shipping.get('recipient_zip', ''),
            shipping_memo=shipping.get('shipping_memo', ''),
        )

        for item in resolved_items:
            OutboundOrderItem.objects.create(
                order=order,
                product=item['product'],
                qty=item['qty'],
                source_item_id=item['source_item_id'],
            )

        # 재고 할당 시도
        hold_reasons = []
        for item in resolved_items:
            try:
                InventoryService.allocate_stock(
                    product=item['product'],
                    client=wms_client,
                    qty=item['qty'],
                    reference_id=order.wms_order_id,
                )
            except InsufficientStockError as e:
                hold_reasons.append(
                    f"{item['product'].name}: 요청 {e.requested}, 가용 {e.available}"
                )

        if hold_reasons:
            order.status = 'HELD'
            order.hold_reason = '; '.join(hold_reasons)
            order.save(update_fields=['status', 'hold_reason', 'updated_at'])
            for item in resolved_items:
                try:
                    InventoryService.deallocate_stock(
                        product=item['product'],
                        client=wms_client,
                        qty=item['qty'],
                        reference_id=order.wms_order_id,
                    )
                except InsufficientStockError:
                    pass
        else:
            order.status = 'ALLOCATED'
            order.save(update_fields=['status', 'updated_at'])

        return order

    @staticmethod
    def _resolve_product(sku):
        """SKU로 상품 조회"""
        from apps.inventory.models import ProductBarcode
        product = Product.objects.filter(barcode=sku).first()
        if product:
            return product
        pb = ProductBarcode.objects.select_related('product').filter(
            barcode=sku,
        ).first()
        return pb.product if pb else None
