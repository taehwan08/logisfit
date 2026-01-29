"""
거래처 API 뷰 모듈

DRF ViewSet 기반 API를 정의합니다.
"""
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone

from .models import Client, PriceContract
from .serializers import (
    ClientSerializer, ClientListSerializer, PriceContractSerializer
)


class ClientViewSet(viewsets.ModelViewSet):
    """거래처 API ViewSet"""
    queryset = Client.objects.select_related('created_by')
    serializer_class = ClientSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['company_name', 'business_number', 'contact_person']
    ordering_fields = ['company_name', 'created_at']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return ClientListSerializer
        return ClientSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['get'])
    def price_contracts(self, request, pk=None):
        """특정 거래처의 단가 계약 목록 조회"""
        client = self.get_object()
        contracts = client.price_contracts.all()
        serializer = PriceContractSerializer(contracts, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='current-prices')
    def current_prices(self, request, pk=None):
        """현재 유효한 단가 조회"""
        client = self.get_object()
        today = timezone.now().date()
        contracts = client.price_contracts.filter(
            valid_from__lte=today,
            valid_to__gte=today,
        )
        serializer = PriceContractSerializer(contracts, many=True)
        return Response(serializer.data)


class PriceContractViewSet(viewsets.ModelViewSet):
    """단가 계약 API ViewSet"""
    queryset = PriceContract.objects.select_related('client', 'created_by')
    serializer_class = PriceContractSerializer
    filter_backends = [filters.OrderingFilter]
    ordering = ['-valid_from']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)