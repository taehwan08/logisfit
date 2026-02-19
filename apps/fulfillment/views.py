"""
출고 관리 뷰

B2B 출고 주문 목록, 등록, 수정, 삭제, 상태변경, 엑셀 다운로드/업로드 기능을 제공합니다.
"""
import json
from datetime import datetime
from functools import wraps

from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone

from .models import FulfillmentOrder, FulfillmentComment
from apps.clients.models import Client


# ============================================================================
# 권한 데코레이터
# ============================================================================

def fulfillment_access_required(view_func):
    """출고 관리 접근 가능 데코레이터 (관리자/작업자/고객사)"""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not (user.is_admin or user.is_worker or user.is_client or user.is_superuser):
            return JsonResponse({'error': '접근 권한이 없습니다.'}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper


def admin_required(view_func):
    """관리자 전용 데코레이터"""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not (user.is_admin or user.is_superuser):
            return JsonResponse({'error': '관리자 권한이 필요합니다.'}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper


def admin_or_client_required(view_func):
    """관리자 또는 고객사 데코레이터"""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not (user.is_admin or user.is_client or user.is_superuser):
            return JsonResponse({'error': '접근 권한이 없습니다.'}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper


def _get_client_filter(user):
    """고객사 사용자의 경우 자기 거래처만 필터링"""
    if user.is_client:
        client_ids = user.clients.values_list('id', flat=True)
        return Q(client_id__in=client_ids)
    return Q()  # 관리자/작업자는 전체


# ============================================================================
# 페이지 뷰
# ============================================================================

@fulfillment_access_required
def order_list_page(request):
    """출고 주문 목록 페이지"""
    user = request.user

    # 고객사 목록 (필터용)
    if user.is_client:
        clients = user.clients.filter(is_active=True)
    else:
        clients = Client.objects.filter(is_active=True).order_by('company_name')

    context = {
        'clients': clients,
        'platforms': FulfillmentOrder.Platform.choices,
        'statuses': FulfillmentOrder.Status.choices,
        'is_admin': user.is_admin or user.is_superuser,
        'is_client': user.is_client,
        'is_worker': user.is_worker,
    }
    return render(request, 'fulfillment/order_list.html', context)


# ============================================================================
# API 뷰
# ============================================================================

@fulfillment_access_required
@require_http_methods(["GET"])
def get_orders(request):
    """주문 목록 JSON API (필터/검색/페이징)"""
    user = request.user
    qs = FulfillmentOrder.objects.select_related('client', 'created_by')

    # 고객사 필터 (권한)
    qs = qs.filter(_get_client_filter(user))

    # 필터 파라미터
    client_id = request.GET.get('client_id')
    platform = request.GET.get('platform')
    status = request.GET.get('status')
    search = request.GET.get('search', '').strip()
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    page = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 20)

    if client_id:
        qs = qs.filter(client_id=client_id)
    if platform:
        qs = qs.filter(platform=platform)
    if status:
        qs = qs.filter(status=status)
    if search:
        qs = qs.filter(
            Q(order_number__icontains=search) |
            Q(product_name__icontains=search) |
            Q(barcode__icontains=search)
        )
    if date_from:
        try:
            qs = qs.filter(order_date__gte=datetime.strptime(date_from, '%Y-%m-%d').date())
        except ValueError:
            pass
    if date_to:
        try:
            qs = qs.filter(order_date__lte=datetime.strptime(date_to, '%Y-%m-%d').date())
        except ValueError:
            pass

    # 정렬
    qs = qs.order_by('-order_date', '-created_at')

    # 페이징
    try:
        page_size = min(int(page_size), 100)
    except (ValueError, TypeError):
        page_size = 20

    paginator = Paginator(qs, page_size)
    try:
        page_obj = paginator.page(page)
    except Exception:
        page_obj = paginator.page(1)

    orders = []
    for order in page_obj:
        orders.append({
            'id': order.id,
            'client_id': order.client_id,
            'client_name': order.client.company_name,
            'platform': order.platform,
            'platform_display': order.get_platform_display(),
            'order_number': order.order_number,
            'order_date': order.order_date.strftime('%Y-%m-%d') if order.order_date else '',
            'status': order.status,
            'status_display': order.get_status_display(),
            'product_name': order.product_name,
            'barcode': order.barcode,
            'order_quantity': order.order_quantity,
            'box_quantity': order.box_quantity,
            'manager': order.manager,
            'expiry_date': order.expiry_date,
            'receiving_date': order.receiving_date.strftime('%Y-%m-%d') if order.receiving_date else '',
            'address': order.address,
            'memo': order.memo,
            'platform_data': order.platform_data,
            'confirmed_at': order.confirmed_at.strftime('%Y-%m-%d %H:%M') if order.confirmed_at else '',
            'shipped_at': order.shipped_at.strftime('%Y-%m-%d %H:%M') if order.shipped_at else '',
            'synced_at': order.synced_at.strftime('%Y-%m-%d %H:%M') if order.synced_at else '',
            'created_by': order.created_by.name if order.created_by else '',
            'created_at': order.created_at.strftime('%Y-%m-%d %H:%M'),
        })

    return JsonResponse({
        'orders': orders,
        'total': paginator.count,
        'page': page_obj.number,
        'total_pages': paginator.num_pages,
        'has_next': page_obj.has_next(),
        'has_previous': page_obj.has_previous(),
    })


@admin_or_client_required
@require_http_methods(["POST"])
def create_order(request):
    """주문 등록"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': '잘못된 요청입니다.'}, status=400)

    user = request.user
    client_id = data.get('client_id')

    # 고객사 검증
    if not client_id:
        return JsonResponse({'error': '거래처를 선택해주세요.'}, status=400)

    try:
        client = Client.objects.get(id=client_id, is_active=True)
    except Client.DoesNotExist:
        return JsonResponse({'error': '유효하지 않은 거래처입니다.'}, status=400)

    # 고객사 사용자는 자기 거래처만 등록 가능
    if user.is_client and not user.clients.filter(id=client_id).exists():
        return JsonResponse({'error': '해당 거래처에 대한 권한이 없습니다.'}, status=403)

    # 필수 필드 검증
    platform = data.get('platform', '')
    order_number = data.get('order_number', '').strip()
    product_name = data.get('product_name', '').strip()

    if not platform:
        return JsonResponse({'error': '플랫폼을 선택해주세요.'}, status=400)
    if not order_number:
        return JsonResponse({'error': '발주번호를 입력해주세요.'}, status=400)
    if not product_name:
        return JsonResponse({'error': '상품명을 입력해주세요.'}, status=400)

    # 발주일 파싱
    order_date_str = data.get('order_date', '')
    order_date = timezone.now().date()
    if order_date_str:
        try:
            order_date = datetime.strptime(order_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    # 입고일 파싱
    receiving_date = None
    receiving_date_str = data.get('receiving_date', '')
    if receiving_date_str:
        try:
            receiving_date = datetime.strptime(receiving_date_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    order = FulfillmentOrder.objects.create(
        client=client,
        platform=platform,
        order_number=order_number,
        order_date=order_date,
        product_name=product_name,
        barcode=data.get('barcode', '').strip(),
        order_quantity=int(data.get('order_quantity', 0) or 0),
        manager=data.get('manager', '').strip(),
        expiry_date=data.get('expiry_date', '').strip(),
        receiving_date=receiving_date,
        box_quantity=int(data.get('box_quantity', 0) or 0),
        address=data.get('address', '').strip(),
        memo=data.get('memo', '').strip(),
        platform_data=data.get('platform_data', {}),
        created_by=user,
    )

    return JsonResponse({
        'success': True,
        'message': '주문이 등록되었습니다.',
        'order_id': order.id,
    })


@admin_required
@require_http_methods(["POST"])
def update_order(request, order_id):
    """주문 수정 (관리자 전용)"""
    try:
        order = FulfillmentOrder.objects.get(id=order_id)
    except FulfillmentOrder.DoesNotExist:
        return JsonResponse({'error': '주문을 찾을 수 없습니다.'}, status=404)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': '잘못된 요청입니다.'}, status=400)

    # 수정 가능 필드
    if 'client_id' in data:
        try:
            client = Client.objects.get(id=data['client_id'], is_active=True)
            order.client = client
        except Client.DoesNotExist:
            return JsonResponse({'error': '유효하지 않은 거래처입니다.'}, status=400)

    if 'platform' in data:
        order.platform = data['platform']
    if 'order_number' in data:
        order.order_number = data['order_number'].strip()
    if 'order_date' in data and data['order_date']:
        try:
            order.order_date = datetime.strptime(data['order_date'], '%Y-%m-%d').date()
        except ValueError:
            pass
    if 'product_name' in data:
        order.product_name = data['product_name'].strip()
    if 'barcode' in data:
        order.barcode = data['barcode'].strip()
    if 'order_quantity' in data:
        order.order_quantity = int(data['order_quantity'] or 0)
    if 'box_quantity' in data:
        order.box_quantity = int(data['box_quantity'] or 0)
    if 'manager' in data:
        order.manager = data['manager'].strip()
    if 'expiry_date' in data:
        order.expiry_date = data['expiry_date'].strip()
    if 'receiving_date' in data:
        if data['receiving_date']:
            try:
                order.receiving_date = datetime.strptime(data['receiving_date'], '%Y-%m-%d').date()
            except ValueError:
                pass
        else:
            order.receiving_date = None
    if 'address' in data:
        order.address = data['address'].strip()
    if 'memo' in data:
        order.memo = data['memo'].strip()
    if 'platform_data' in data:
        order.platform_data = data['platform_data']

    order.save()

    return JsonResponse({
        'success': True,
        'message': '주문이 수정되었습니다.',
    })


@admin_required
@require_http_methods(["POST"])
def delete_order(request, order_id):
    """주문 삭제 (관리자 전용)"""
    try:
        order = FulfillmentOrder.objects.get(id=order_id)
    except FulfillmentOrder.DoesNotExist:
        return JsonResponse({'error': '주문을 찾을 수 없습니다.'}, status=404)

    order.delete()
    return JsonResponse({
        'success': True,
        'message': '주문이 삭제되었습니다.',
    })


@admin_required
@require_http_methods(["POST"])
def update_status(request, order_id):
    """상태 변경 (관리자 전용) - 확인/출고/전산반영"""
    try:
        order = FulfillmentOrder.objects.get(id=order_id)
    except FulfillmentOrder.DoesNotExist:
        return JsonResponse({'error': '주문을 찾을 수 없습니다.'}, status=404)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': '잘못된 요청입니다.'}, status=400)

    action = data.get('action', '')
    user = request.user

    status_actions = {
        'confirm': {
            'method': order.confirm,
            'message': '확인완료 처리되었습니다.',
            'system_msg': '상태가 [확인완료]로 변경되었습니다.',
            'time_field': 'confirmed_at',
        },
        'ship': {
            'method': order.ship,
            'message': '출고완료 처리되었습니다.',
            'system_msg': '상태가 [출고완료]로 변경되었습니다.',
            'time_field': 'shipped_at',
        },
        'sync': {
            'method': order.sync,
            'message': '전산반영 처리되었습니다.',
            'system_msg': '상태가 [전산반영]으로 변경되었습니다.',
            'time_field': 'synced_at',
        },
    }

    if action not in status_actions:
        return JsonResponse({'error': '잘못된 액션입니다.'}, status=400)

    cfg = status_actions[action]
    if cfg['method'](user):
        # 시스템 댓글 자동 추가
        FulfillmentComment.objects.create(
            order=order,
            author=user,
            content=f"{cfg['system_msg']} ({user.name})",
            is_system=True,
        )
        time_val = getattr(order, cfg['time_field'])
        return JsonResponse({
            'success': True,
            'message': cfg['message'],
            'status': order.status,
            'status_display': order.get_status_display(),
            cfg['time_field']: time_val.strftime('%Y-%m-%d %H:%M') if time_val else '',
        })
    else:
        error_msgs = {
            'confirm': '확인 처리할 수 없는 상태입니다.',
            'ship': '출고 처리할 수 없는 상태입니다.',
            'sync': '전산반영 처리할 수 없는 상태입니다.',
        }
        return JsonResponse({'error': error_msgs[action]}, status=400)


@fulfillment_access_required
@require_http_methods(["GET"])
def export_excel(request):
    """엑셀 다운로드 (현재 필터 조건 적용)"""
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    except ImportError:
        return JsonResponse({'error': 'openpyxl 패키지가 필요합니다.'}, status=500)

    user = request.user
    qs = FulfillmentOrder.objects.select_related('client')

    # 고객사 필터 (권한)
    qs = qs.filter(_get_client_filter(user))

    # 필터 파라미터 (목록 API와 동일)
    client_id = request.GET.get('client_id')
    platform = request.GET.get('platform')
    status = request.GET.get('status')
    search = request.GET.get('search', '').strip()
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    if client_id:
        qs = qs.filter(client_id=client_id)
    if platform:
        qs = qs.filter(platform=platform)
    if status:
        qs = qs.filter(status=status)
    if search:
        qs = qs.filter(
            Q(order_number__icontains=search) |
            Q(product_name__icontains=search) |
            Q(barcode__icontains=search)
        )
    if date_from:
        try:
            qs = qs.filter(order_date__gte=datetime.strptime(date_from, '%Y-%m-%d').date())
        except ValueError:
            pass
    if date_to:
        try:
            qs = qs.filter(order_date__lte=datetime.strptime(date_to, '%Y-%m-%d').date())
        except ValueError:
            pass

    qs = qs.order_by('-order_date', '-created_at')

    # 엑셀 생성
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = '출고 주문 목록'

    # 헤더 스타일
    header_font = Font(bold=True, color='FFFFFF', size=11)
    header_fill = PatternFill(start_color='2C3E50', end_color='2C3E50', fill_type='solid')
    header_alignment = Alignment(horizontal='center', vertical='center')
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin'),
    )

    # 헤더
    headers = [
        '거래처', '플랫폼', '발주번호', '발주일', '상품명',
        '바코드', '발주수량', '박스수량', '상태',
        '소비기한', '입고일', '담당자', '주소지', '비고',
    ]
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = thin_border

    # 데이터
    for row_idx, order in enumerate(qs, 2):
        row_data = [
            order.client.company_name,
            order.get_platform_display(),
            order.order_number,
            order.order_date.strftime('%Y-%m-%d') if order.order_date else '',
            order.product_name,
            order.barcode,
            order.order_quantity,
            order.box_quantity,
            order.get_status_display(),
            order.expiry_date,
            order.receiving_date.strftime('%Y-%m-%d') if order.receiving_date else '',
            order.manager,
            order.address,
            order.memo,
        ]
        for col, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col, value=value)
            cell.border = thin_border
            cell.alignment = Alignment(vertical='center')

    # 컬럼 너비 조정
    col_widths = [15, 12, 15, 12, 30, 15, 10, 10, 10, 12, 12, 10, 30, 20]
    for i, width in enumerate(col_widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = width

    # 응답
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    now_str = timezone.now().strftime('%Y%m%d_%H%M')
    response['Content-Disposition'] = f'attachment; filename="fulfillment_orders_{now_str}.xlsx"'
    wb.save(response)
    return response


# 플랫폼별 추가 컬럼 정의
PLATFORM_EXTRA_COLUMNS = {
    'coupang': ['배송유형', '벤더코드'],
    'kurly': ['배송예정일', '온도대'],
    'oliveyoung': ['매장코드', '진열예정일'],
    'smartstore': ['판매채널'],
    'offline': ['매장명', '배송방법'],
    'export': ['수출국', '인코텀즈'],
    'other': [],
}

# 플랫폼별 예시 데이터
PLATFORM_EXAMPLE_DATA = {
    'coupang': {
        'base': ['(주)예시거래처', '쿠팡', 'CPG-2025-001', '2025-03-01', '상품명 예시',
                 '8801234567890', 100, 10, '', '2026-12-31', '2025-03-05', '홍길동', '서울시 강남구', '비고 예시'],
        'extra': ['로켓배송', 'VD12345'],
    },
    'kurly': {
        'base': ['(주)예시거래처', '컬리', 'KRL-2025-001', '2025-03-01', '상품명 예시',
                 '8801234567890', 50, 5, '', '2026-06-30', '2025-03-03', '김철수', '서울시 송파구', ''],
        'extra': ['2025-03-05', '냉장'],
    },
    'oliveyoung': {
        'base': ['(주)예시거래처', '올리브영', 'OY-2025-001', '2025-03-01', '상품명 예시',
                 '8801234567890', 200, 20, '', '2026-12-31', '2025-03-10', '이영희', '', ''],
        'extra': ['OY-STORE-001', '2025-03-15'],
    },
    'smartstore': {
        'base': ['(주)예시거래처', '스마트스토어', 'SS-2025-001', '2025-03-01', '상품명 예시',
                 '8801234567890', 30, 3, '', '2026-12-31', '', '박민수', '경기도 성남시', ''],
        'extra': ['네이버'],
    },
    'offline': {
        'base': ['(주)예시거래처', '오프라인마트', 'OFF-2025-001', '2025-03-01', '상품명 예시',
                 '8801234567890', 500, 50, '', '2026-12-31', '2025-03-07', '최수진', '서울시 마포구', ''],
        'extra': ['이마트 홍대점', '직배'],
    },
    'export': {
        'base': ['(주)예시거래처', '해외수출', 'EXP-2025-001', '2025-03-01', '상품명 예시',
                 '8801234567890', 1000, 100, '', '2026-12-31', '2025-04-01', '정대한', '', ''],
        'extra': ['일본', 'FOB'],
    },
    'other': {
        'base': ['(주)예시거래처', '기타', 'ETC-2025-001', '2025-03-01', '상품명 예시',
                 '8801234567890', 100, 10, '', '2026-12-31', '', '담당자명', '', ''],
        'extra': [],
    },
}


@fulfillment_access_required
@require_http_methods(["GET"])
def download_template(request):
    """플랫폼별 엑셀 업로드 양식 다운로드"""
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    except ImportError:
        return JsonResponse({'error': 'openpyxl 패키지가 필요합니다.'}, status=500)

    platform = request.GET.get('platform', 'other')
    if platform not in PLATFORM_EXTRA_COLUMNS:
        platform = 'other'

    # 플랫폼 표시명
    platform_labels = dict(FulfillmentOrder.Platform.choices)
    platform_label = platform_labels.get(platform, '기타')

    # 공통 헤더
    base_headers = [
        '거래처', '플랫폼', '발주번호', '발주일', '상품명',
        '바코드', '발주수량', '박스수량', '상태',
        '소비기한', '입고일', '담당자', '주소지', '비고',
    ]
    extra_headers = PLATFORM_EXTRA_COLUMNS.get(platform, [])
    all_headers = base_headers + extra_headers

    # 엑셀 생성
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f'{platform_label} 양식'

    # 헤더 스타일
    header_font = Font(bold=True, color='FFFFFF', size=11)
    header_fill = PatternFill(start_color='2C3E50', end_color='2C3E50', fill_type='solid')
    extra_fill = PatternFill(start_color='2980B9', end_color='2980B9', fill_type='solid')
    header_alignment = Alignment(horizontal='center', vertical='center')
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin'),
    )

    # 헤더 행
    for col, header in enumerate(all_headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = extra_fill if col > len(base_headers) else header_fill
        cell.alignment = header_alignment
        cell.border = thin_border

    # 예시 데이터 행
    example = PLATFORM_EXAMPLE_DATA.get(platform, PLATFORM_EXAMPLE_DATA['other'])
    example_data = example['base'] + example['extra']
    example_font = Font(color='999999', italic=True, size=10)
    for col, value in enumerate(example_data, 1):
        cell = ws.cell(row=2, column=col, value=value)
        cell.font = example_font
        cell.border = thin_border
        cell.alignment = Alignment(vertical='center')

    # 컬럼 너비
    base_widths = [15, 12, 15, 12, 30, 15, 10, 10, 10, 12, 12, 10, 30, 20]
    extra_widths = [15] * len(extra_headers)
    all_widths = base_widths + extra_widths
    for i, width in enumerate(all_widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = width

    # 응답
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    now_str = timezone.now().strftime('%Y%m%d')
    response['Content-Disposition'] = f'attachment; filename="fulfillment_template_{platform}_{now_str}.xlsx"'
    wb.save(response)
    return response


@admin_required
@require_http_methods(["POST"])
def upload_orders_excel(request):
    """엑셀 일괄 업로드 (관리자 전용)"""
    try:
        import openpyxl
    except ImportError:
        return JsonResponse({'error': 'openpyxl 패키지가 필요합니다.'}, status=500)

    file = request.FILES.get('file')
    if not file:
        return JsonResponse({'error': '파일을 선택해주세요.'}, status=400)

    if not file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Excel 파일(.xlsx)만 업로드 가능합니다.'}, status=400)

    try:
        wb = openpyxl.load_workbook(file)
        ws = wb.active
    except Exception as e:
        return JsonResponse({'error': f'파일을 읽을 수 없습니다: {str(e)}'}, status=400)

    # 플랫폼 이름→코드 매핑
    platform_map = {v: k for k, v in FulfillmentOrder.Platform.choices}

    user = request.user
    created_count = 0
    errors = []

    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
        if not row or not row[0]:
            continue

        try:
            # 거래처 매칭
            client_name = str(row[0]).strip()
            try:
                client = Client.objects.get(company_name=client_name, is_active=True)
            except Client.DoesNotExist:
                errors.append(f'{row_idx}행: 거래처 "{client_name}"을 찾을 수 없습니다.')
                continue

            # 플랫폼 매칭
            platform_name = str(row[1]).strip() if row[1] else ''
            platform_code = platform_map.get(platform_name, '')
            if not platform_code:
                # 코드값으로도 시도
                if platform_name.lower() in dict(FulfillmentOrder.Platform.choices):
                    platform_code = platform_name.lower()
                else:
                    errors.append(f'{row_idx}행: 플랫폼 "{platform_name}"을 찾을 수 없습니다.')
                    continue

            # 발주번호
            order_number = str(row[2]).strip() if row[2] else ''
            if not order_number:
                errors.append(f'{row_idx}행: 발주번호가 비어있습니다.')
                continue

            # 발주일
            order_date = timezone.now().date()
            if row[3]:
                if isinstance(row[3], datetime):
                    order_date = row[3].date()
                else:
                    try:
                        order_date = datetime.strptime(str(row[3]).strip(), '%Y-%m-%d').date()
                    except ValueError:
                        pass

            # 상품명
            product_name = str(row[4]).strip() if len(row) > 4 and row[4] else ''
            if not product_name:
                errors.append(f'{row_idx}행: 상품명이 비어있습니다.')
                continue

            # 나머지 필드
            barcode = str(row[5]).strip() if len(row) > 5 and row[5] else ''
            order_quantity = int(row[6] or 0) if len(row) > 6 and row[6] else 0
            box_quantity = int(row[7] or 0) if len(row) > 7 and row[7] else 0

            # 입고일
            receiving_date = None
            if len(row) > 10 and row[10]:
                if isinstance(row[10], datetime):
                    receiving_date = row[10].date()
                else:
                    try:
                        receiving_date = datetime.strptime(str(row[10]).strip(), '%Y-%m-%d').date()
                    except ValueError:
                        pass

            FulfillmentOrder.objects.create(
                client=client,
                platform=platform_code,
                order_number=order_number,
                order_date=order_date,
                product_name=product_name,
                barcode=barcode,
                order_quantity=order_quantity,
                box_quantity=box_quantity,
                expiry_date=str(row[9]).strip() if len(row) > 9 and row[9] else '',
                receiving_date=receiving_date,
                manager=str(row[11]).strip() if len(row) > 11 and row[11] else '',
                address=str(row[12]).strip() if len(row) > 12 and row[12] else '',
                memo=str(row[13]).strip() if len(row) > 13 and row[13] else '',
                created_by=user,
            )
            created_count += 1

        except Exception as e:
            errors.append(f'{row_idx}행: {str(e)}')

    result = {
        'success': True,
        'message': f'{created_count}건이 등록되었습니다.',
        'created_count': created_count,
    }
    if errors:
        result['errors'] = errors[:20]  # 최대 20개까지만
        result['error_count'] = len(errors)

    return JsonResponse(result)


# ============================================================================
# 댓글 API
# ============================================================================

def _check_order_access(user, order):
    """주문에 대한 접근 권한 확인"""
    if user.is_admin or user.is_superuser or user.is_worker:
        return True
    if user.is_client:
        return user.clients.filter(id=order.client_id).exists()
    return False


@fulfillment_access_required
@require_http_methods(["GET"])
def get_comments(request, order_id):
    """댓글 목록 조회"""
    try:
        order = FulfillmentOrder.objects.get(id=order_id)
    except FulfillmentOrder.DoesNotExist:
        return JsonResponse({'error': '주문을 찾을 수 없습니다.'}, status=404)

    # 권한 확인
    if not _check_order_access(request.user, order):
        return JsonResponse({'error': '접근 권한이 없습니다.'}, status=403)

    comments = order.comments.select_related('author').all()
    comment_list = []
    for c in comments:
        comment_list.append({
            'id': c.id,
            'author_name': c.author.name if c.author else '시스템',
            'author_role': c.author.get_role_display() if c.author else '',
            'author_id': c.author.id if c.author else None,
            'content': c.content,
            'is_system': c.is_system,
            'created_at': c.created_at.strftime('%Y-%m-%d %H:%M'),
            'is_mine': c.author_id == request.user.id if c.author else False,
        })

    return JsonResponse({'comments': comment_list})


@fulfillment_access_required
@require_http_methods(["POST"])
def add_comment(request, order_id):
    """댓글 등록"""
    try:
        order = FulfillmentOrder.objects.get(id=order_id)
    except FulfillmentOrder.DoesNotExist:
        return JsonResponse({'error': '주문을 찾을 수 없습니다.'}, status=404)

    # 권한 확인
    if not _check_order_access(request.user, order):
        return JsonResponse({'error': '접근 권한이 없습니다.'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': '잘못된 요청입니다.'}, status=400)

    content = data.get('content', '').strip()
    if not content:
        return JsonResponse({'error': '댓글 내용을 입력해주세요.'}, status=400)

    comment = FulfillmentComment.objects.create(
        order=order,
        author=request.user,
        content=content,
    )

    return JsonResponse({
        'success': True,
        'message': '댓글이 등록되었습니다.',
        'comment': {
            'id': comment.id,
            'author_name': comment.author.name,
            'author_role': comment.author.get_role_display(),
            'author_id': comment.author.id,
            'content': comment.content,
            'is_system': False,
            'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M'),
            'is_mine': True,
        },
    })


@fulfillment_access_required
@require_http_methods(["POST"])
def delete_comment(request, order_id, comment_id):
    """댓글 삭제 (본인 또는 관리자)"""
    try:
        comment = FulfillmentComment.objects.get(id=comment_id, order_id=order_id)
    except FulfillmentComment.DoesNotExist:
        return JsonResponse({'error': '댓글을 찾을 수 없습니다.'}, status=404)

    user = request.user
    # 본인 댓글이거나 관리자만 삭제 가능
    if comment.author_id != user.id and not (user.is_admin or user.is_superuser):
        return JsonResponse({'error': '삭제 권한이 없습니다.'}, status=403)

    comment.delete()
    return JsonResponse({
        'success': True,
        'message': '댓글이 삭제되었습니다.',
    })
