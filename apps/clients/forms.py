"""
거래처 폼 모듈

거래처 등록/수정, 단가 계약, 파레트 보관료 폼을 정의합니다.
"""
import re
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q

from .models import Client, PriceContract, PalletStoragePrice


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
    """단가 계약 등록/수정 폼"""

    class Meta:
        model = PriceContract
        fields = ['work_type', 'unit_price', 'unit', 'valid_from', 'valid_to', 'memo']
        widgets = {
            'work_type': forms.Select(attrs={'class': 'form-select'}),
            'unit_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '단가',
            }),
            'unit': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '건',
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
        """유효기간 및 기간 겹침 검증"""
        cleaned_data = super().clean()
        valid_from = cleaned_data.get('valid_from')
        valid_to = cleaned_data.get('valid_to')

        if valid_from and valid_to and valid_from > valid_to:
            self.add_error('valid_to', '종료일은 시작일 이후여야 합니다.')

        return cleaned_data


class PalletStoragePriceForm(forms.ModelForm):
    """파레트 보관료 등록/수정 폼"""

    class Meta:
        model = PalletStoragePrice
        fields = ['daily_price', 'monthly_price', 'valid_from', 'valid_to', 'memo']
        widgets = {
            'daily_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '일 단가',
            }),
            'monthly_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '월 단가 (선택)',
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
