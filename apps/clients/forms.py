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
        fields = ['work_type', 'unit_price', 'unit', 'valid_from', 'valid_to', 'memo']
        widgets = {
            'work_type': forms.Select(attrs={'class': 'form-select'}),
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
    """단가 계약 일괄 등록 폼 - 모든 작업유형을 테이블로 한번에 입력"""

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

    def __init__(self, *args, **kwargs):
        self.client = kwargs.pop('client', None)
        super().__init__(*args, **kwargs)
        for value, label in WorkType.choices:
            self.fields[f'price_{value}'] = forms.DecimalField(
                required=False,
                min_value=0,
                max_digits=10,
                decimal_places=2,
                widget=forms.NumberInput(attrs={
                    'class': 'form-control form-control-sm',
                    'placeholder': '0',
                    'step': '1',
                }),
            )
            self.fields[f'unit_{value}'] = forms.CharField(
                required=False,
                max_length=20,
                initial=_get_default_unit(value),
                widget=forms.TextInput(attrs={
                    'class': 'form-control form-control-sm',
                    'style': 'width: 100px;',
                }),
            )

    def clean(self):
        cleaned_data = super().clean()
        valid_from = cleaned_data.get('valid_from')
        valid_to = cleaned_data.get('valid_to')

        if valid_from and valid_to and valid_from > valid_to:
            self.add_error('valid_to', '종료일은 시작일 이후여야 합니다.')

        return cleaned_data

    def get_work_type_groups(self):
        """템플릿에서 카테고리별로 그룹핑해서 렌더링하기 위한 데이터"""
        groups = []
        for group_name, types in WORK_TYPE_GROUPS:
            items = []
            for wt in types:
                items.append({
                    'value': wt.value,
                    'label': wt.label,
                    'price_field': self[f'price_{wt.value}'],
                    'unit_field': self[f'unit_{wt.value}'],
                })
            groups.append((group_name, items))
        return groups

    def save(self, user=None):
        """입력된 단가가 있는 항목만 PriceContract로 생성"""
        cleaned = self.cleaned_data
        valid_from = cleaned['valid_from']
        valid_to = cleaned['valid_to']
        memo = cleaned.get('memo', '')

        contracts = []
        for value, label in WorkType.choices:
            price = cleaned.get(f'price_{value}')
            unit = cleaned.get(f'unit_{value}') or _get_default_unit(value)
            if price is not None and price > 0:
                contracts.append(PriceContract(
                    client=self.client,
                    work_type=value,
                    unit_price=price,
                    unit=unit,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    memo=memo,
                    created_by=user,
                ))

        if contracts:
            PriceContract.objects.bulk_create(contracts)
        return contracts
