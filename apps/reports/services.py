"""
리포트 쿼리 서비스

각 리포트의 데이터 수집 로직을 정의합니다.
"""
from collections import defaultdict

from django.db.models import Sum, Count, Q

from apps.history.models import InventoryTransaction
from apps.inventory.models import check_safety_stock_alerts
from apps.waves.models import OutboundOrder, TotalPickListDetail


def get_inventory_ledger(*, client_id, date_from, date_to):
    """수불부 리포트

    SKU별 기초재고 + 입고/출고/조정/이동 + 기말재고
    """
    # 기간 내 트랜잭션
    txns = (
        InventoryTransaction.objects
        .filter(client_id=client_id, timestamp__date__gte=date_from, timestamp__date__lte=date_to)
        .select_related('product')
    )

    # product별 집계
    product_data = defaultdict(lambda: {
        'inbound_qty': 0,
        'return_qty': 0,
        'outbound_qty': 0,
        'adjustment_qty': 0,
        'movement_qty': 0,
    })

    # product 정보 캐시
    product_info = {}
    # 기말재고 계산을 위한 마지막 balance_after 추적
    last_txn = {}

    for txn in txns.order_by('timestamp'):
        pid = txn.product_id
        if pid not in product_info:
            product_info[pid] = {
                'sku': txn.product.barcode,
                'product_name': txn.product.name,
            }

        d = product_data[pid]
        tt = txn.transaction_type

        if tt == 'GR':
            d['inbound_qty'] += txn.qty
        elif tt == 'RTN':
            d['return_qty'] += txn.qty
        elif tt == 'GI':
            d['outbound_qty'] += txn.qty  # 음수
        elif tt in ('ADJ_PLUS', 'ADJ_MINUS'):
            d['adjustment_qty'] += txn.qty
        elif tt in ('MV', 'WV_MV'):
            d['movement_qty'] += txn.qty

        last_txn[pid] = txn.balance_after

    # 기초재고: date_from 직전 마지막 balance_after
    opening_balances = {}
    for pid in product_data:
        prev = (
            InventoryTransaction.objects
            .filter(client_id=client_id, product_id=pid, timestamp__date__lt=date_from)
            .order_by('-timestamp')
            .values_list('balance_after', flat=True)
            .first()
        )
        opening_balances[pid] = prev or 0

    results = []
    for pid, d in product_data.items():
        opening = opening_balances.get(pid, 0)
        closing = last_txn.get(pid, opening)
        info = product_info[pid]
        results.append({
            'sku': info['sku'],
            'product_name': info['product_name'],
            'opening_balance': opening,
            'inbound_qty': d['inbound_qty'],
            'return_qty': d['return_qty'],
            'outbound_qty': d['outbound_qty'],
            'adjustment_qty': d['adjustment_qty'],
            'movement_qty': d['movement_qty'],
            'closing_balance': closing,
        })

    results.sort(key=lambda r: r['sku'])
    return results


def get_shipment_summary(*, date_from, date_to, client_id=None):
    """출고 실적 리포트

    일별/화주사별/브랜드별 출고 건수·수량 + 웨이브별 출고 실적
    """
    qs = OutboundOrder.objects.filter(
        status='SHIPPED',
        shipped_at__date__gte=date_from,
        shipped_at__date__lte=date_to,
    )
    if client_id:
        qs = qs.filter(client_id=client_id)

    # 일별/화주사별/브랜드별
    daily = list(
        qs.values(
            'shipped_at__date', 'client__company_name', 'brand__name',
        ).annotate(
            order_count=Count('id'),
            total_qty=Sum('items__qty'),
        ).order_by('shipped_at__date')
    )
    daily_results = [
        {
            'date': str(row['shipped_at__date']),
            'client_name': row['client__company_name'],
            'brand_name': row['brand__name'] or '',
            'order_count': row['order_count'],
            'total_qty': row['total_qty'] or 0,
        }
        for row in daily
    ]

    # 웨이브별
    wave = list(
        qs.filter(wave__isnull=False)
        .values('wave__wave_id')
        .annotate(
            order_count=Count('id'),
            shipped_count=Count('id', filter=Q(status='SHIPPED')),
        )
        .order_by('wave__wave_id')
    )
    wave_results = [
        {
            'wave_id': row['wave__wave_id'],
            'order_count': row['order_count'],
            'shipped_count': row['shipped_count'],
        }
        for row in wave
    ]

    return {'daily': daily_results, 'wave': wave_results}


def get_shipment_summary_flat(*, date_from, date_to, client_id=None):
    """출고 실적 (엑셀용 — daily만 flat list)"""
    result = get_shipment_summary(date_from=date_from, date_to=date_to, client_id=client_id)
    return result['daily']


def get_worker_productivity(*, date_from, date_to):
    """작업자 생산성 리포트

    피킹 건수/수량 + 트랜잭션 건수
    """
    # 피킹
    pick_data = {}
    pick_qs = (
        TotalPickListDetail.objects
        .filter(
            picked_at__date__gte=date_from,
            picked_at__date__lte=date_to,
            picked_by__isnull=False,
        )
        .values('picked_by__id', 'picked_by__name')
        .annotate(
            pick_count=Count('id'),
            pick_qty=Sum('picked_qty'),
        )
    )
    for row in pick_qs:
        pick_data[row['picked_by__id']] = {
            'worker_id': row['picked_by__id'],
            'worker_name': row['picked_by__name'],
            'pick_count': row['pick_count'],
            'pick_qty': row['pick_qty'] or 0,
        }

    # 트랜잭션 처리 건수
    txn_qs = (
        InventoryTransaction.objects
        .filter(
            timestamp__date__gte=date_from,
            timestamp__date__lte=date_to,
            performed_by__isnull=False,
        )
        .values('performed_by__id', 'performed_by__name')
        .annotate(transaction_count=Count('id'))
    )
    txn_data = {}
    for row in txn_qs:
        txn_data[row['performed_by__id']] = {
            'worker_id': row['performed_by__id'],
            'worker_name': row['performed_by__name'],
            'transaction_count': row['transaction_count'],
        }

    # 합산
    all_worker_ids = set(pick_data.keys()) | set(txn_data.keys())
    results = []
    for wid in sorted(all_worker_ids):
        p = pick_data.get(wid, {})
        t = txn_data.get(wid, {})
        results.append({
            'worker_id': wid,
            'worker_name': p.get('worker_name') or t.get('worker_name', ''),
            'pick_count': p.get('pick_count', 0),
            'pick_qty': p.get('pick_qty', 0),
            'transaction_count': t.get('transaction_count', 0),
        })

    return results


def get_safety_stock_alerts(*, client_id=None):
    """안전재고 미달 리포트"""
    raw = check_safety_stock_alerts(client_id)
    return [
        {
            'product_id': item['safety_stock'].product_id,
            'sku': item['safety_stock'].product.barcode,
            'product_name': item['safety_stock'].product.name,
            'client_name': item['safety_stock'].client.company_name,
            'min_qty': item['safety_stock'].min_qty,
            'current_qty': item['total_on_hand'],
            'shortage': item['shortage'],
        }
        for item in raw
    ]
