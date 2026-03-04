"""
리포트 시리얼라이저
"""
from rest_framework import serializers


class DateRangeSerializer(serializers.Serializer):
    """공통 날짜 범위 파라미터"""
    date_from = serializers.DateField(required=True)
    date_to = serializers.DateField(required=True)

    def validate(self, data):
        if data['date_from'] > data['date_to']:
            raise serializers.ValidationError(
                'date_from은 date_to보다 이전이어야 합니다.'
            )
        return data


class InventoryLedgerParamSerializer(DateRangeSerializer):
    client_id = serializers.IntegerField(required=True)


class ShipmentSummaryParamSerializer(DateRangeSerializer):
    client_id = serializers.IntegerField(required=False)


class WorkerProductivityParamSerializer(DateRangeSerializer):
    pass


class SafetyStockAlertParamSerializer(serializers.Serializer):
    client_id = serializers.IntegerField(required=False)


class ReportFileSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    report_type = serializers.CharField()
    status = serializers.CharField()
    file_url = serializers.SerializerMethodField()
    file_name = serializers.CharField()
    row_count = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField()

    def get_file_url(self, obj):
        if obj.file:
            return obj.file.url
        return None
