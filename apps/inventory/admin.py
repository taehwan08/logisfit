from django import forms
from django.contrib import admin, messages
from django.shortcuts import render, redirect
from django.urls import path
from django.utils.html import format_html

from .models import Product, Location, InventorySession, InventoryRecord, InboundRecord, InboundImage


# ============================================================================
# 로케이션 다중 생성 폼
# ============================================================================

class BulkLocationForm(forms.Form):
    """바코드 형식: {센터}-{동}-{라인}-{열}-{층}  예) 1C-1D-A-01-02"""

    center = forms.CharField(
        label='센터', max_length=10, initial='1C',
        help_text='예: 1C, 2C, 3C',
    )
    building = forms.CharField(
        label='동', max_length=10, initial='1D',
        help_text='예: 1D, 2D, 3D',
    )
    lines = forms.CharField(
        label='라인', initial='A',
        help_text='쉼표 구분: A,B,C  또는 범위: A-D (A~D 자동 생성)',
    )
    col_start = forms.IntegerField(label='열 시작', initial=1, min_value=1)
    col_end = forms.IntegerField(label='열 끝', initial=5, min_value=1,
                                  help_text='예: 1~5 → 01열~05열')
    floor_start = forms.IntegerField(label='층 시작', initial=1, min_value=1)
    floor_end = forms.IntegerField(label='층 끝', initial=3, min_value=1,
                                    help_text='예: 1~3 → 01층~03층')
    zone = forms.CharField(label='구역', max_length=50, required=False,
                           help_text='선택사항')

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('col_start') and cleaned.get('col_end'):
            if cleaned['col_start'] > cleaned['col_end']:
                raise forms.ValidationError('열 시작이 열 끝보다 클 수 없습니다.')
        if cleaned.get('floor_start') and cleaned.get('floor_end'):
            if cleaned['floor_start'] > cleaned['floor_end']:
                raise forms.ValidationError('층 시작이 층 끝보다 클 수 없습니다.')
        return cleaned

    def parse_lines(self):
        raw = self.cleaned_data['lines'].strip().upper()
        # A-D 범위 형식
        if '-' in raw and ',' not in raw and len(raw) == 3:
            s, e = raw[0], raw[2]
            if s.isalpha() and e.isalpha():
                return [chr(c) for c in range(ord(s), ord(e) + 1)]
        return [x.strip() for x in raw.split(',') if x.strip()]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('barcode', 'name', 'display_name', 'option_code', 'created_at', 'updated_at')
    search_fields = ('barcode', 'name', 'display_name', 'option_code')
    ordering = ('name',)


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('barcode', 'name', 'zone', 'created_at')
    search_fields = ('barcode', 'name')
    list_filter = ('zone',)

    # ── 커스텀 URL 추가 ──
    def get_urls(self):
        custom = [
            path('bulk-create/',
                 self.admin_site.admin_view(self.bulk_create_view),
                 name='inventory_location_bulk_create'),
        ]
        return custom + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['has_bulk_create'] = True
        return super().changelist_view(request, extra_context=extra_context)

    def bulk_create_view(self, request):
        """로케이션 다중 생성 뷰"""
        if request.method == 'POST':
            form = BulkLocationForm(request.POST)
            if form.is_valid():
                center = form.cleaned_data['center'].upper()
                building = form.cleaned_data['building'].upper()
                line_list = form.parse_lines()
                col_s = form.cleaned_data['col_start']
                col_e = form.cleaned_data['col_end']
                floor_s = form.cleaned_data['floor_start']
                floor_e = form.cleaned_data['floor_end']
                zone = form.cleaned_data['zone']

                created = skipped = 0
                for line in line_list:
                    for col in range(col_s, col_e + 1):
                        for floor in range(floor_s, floor_e + 1):
                            barcode = f'{center}-{building}-{line}-{col:02d}-{floor:02d}'
                            _, is_new = Location.objects.get_or_create(
                                barcode=barcode,
                                defaults={'zone': zone},
                            )
                            if is_new:
                                created += 1
                            else:
                                skipped += 1

                msg = f'{created}개 로케이션 생성 완료.'
                if skipped:
                    msg += f' ({skipped}개는 이미 존재하여 건너뜀)'
                messages.success(request, msg)
                return redirect('..')
        else:
            form = BulkLocationForm()

        context = {
            **self.admin_site.each_context(request),
            'form': form,
            'opts': self.model._meta,
            'title': '로케이션 다중 생성',
        }
        return render(request, 'admin/inventory/location/bulk_create.html', context)


@admin.register(InventorySession)
class InventorySessionAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'started_at', 'ended_at', 'started_by')
    list_filter = ('status',)
    search_fields = ('name',)


@admin.register(InventoryRecord)
class InventoryRecordAdmin(admin.ModelAdmin):
    list_display = ('session', 'location', 'barcode', 'product_name', 'quantity', 'expiry_date', 'lot_number', 'worker', 'created_at')
    list_filter = ('session',)
    search_fields = ('barcode', 'product_name', 'lot_number', 'location__barcode')


class InboundImageInline(admin.TabularInline):
    """입고 이미지 인라인 (입고 기록 편집 시 이미지 관리)"""
    model = InboundImage
    extra = 1
    readonly_fields = ('image_preview', 'created_at')
    fields = ('image', 'image_preview', 'created_at')

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height:80px; border-radius:4px;" />', obj.image.url)
        return '-'
    image_preview.short_description = '미리보기'


@admin.register(InboundRecord)
class InboundRecordAdmin(admin.ModelAdmin):
    list_display = ('product', 'quantity', 'expiry_date', 'lot_number', 'status', 'image_count', 'registered_by', 'created_at', 'completed_by', 'completed_at')
    list_filter = ('status', 'created_at')
    search_fields = ('product__name', 'product__barcode', 'lot_number', 'memo')
    raw_id_fields = ('product', 'registered_by', 'completed_by')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [InboundImageInline]
    list_per_page = 30

    def image_count(self, obj):
        count = obj.images.count()
        return f'{count}장' if count else '-'
    image_count.short_description = '이미지'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'product', 'registered_by', 'completed_by'
        ).prefetch_related('images')


@admin.register(InboundImage)
class InboundImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'inbound_record', 'image_preview', 'created_at')
    list_filter = ('created_at',)
    raw_id_fields = ('inbound_record',)
    readonly_fields = ('image_preview_large', 'created_at')

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height:40px; border-radius:4px;" />', obj.image.url)
        return '-'
    image_preview.short_description = '미리보기'

    def image_preview_large(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height:300px; border-radius:8px;" />', obj.image.url)
        return '-'
    image_preview_large.short_description = '이미지 미리보기'
