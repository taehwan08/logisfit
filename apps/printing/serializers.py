"""
출력 관리 시리얼라이저
"""
from rest_framework import serializers

from .models import PrintJob


class PrintJobSerializer(serializers.ModelSerializer):
    wms_order_id = serializers.CharField(
        source='order.wms_order_id', read_only=True,
    )
    printer_name = serializers.CharField(
        source='printer.name', read_only=True, default=None,
    )
    carrier_name = serializers.CharField(
        source='carrier.name', read_only=True, default=None,
    )
    printed_by_name = serializers.CharField(
        source='printed_by.name', read_only=True, default=None,
    )

    class Meta:
        model = PrintJob
        fields = [
            'id', 'order', 'wms_order_id',
            'printer', 'printer_name',
            'carrier', 'carrier_name',
            'tracking_number', 'status',
            'attempts', 'error_message',
            'printed_at', 'printed_by', 'printed_by_name',
            'created_at',
        ]
