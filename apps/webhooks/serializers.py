"""
웹훅 관리 시리얼라이저
"""
from rest_framework import serializers

from .models import WebhookSubscriber, WebhookLog, WebhookEvents


class WebhookSubscriberSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookSubscriber
        fields = [
            'id', 'name', 'url', 'events',
            'is_active', 'secret_key', 'created_at',
        ]
        extra_kwargs = {
            'secret_key': {'write_only': True},
        }

    def validate_events(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('events는 리스트여야 합니다.')
        invalid = [e for e in value if e not in WebhookEvents.ALL]
        if invalid:
            raise serializers.ValidationError(
                f"유효하지 않은 이벤트: {', '.join(invalid)}. "
                f"가능한 이벤트: {', '.join(WebhookEvents.ALL)}"
            )
        return value


class WebhookLogSerializer(serializers.ModelSerializer):
    subscriber_name = serializers.CharField(
        source='subscriber.name', read_only=True,
    )

    class Meta:
        model = WebhookLog
        fields = [
            'id', 'subscriber', 'subscriber_name',
            'event', 'payload', 'status_code',
            'attempts', 'success', 'error_message',
            'created_at',
        ]
