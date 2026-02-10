"""
검수 시스템 뷰
"""
import json
from collections import defaultdict

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.db import transaction
from django.utils import timezone
import openpyxl

from .models import Order, OrderProduct, InspectionLog


def office_page(request):
    """오피스팀 페이지"""
    orders = Order.objects.all()
    total = orders.count()
    waiting = orders.filter(status='대기중').count()
    inspecting = orders.filter(status='검수중').count()
    completed = orders.filter(status='완료').count()
    context = {
        'total': total,
        'waiting': waiting,
        'inspecting': inspecting,
        'completed': completed,
    }
    return render(request, 'inspection/office.html', context)


def field_page(request):
    """필드팀 페이지"""
    return render(request, 'inspection/field.html')


@csrf_exempt
@require_POST
def upload_excel(request):
    """엑셀 업로드 처리"""
    if 'file' not in request.FILES:
        return JsonResponse({'success': False, 'message': '파일이 없습니다.'}, status=400)

    excel_file = request.FILES['file']

    # 확장자 검증
    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'success': False, 'message': '엑셀 파일만 업로드 가능합니다.'}, status=400)

    try:
        wb = openpyxl.load_workbook(excel_file, read_only=True)
        ws = wb.active

        # 헤더 읽기
        headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        headers = [h.strip() if h else '' for h in headers]

        required_columns = ['송장번호', '판매처', '수령인', '핸드폰', '주소', '상품바코드', '상품명', '수량']
        col_map = {}
        for col_name in required_columns:
            if col_name in headers:
                col_map[col_name] = headers.index(col_name)
            else:
                return JsonResponse({
                    'success': False,
                    'message': f'필수 컬럼이 없습니다: {col_name}'
                }, status=400)

        # 데이터 파싱 - 송장번호 기준 그룹화
        orders_data = defaultdict(lambda: {'info': None, 'products': []})
        row_count = 0

        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or not row[col_map['송장번호']]:
                continue

            tracking_number = str(row[col_map['송장번호']]).strip()
            row_count += 1

            if orders_data[tracking_number]['info'] is None:
                orders_data[tracking_number]['info'] = {
                    'seller': str(row[col_map['판매처']] or '').strip(),
                    'receiver_name': str(row[col_map['수령인']] or '').strip(),
                    'receiver_phone': str(row[col_map['핸드폰']] or '').strip(),
                    'receiver_address': str(row[col_map['주소']] or '').strip(),
                }

            barcode = str(row[col_map['상품바코드']] or '').strip()
            product_name = str(row[col_map['상품명']] or '').strip()
            try:
                quantity = int(row[col_map['수량']] or 0)
            except (ValueError, TypeError):
                quantity = 0

            if barcode and product_name:
                orders_data[tracking_number]['products'].append({
                    'barcode': barcode,
                    'product_name': product_name,
                    'quantity': quantity,
                })

        wb.close()

        if not orders_data:
            return JsonResponse({'success': False, 'message': '유효한 데이터가 없습니다.'}, status=400)

        # DB 저장
        total_orders = 0
        total_products = 0
        duplicated = 0

        with transaction.atomic():
            for tracking_number, data in orders_data.items():
                # 중복 송장번호 처리: 기존 데이터 삭제 후 재등록
                existing = Order.objects.filter(tracking_number=tracking_number)
                if existing.exists():
                    existing.delete()
                    duplicated += 1

                order = Order.objects.create(
                    tracking_number=tracking_number,
                    **data['info']
                )
                total_orders += 1

                products = [
                    OrderProduct(
                        order=order,
                        barcode=p['barcode'],
                        product_name=p['product_name'],
                        quantity=p['quantity'],
                    )
                    for p in data['products']
                ]
                OrderProduct.objects.bulk_create(products)
                total_products += len(products)

        message = f'{total_orders}건의 송장이 등록되었습니다.'
        if duplicated:
            message += f' (중복 {duplicated}건 재등록)'

        return JsonResponse({
            'success': True,
            'message': message,
            'total_orders': total_orders,
            'total_products': total_products,
            'duplicated': duplicated,
        })

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'파일 처리 중 오류: {str(e)}'}, status=500)


