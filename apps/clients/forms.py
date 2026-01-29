"""
거래처 폼 모듈

거래처 등록/수정, 단가 계약 (개별/일괄) 폼을 정의합니다.
"""
import re

from django import forms
from django.core.exceptions import ValidationError

from .models import Client, PriceContract, WorkType, WORK_TYPE_GROUPS


# 작업유형별 기본 단위
DEFAULT_UNITS = {
    'STORAGE': '팔레트/일',
}


def _get_default_unit(work_type_value):
    return DEFAULT_UNITS.get(work_type_value, '건')


class ClientForm(forms.ModelForm):
    """거래처 등록/수정 폼"""

    class Meta:
        model = Client
        fields = [
            'company_name', 'business_number',
            'contact_person', 'contact_phone', 'contact_email',
            'contract_start_date', 'contract_end_date',
            'invoice_email', 'invoice_day',
            'address', 'address_detail',
            'memo', 'is_active',
        ]
        widgets = {
            'company_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '회사명을 입력하세요',
            }),
            'business_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '123-45-67890',
                'data-format': 'business-number',
            }),
            'contact_person': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '담당자명',
            }),
            'contact_phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '010-1234-5678',
                'data-format': 'phone',
            }),
            'contact_email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'email@example.com',
            }),
            'contract_start_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'contract_end_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'invoice_email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'invoice@example.com',
            }),
            'invoice_day': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 28,
            }),
            'address': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '주소',
            }),
            'address_detail': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '상세 주소',
            }),
            'memo': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': '메모를 입력하세요',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }

    def clean_business_number(self):
        """사업자등록번호 하이픈 자동 추가"""
        value = self.cleaned_data['business_number']
        digits = re.sub(r'[^0-9]', '', value)
        if len(digits) != 10:
            raise ValidationError('사업자등록번호는 10자리 숫자여야 합니다.')
        return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"

    def clean_invoice_day(self):
        """청구서 발송일 범위 검증"""
        value = self.cleaned_data['invoice_day']
        if not 1 <= value <= 28:
            raise ValidationError('청구서 발송일은 1~28 사이의 값이어야 합니다.')
        return value

    def clean(self):
        """폼 전체 검증"""
        cleaned_data = super().clean()
        start = cleaned_data.get('contract_start_date')
        end = cleaned_data.get('contract_end_date')
        if start and end and start > end:
            self.add_error('contract_end_date', '계약 종료일은 시작일 이후여야 합니다.')
        return cleaned_data


class PriceContractForm(forms.ModelForm):
    """단가 계약 개별 등록/수정 폼"""

    class Meta:
        model = PriceContract
        fields = [
            'work_type', 'sub_category', 'item_name',
            'unit_price', 'unit', 'quantity', 'remarks',
            'valid_from', 'valid_to', 'memo',
        ]
        widgets = {
            'work_type': forms.Select(attrs={'class': 'form-select'}),
            'sub_category': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '소분류 (선택)',
            }),
            'item_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '품목 (예: 박스, 팔레트)',
            }),
            'unit_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '1',
                'min': '0',
                'placeholder': '단가',
            }),
            'unit': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '건/pt',
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': '수량',
            }),
            'remarks': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '비고',
            }),
            'valid_from': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'valid_to': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'memo': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': '메모',
            }),
        }

    def clean(self):
        """유효기간 검증"""
        cleaned_data = super().clean()
        valid_from = cleaned_data.get('valid_from')
        valid_to = cleaned_data.get('valid_to')

        if valid_from and valid_to and valid_from > valid_to:
            self.add_error('valid_to', '종료일은 시작일 이후여야 합니다.')

        return cleaned_data


