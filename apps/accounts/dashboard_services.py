from django.db.models import Count, Sum
from django.utils import timezone


def get_office_dashboard():
    from apps.inbound.models import InboundOrder
    from apps.inventory.models import check_safety_stock_alerts
    from apps.waves.models import OutboundOrder, Wave

    today = timezone.localdate()

    total_orders_received = OutboundOrder.objects.filter(
        ordered_at__date=today,
    ).count()
    total_orders_shipped = OutboundOrder.objects.filter(
        status='SHIPPED', shipped_at__date=today,
    ).count()
    orders_held = OutboundOrder.objects.filter(status='HELD').count()
    shipment_rate = (
        round(total_orders_shipped / total_orders_received * 100, 1)
        if total_orders_received
        else 0
    )

    waves = list(
        Wave.objects.filter(created_at__date=today).values(
            'wave_id', 'wave_time', 'status', 'total_orders', 'shipped_count',
        )
    )
    for w in waves:
        total = w['total_orders'] or 0
        w['progress'] = (
            round(w['shipped_count'] / total * 100, 1) if total else 0
        )

    safety_stock_alerts = len(check_safety_stock_alerts())
    pending_inbound = InboundOrder.objects.filter(
        status__in=['PLANNED', 'ARRIVED', 'INSPECTING'],
    ).count()

    return {
        'today_summary': {
            'total_orders_received': total_orders_received,
            'total_orders_shipped': total_orders_shipped,
            'orders_held': orders_held,
            'shipment_rate': shipment_rate,
        },
        'waves': waves,
        'safety_stock_alerts': safety_stock_alerts,
        'pending_inbound': pending_inbound,
    }


def get_field_dashboard(user):
    from apps.history.models import InventoryTransaction
    from apps.waves.models import OutboundOrder, TotalPickListDetail, Wave

    today = timezone.localdate()

    current_wave = Wave.objects.filter(
        status__in=['PICKING', 'DISTRIBUTING', 'SHIPPING'],
        created_at__date=today,
    ).first()

    current_wave_data = None
    inspection_pending = 0
    if current_wave:
        pick_total = current_wave.total_orders or 0
        pick_done = current_wave.picked_count or 0
        current_wave_data = {
            'wave_id': current_wave.wave_id,
            'status': current_wave.status,
            'pick_total': pick_total,
            'pick_done': pick_done,
            'progress': (
                round(pick_done / pick_total * 100, 1) if pick_total else 0
            ),
        }
        inspection_pending = OutboundOrder.objects.filter(
            status='PICKING', wave=current_wave,
        ).count()

    my_picks = TotalPickListDetail.objects.filter(
        picked_by=user, picked_at__date=today,
    )
    pick_count = my_picks.count()
    pick_qty = my_picks.aggregate(total=Sum('picked_qty'))['total'] or 0

    transaction_count = InventoryTransaction.objects.filter(
        performed_by=user, timestamp__date=today,
    ).count()

    return {
        'current_wave': current_wave_data,
        'inspection_pending': inspection_pending,
        'my_today': {
            'pick_count': pick_count,
            'pick_qty': pick_qty,
            'transaction_count': transaction_count,
        },
    }


def get_client_dashboard(user):
    from apps.history.models import InventoryTransaction
    from apps.inventory.models import InventoryBalance, check_safety_stock_alerts

    client_ids = list(user.clients.values_list('id', flat=True))
    today = timezone.localdate()

    inventory_summary = list(
        InventoryBalance.objects.filter(client_id__in=client_ids)
        .values('product__brand__name')
        .annotate(
            total_on_hand=Sum('on_hand_qty'),
            total_allocated=Sum('allocated_qty'),
        )
        .order_by('product__brand__name')
    )

    today_inbound = InventoryTransaction.objects.filter(
        client_id__in=client_ids,
        transaction_type='GR',
        timestamp__date=today,
    ).aggregate(count=Count('id'), qty=Sum('qty'))

    today_outbound = InventoryTransaction.objects.filter(
        client_id__in=client_ids,
        transaction_type='GI',
        timestamp__date=today,
    ).aggregate(count=Count('id'), qty=Sum('qty'))

    all_alerts = check_safety_stock_alerts()
    safety_stock_alerts = [
        {
            'product_name': a['safety_stock'].product.name,
            'client_name': a['safety_stock'].client.company_name,
            'min_qty': a['safety_stock'].min_qty,
            'total_on_hand': a['total_on_hand'],
            'shortage': a['shortage'],
        }
        for a in all_alerts
        if a['safety_stock'].client_id in client_ids
    ]

    return {
        'inventory_summary': inventory_summary,
        'today_inbound': {
            'count': today_inbound['count'] or 0,
            'qty': today_inbound['qty'] or 0,
        },
        'today_outbound': {
            'count': today_outbound['count'] or 0,
            'qty': today_outbound['qty'] or 0,
        },
        'safety_stock_alerts': safety_stock_alerts,
    }
