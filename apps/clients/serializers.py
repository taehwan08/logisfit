"""
거래처 시리얼라이저 모듈

DRF API용 시리얼라이저를 정의합니다.
"""
from rest_framework import serializers
from .models import Client, PriceContract


class ClientListSerializer(serializers.ModelSerializer):
    """거래처 목록용 시리얼라이저 (간단한 정보만)"""

    class Meta:
        model = Client
        fields = [
            'id', 'company_name', 'business_number',
            'contact_person', 'contact_phone', 'is_active',
        ]


class ClientSerializer(serializers.ModelSerializer):
    """거래처 상세 시리얼라이저"""
    created_by_name = serializers.CharField(source='created_by.name', read_only=True, default='')
    is_contract_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Client
        fields = '__all__'
        read_only_fields = ['created_by', 'created_at', 'updated_at']


class PriceContractSerializer(serializers.ModelSerializer):
    """단가 계약 시리얼라이저"""
    client_name = serializers.CharField(source='client.company_name', read_only=True)
    work_type_display = serializers.CharField(source='get_work_type_display', read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = PriceContract
        fields = '__all__'
        read_only_fields = ['created_by', 'created_at']

    def validate(self, data):
        valid_from = data.get('valid_from')
        valid_to = data.get('valid_to')
        if valid_from and valid_to and valid_from > valid_to:
            raise serializers.ValidationError('종료일은 시작일 이후여야 합니다.')
        return data