class PriceContractBulkForm(forms.Form):
    """단가 계약 일괄 등록 폼 - 동적 행 추가/삭제로 여러 항목을 한번에 입력"""

    valid_from = forms.DateField(
        label='적용 시작일',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    valid_to = forms.DateField(
        label='적용 종료일',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    memo = forms.CharField(
        label='메모',
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': '메모'}),
    )
    row_count = forms.IntegerField(widget=forms.HiddenInput(), initial=0)

    def __init__(self, *args, **kwargs):
        self.client = kwargs.pop('client', None)
        super().__init__(*args, **kwargs)

        # POST 데이터에서 동적 행 필드를 생성
        if self.data:
            try:
                row_count = int(self.data.get('row_count', 0))
            except (ValueError, TypeError):
                row_count = 0

            for i in range(row_count):
                self._add_row_fields(i)

    def _add_row_fields(self, index):
        """동적 행에 대한 필드 추가"""
        prefix = f'row_{index}'
        self.fields[f'{prefix}_work_type'] = forms.ChoiceField(
            choices=[('', '---')] + list(WorkType.choices),
            required=False,
            widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
        )
        self.fields[f'{prefix}_sub_category'] = forms.CharField(
            required=False, max_length=100,
            widget=forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': '소분류',
            }),
        )
        self.fields[f'{prefix}_item_name'] = forms.CharField(
            required=False, max_length=100,
            widget=forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': '품목',
            }),
        )
        self.fields[f'{prefix}_unit_price'] = forms.DecimalField(
            required=False, min_value=0, max_digits=10, decimal_places=2,
            widget=forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': '0',
                'step': '1',
            }),
        )
        self.fields[f'{prefix}_unit'] = forms.CharField(
            required=False, max_length=20,
            widget=forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': '건',
                'style': 'width: 80px;',
            }),
        )
        self.fields[f'{prefix}_quantity'] = forms.IntegerField(
            required=False, min_value=0,
            widget=forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': '1',
                'style': 'width: 70px;',
            }),
        )
        self.fields[f'{prefix}_remarks'] = forms.CharField(
            required=False, max_length=200,
            widget=forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': '비고',
            }),
        )

    def clean(self):
        cleaned_data = super().clean()
        valid_from = cleaned_data.get('valid_from')
        valid_to = cleaned_data.get('valid_to')

        if valid_from and valid_to and valid_from > valid_to:
            self.add_error('valid_to', '종료일은 시작일 이후여야 합니다.')

        # 최소 1개 행이 유효한지 확인
        row_count = int(cleaned_data.get('row_count', 0))
        has_valid_row = False
        for i in range(row_count):
            prefix = f'row_{i}'
            work_type = cleaned_data.get(f'{prefix}_work_type')
            unit_price = cleaned_data.get(f'{prefix}_unit_price')
            if work_type and unit_price is not None and unit_price > 0:
                has_valid_row = True
                break

        if not has_valid_row and not self.errors:
            raise ValidationError('최소 1개 이상의 단가 항목을 입력해주세요.')

        return cleaned_data

    @staticmethod
    def get_work_type_groups_data():
        """작업유형 그룹 데이터 (JavaScript에서 사용)"""
        groups = []
        for group_name, types in WORK_TYPE_GROUPS:
            items = [{'value': wt.value, 'label': wt.label} for wt in types]
            groups.append({'name': group_name, 'items': items})
        return groups

    def save(self, user=None):
        """입력된 행을 PriceContract로 생성"""
        cleaned = self.cleaned_data
        valid_from = cleaned['valid_from']
        valid_to = cleaned['valid_to']
        memo = cleaned.get('memo', '')
        row_count = int(cleaned.get('row_count', 0))

        contracts = []
        for i in range(row_count):
            prefix = f'row_{i}'
            work_type = cleaned.get(f'{prefix}_work_type')
            unit_price = cleaned.get(f'{prefix}_unit_price')
            if not work_type or unit_price is None or unit_price <= 0:
                continue

            sub_category = cleaned.get(f'{prefix}_sub_category', '')
            item_name = cleaned.get(f'{prefix}_item_name', '')
            unit = cleaned.get(f'{prefix}_unit') or _get_default_unit(work_type)
            quantity = cleaned.get(f'{prefix}_quantity') or 1
            remarks = cleaned.get(f'{prefix}_remarks', '')

            contracts.append(PriceContract(
                client=self.client,
                work_type=work_type,
                sub_category=sub_category,
                item_name=item_name,
                unit_price=unit_price,
                unit=unit,
                quantity=quantity,
                remarks=remarks,
                valid_from=valid_from,
                valid_to=valid_to,
                memo=memo,
                created_by=user,
            ))

        if contracts:
            PriceContract.objects.bulk_create(contracts)
        return contracts