@require_GET
def get_order(request, tracking_number):
    """송장 조회"""
    worker = request.user.name if request.user.is_authenticated else None

    try:
        order = Order.objects.prefetch_related('products').get(
            tracking_number=tracking_number
        )

        # 기처리 배송 체크
        if order.status == '완료':
            InspectionLog.objects.create(
                tracking_number=tracking_number,
                scan_type='송장',
                alert_code='기처리배송',
                worker=worker,
            )
            return JsonResponse({
                'success': True,
                'alert_code': '기처리배송',
                'order': {
                    'tracking_number': order.tracking_number,
                    'seller': order.seller,
                    'receiver_name': order.receiver_name,
                    'receiver_phone': order.receiver_phone,
                    'receiver_address': order.receiver_address,
                    'status': order.status,
                    'completed_at': order.completed_at.isoformat() if order.completed_at else None,
                },
                'products': [
                    {
                        'id': p.id,
                        'barcode': p.barcode,
                        'product_name': p.product_name,
                        'quantity': p.quantity,
                        'scanned_quantity': p.scanned_quantity,
                    }
                    for p in order.products.all()
                ],
            })

        # 정상 조회 로그
        InspectionLog.objects.create(
            tracking_number=tracking_number,
            scan_type='송장',
            alert_code='정상',
            worker=worker,
        )

        return JsonResponse({
            'success': True,
            'alert_code': '정상',
            'order': {
                'tracking_number': order.tracking_number,
                'seller': order.seller,
                'receiver_name': order.receiver_name,
                'receiver_phone': order.receiver_phone,
                'receiver_address': order.receiver_address,
                'status': order.status,
            },
            'products': [
                {
                    'id': p.id,
                    'barcode': p.barcode,
                    'product_name': p.product_name,
                    'quantity': p.quantity,
                    'scanned_quantity': p.scanned_quantity,
                }
                for p in order.products.all()
            ],
        })

    except Order.DoesNotExist:
        InspectionLog.objects.create(
            tracking_number=tracking_number,
            scan_type='송장',
            alert_code='송장번호미등록',
            worker=worker,
        )
        return JsonResponse({
            'success': False,
            'alert_code': '송장번호미등록',
            'message': '등록되지 않은 송장번호입니다.',
        })


@csrf_exempt
@require_POST
def scan_product(request):
    """상품 스캔 처리"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': '잘못된 요청입니다.'}, status=400)

    tracking_number = data.get('tracking_number', '').strip()
    barcode = data.get('barcode', '').strip()
    worker = request.user.name if request.user.is_authenticated else None

    if not tracking_number or not barcode:
        return JsonResponse({'success': False, 'message': '송장번호와 바코드가 필요합니다.'}, status=400)

    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().get(tracking_number=tracking_number)

            # 해당 주문의 상품 중 바코드 매칭
            products = list(order.products.select_for_update().filter(barcode=barcode))

            if not products:
                # 상품오류
                InspectionLog.objects.create(
                    tracking_number=tracking_number,
                    barcode=barcode,
                    scan_type='상품',
                    alert_code='상품오류',
                    worker=worker,
                )
                return JsonResponse({
                    'success': False,
                    'alert_code': '상품오류',
                    'message': '해당 송장에 없는 상품입니다.',
                })

            # 스캔 가능한 상품 찾기 (scanned_quantity < quantity)
            target_product = None
            for p in products:
                if p.scanned_quantity < p.quantity:
                    target_product = p
                    break

            if target_product is None:
                # 중복스캔
                InspectionLog.objects.create(
                    tracking_number=tracking_number,
                    barcode=barcode,
                    scan_type='상품',
                    alert_code='중복스캔',
                    worker=worker,
                )
                return JsonResponse({
                    'success': False,
                    'alert_code': '중복스캔',
                    'message': '이미 스캔 완료된 상품입니다.',
                })

            # 스캔 수량 증가
            target_product.scanned_quantity += 1
            target_product.save(update_fields=['scanned_quantity'])

            # Order status 업데이트
            if order.status == '대기중':
                order.status = '검수중'
                order.save(update_fields=['status'])

            # 남은 수량 계산 (해당 상품)
            remaining = target_product.quantity - target_product.scanned_quantity

            # 전체 완료 체크
            all_products = list(order.products.all())
            all_completed = all(p.scanned_quantity >= p.quantity for p in all_products)

            if all_completed:
                order.status = '완료'
                order.completed_at = timezone.now()
                order.save(update_fields=['status', 'completed_at'])

                InspectionLog.objects.create(
                    tracking_number=tracking_number,
                    barcode=barcode,
                    scan_type='상품',
                    alert_code='완료',
                    worker=worker,
                )

                return JsonResponse({
                    'success': True,
                    'alert_code': '완료',
                    'all_completed': True,
                    'product': {
                        'id': target_product.id,
                        'barcode': target_product.barcode,
                        'product_name': target_product.product_name,
                        'quantity': target_product.quantity,
                        'scanned_quantity': target_product.scanned_quantity,
                    },
                    'order': {
                        'tracking_number': order.tracking_number,
                        'completed_at': order.completed_at.isoformat(),
                    },
                })

            # 남은 수량에 따른 알림코드
            if remaining > 0:
                alert_code = '숫자'
            else:
                alert_code = '정상'

            InspectionLog.objects.create(
                tracking_number=tracking_number,
                barcode=barcode,
                scan_type='상품',
                alert_code=alert_code,
                worker=worker,
            )

            return JsonResponse({
                'success': True,
                'alert_code': alert_code,
                'remaining': remaining,
                'product': {
                    'id': target_product.id,
                    'barcode': target_product.barcode,
                    'product_name': target_product.product_name,
                    'quantity': target_product.quantity,
                    'scanned_quantity': target_product.scanned_quantity,
                },
                'all_completed': False,
                'products': [
                    {
                        'id': p.id,
                        'barcode': p.barcode,
                        'product_name': p.product_name,
                        'quantity': p.quantity,
                        'scanned_quantity': p.scanned_quantity,
                    }
                    for p in all_products
                ],
            })

    except Order.DoesNotExist:
        return JsonResponse({
            'success': False,
            'alert_code': '송장번호미등록',
            'message': '등록되지 않은 송장번호입니다.',
        })


@csrf_exempt
@require_POST
def complete_inspection(request):
    """검수 완료 처리"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': '잘못된 요청입니다.'}, status=400)

    tracking_number = data.get('tracking_number', '').strip()
    worker = request.user.name if request.user.is_authenticated else None

    if not tracking_number:
        return JsonResponse({'success': False, 'message': '송장번호가 필요합니다.'}, status=400)

    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().get(tracking_number=tracking_number)

            # 모든 상품 스캔 완료 여부 확인
            all_products = order.products.all()
            incomplete = [p for p in all_products if p.scanned_quantity < p.quantity]

            if incomplete:
                return JsonResponse({
                    'success': False,
                    'message': f'아직 스캔하지 않은 상품이 {len(incomplete)}건 있습니다.',
                })

            order.status = '완료'
            order.completed_at = timezone.now()
            order.save(update_fields=['status', 'completed_at'])

            InspectionLog.objects.create(
                tracking_number=tracking_number,
                scan_type='상품',
                alert_code='완료',
                worker=worker,
            )

            return JsonResponse({
                'success': True,
                'message': '검수가 완료되었습니다.',
                'tracking_number': tracking_number,
                'completed_at': order.completed_at.isoformat(),
            })

    except Order.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': '등록되지 않은 송장번호입니다.',
        })


