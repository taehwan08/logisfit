"""
재고 관리 뷰
"""
import json
import logging
from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import Location, InventorySession, InventoryRecord

logger = logging.getLogger(__name__)


# ============================================================================
# 관리자 권한 체크 데코레이터
# ============================================================================

def admin_required(view_func):
    """관리자 전용 뷰 데코레이터 (v1에서는 관리자만 접근 가능)"""
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_admin or request.user.is_superuser):
            return JsonResponse({'error': '관리자 권한이 필요합니다.'}, status=403)
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    wrapper.__doc__ = view_func.__doc__
    return wrapper


# ============================================================================
# 페이지 뷰
# ============================================================================

@login_required
@admin_required
def session_page(request):
    """재고조사 세션 관리 페이지"""
    active_session = InventorySession.objects.filter(status='active').first()
    return render(request, 'inventory/session.html', {
        'active_session': active_session,
    })


@login_required
@admin_required
def scan_page(request):
    """재고 스캔 입력 페이지"""
    active_session = InventorySession.objects.filter(status='active').first()
    return render(request, 'inventory/scan.html', {
        'active_session': active_session,
    })


@login_required
@admin_required
def status_page(request):
    """재고 현황 조회 페이지"""
    sessions = InventorySession.objects.all()
    active_session = sessions.filter(status='active').first()
    return render(request, 'inventory/status.html', {
        'sessions': sessions,
        'active_session': active_session,
    })


# ============================================================================
# API: 세션 관리
# ============================================================================

@csrf_exempt
@login_required
@admin_required
@require_POST
def create_session(request):
    """새 재고조사 세션을 시작한다."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': '잘못된 요청입니다.'}, status=400)

    name = data.get('name', '').strip()
    if not name:
        return JsonResponse({'error': '세션명을 입력해주세요.'}, status=400)

    # 이미 활성 세션이 있는지 확인
    active = InventorySession.objects.filter(status='active').first()
    if active:
        return JsonResponse({
            'error': f'이미 진행 중인 세션이 있습니다: {active.name}',
        }, status=400)

    session = InventorySession.objects.create(
        name=name,
        started_by=request.user.name if hasattr(request.user, 'name') else str(request.user),
    )

    return JsonResponse({
        'success': True,
        'session': _session_to_dict(session),
    })


@csrf_exempt
@login_required
@admin_required
@require_POST
def end_session(request, session_id):
    """재고조사 세션을 종료한다."""
    try:
        session = InventorySession.objects.get(pk=session_id)
    except InventorySession.DoesNotExist:
        return JsonResponse({'error': '세션을 찾을 수 없습니다.'}, status=404)

    if session.status == 'closed':
        return JsonResponse({'error': '이미 종료된 세션입니다.'}, status=400)

    session.status = 'closed'
    session.ended_at = timezone.now()
    session.save(update_fields=['status', 'ended_at'])

    return JsonResponse({
        'success': True,
        'session': _session_to_dict(session),
    })


@login_required
@admin_required
@require_GET
def get_sessions(request):
    """세션 목록을 조회한다."""
    sessions = InventorySession.objects.annotate(
        record_count=Count('records'),
    ).order_by('-started_at')

    return JsonResponse({
        'sessions': [
            {
                **_session_to_dict(s),
                'record_count': s.record_count,
            }
            for s in sessions
        ],
    })


# ============================================================================
# API: 스캔
# ============================================================================

@csrf_exempt
@login_required
@admin_required
@require_POST
def scan_location(request):
    """로케이션 바코드를 스캔한다. 미등록이면 자동 생성."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': '잘못된 요청입니다.'}, status=400)

    barcode = data.get('barcode', '').strip()
    if not barcode:
        return JsonResponse({'error': '로케이션 바코드를 입력해주세요.'}, status=400)

    # 활성 세션 확인
    active_session = InventorySession.objects.filter(status='active').first()
    if not active_session:
        return JsonResponse({'error': '진행 중인 세션이 없습니다.'}, status=400)

    location, created = Location.objects.get_or_create(
        barcode=barcode,
        defaults={'name': '', 'zone': ''},
    )

    # 현재 세션에서 이 로케이션에 등록된 기록 수
    record_count = InventoryRecord.objects.filter(
        session=active_session,
        location=location,
    ).count()

    return JsonResponse({
        'success': True,
        'created': created,
        'location': {
            'id': location.pk,
            'barcode': location.barcode,
            'name': location.name,
            'zone': location.zone,
        },
        'record_count': record_count,
    })


