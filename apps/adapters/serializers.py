"""
외부 연동 어댑터 시리얼라이저
"""
from rest_framework import serializers


class B2BUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    client_id = serializers.IntegerField()