@require_GET
def get_logs(request):
    """로그 조회"""
    logs = InspectionLog.objects.all()

    tracking_number = request.GET.get('tracking_number')
    if tracking_number:
        logs = logs.filter(tracking_number=tracking_number)

    date_from = request.GET.get('date_from')
    if date_from:
        logs = logs.filter(created_at__date__gte=date_from)

    date_to = request.GET.get('date_to')
    if date_to:
        logs = logs.filter(created_at__date__lte=date_to)

    alert_code = request.GET.get('alert_code')
    if alert_code:
        logs = logs.filter(alert_code=alert_code)

    total = logs.count()
    logs = logs[:200]

    return JsonResponse({
        'success': True,
        'logs': [
            {
                'id': log.id,
                'tracking_number': log.tracking_number,
                'barcode': log.barcode,
                'scan_type': log.scan_type,
                'alert_code': log.alert_code,
                'worker': log.worker,
                'created_at': log.created_at.isoformat(),
            }
            for log in logs
        ],
        'total': total,
    })


@require_GET
def get_orders_status(request):
    """송장 현황 조회 (오피스팀용)"""
    orders = Order.objects.all()

    status_filter = request.GET.get('status')
    if status_filter:
        orders = orders.filter(status=status_filter)

    search = request.GET.get('search')
    if search:
        orders = orders.filter(tracking_number__icontains=search)

    total = orders.count()
    orders = orders.prefetch_related('products')[:100]

    return JsonResponse({
        'success': True,
        'orders': [
            {
                'tracking_number': o.tracking_number,
                'seller': o.seller,
                'receiver_name': o.receiver_name,
                'status': o.status,
                'uploaded_at': o.uploaded_at.isoformat(),
                'completed_at': o.completed_at.isoformat() if o.completed_at else None,
                'product_count': o.products.count(),
            }
            for o in orders
        ],
        'total': total,
    })