@csrf_exempt
@login_required
@admin_required
@require_POST
def scan_product(request):
    """상품을 등록한다."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': '잘못된 요청입니다.'}, status=400)

    session_id = data.get('session_id')
    location_id = data.get('location_id')
    barcode = data.get('barcode', '').strip()
    product_name = data.get('product_name', '').strip()
    quantity = data.get('quantity', 1)

    if not session_id or not location_id:
        return JsonResponse({'error': '세션과 로케이션 정보가 필요합니다.'}, status=400)

    if not barcode and not product_name:
        return JsonResponse({'error': '상품바코드 또는 상품명을 입력해주세요.'}, status=400)

    try:
        quantity = int(quantity)
        if quantity < 1:
            quantity = 1
    except (ValueError, TypeError):
        quantity = 1

    # 세션 확인
    try:
        session = InventorySession.objects.get(pk=session_id, status='active')
    except InventorySession.DoesNotExist:
        return JsonResponse({'error': '활성 세션을 찾을 수 없습니다.'}, status=400)

    # 로케이션 확인
    try:
        location = Location.objects.get(pk=location_id)
    except Location.DoesNotExist:
        return JsonResponse({'error': '로케이션을 찾을 수 없습니다.'}, status=400)

    record = InventoryRecord.objects.create(
        session=session,
        location=location,
        barcode=barcode,
        product_name=product_name,
        quantity=quantity,
        worker=request.user.name if hasattr(request.user, 'name') else str(request.user),
    )

    return JsonResponse({
        'success': True,
        'record': _record_to_dict(record),
    })


# ============================================================================
# API: 기록 조회 / 삭제
# ============================================================================

@login_required
@admin_required
@require_GET
def get_records(request):
    """재고 기록을 조회한다.

    Query params:
        session_id: 세션 ID (필수)
        group_by: 'location' 또는 'product' (기본: location)
        search: 검색어 (로케이션 바코드, 상품명, 상품바코드)
    """
    session_id = request.GET.get('session_id')
    if not session_id:
        return JsonResponse({'error': 'session_id가 필요합니다.'}, status=400)

    group_by = request.GET.get('group_by', 'location')
    search = request.GET.get('search', '').strip()

    records = InventoryRecord.objects.filter(
        session_id=session_id,
    ).select_related('location')

    if search:
        records = records.filter(
            models_Q_search(search)
        )

    if group_by == 'product':
        return _get_records_by_product(records)
    else:
        return _get_records_by_location(records)


@csrf_exempt
@login_required
@admin_required
def delete_record(request, record_id):
    """재고 기록을 삭제한다."""
    if request.method != 'DELETE':
        return JsonResponse({'error': 'DELETE 메서드만 허용됩니다.'}, status=405)

    try:
        record = InventoryRecord.objects.get(pk=record_id)
    except InventoryRecord.DoesNotExist:
        return JsonResponse({'error': '기록을 찾을 수 없습니다.'}, status=404)

    record.delete()
    return JsonResponse({'success': True})


@login_required
@admin_required
@require_GET
def get_location_records(request):
    """특정 로케이션의 현재 세션 기록을 조회한다.

    Query params:
        session_id: 세션 ID
        location_id: 로케이션 ID
    """
    session_id = request.GET.get('session_id')
    location_id = request.GET.get('location_id')

    if not session_id or not location_id:
        return JsonResponse({'error': 'session_id와 location_id가 필요합니다.'}, status=400)

    records = InventoryRecord.objects.filter(
        session_id=session_id,
        location_id=location_id,
    ).order_by('-created_at')

    return JsonResponse({
        'records': [_record_to_dict(r) for r in records],
    })


# ============================================================================
# 헬퍼 함수
# ============================================================================

def models_Q_search(search):
    """검색어로 Q 필터를 생성한다."""
    from django.db.models import Q
    return (
        Q(barcode__icontains=search) |
        Q(product_name__icontains=search) |
        Q(location__barcode__icontains=search) |
        Q(location__name__icontains=search)
    )


def _get_records_by_location(records):
    """로케이션별로 그룹핑하여 반환한다."""
    grouped = defaultdict(lambda: {
        'location': None,
        'products': [],
        'total_quantity': 0,
    })

    for r in records:
        key = r.location_id
        if grouped[key]['location'] is None:
            grouped[key]['location'] = {
                'id': r.location.pk,
                'barcode': r.location.barcode,
                'name': r.location.name,
                'zone': r.location.zone,
            }
        grouped[key]['products'].append(_record_to_dict(r))
        grouped[key]['total_quantity'] += r.quantity

    # 로케이션 바코드 순 정렬
    result = sorted(
        grouped.values(),
        key=lambda x: x['location']['barcode'] if x['location'] else '',
    )

    return JsonResponse({'groups': result})


def _get_records_by_product(records):
    """상품별로 그룹핑하여 반환한다."""
    grouped = defaultdict(lambda: {
        'barcode': '',
        'product_name': '',
        'locations': [],
        'total_quantity': 0,
    })

    for r in records:
        key = r.barcode or r.product_name
        if not grouped[key]['barcode']:
            grouped[key]['barcode'] = r.barcode
            grouped[key]['product_name'] = r.product_name
        grouped[key]['locations'].append({
            'location_barcode': r.location.barcode,
            'location_name': r.location.name,
            'quantity': r.quantity,
            'record_id': r.pk,
            'worker': r.worker,
            'created_at': timezone.localtime(r.created_at).strftime('%Y-%m-%d %H:%M'),
        })
        grouped[key]['total_quantity'] += r.quantity

    # 상품 바코드 순 정렬
    result = sorted(
        grouped.values(),
        key=lambda x: x['barcode'] or x['product_name'],
    )

    return JsonResponse({'groups': result})


def _session_to_dict(session):
    """InventorySession 인스턴스를 dict로 변환한다."""
    return {
        'id': session.pk,
        'name': session.name,
        'status': session.status,
        'status_display': session.get_status_display(),
        'started_at': timezone.localtime(session.started_at).strftime('%Y-%m-%d %H:%M'),
        'ended_at': (
            timezone.localtime(session.ended_at).strftime('%Y-%m-%d %H:%M')
            if session.ended_at else None
        ),
        'started_by': session.started_by,
    }


def _record_to_dict(record):
    """InventoryRecord 인스턴스를 dict로 변환한다."""
    return {
        'id': record.pk,
        'barcode': record.barcode,
        'product_name': record.product_name,
        'quantity': record.quantity,
        'worker': record.worker,
        'location_barcode': record.location.barcode if hasattr(record, 'location') and record.location else '',
        'location_name': record.location.name if hasattr(record, 'location') and record.location else '',
        'created_at': timezone.localtime(record.created_at).strftime('%Y-%m-%d %H:%M'),
    }
