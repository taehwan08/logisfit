"""
웹훅 관리 뷰
"""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.waves.permissions import IsOfficeStaff

from .models import WebhookSubscriber, WebhookLog
from .serializers import WebhookSubscriberSerializer, WebhookLogSerializer


class WebhookSubscriberListView(APIView):
    """구독자 목록 / 생성

    GET  /api/v1/webhooks/subscribers/
    POST /api/v1/webhooks/subscribers/
    """

    permission_classes = [IsOfficeStaff]

    def get(self, request):
        subscribers = WebhookSubscriber.objects.all()
        serializer = WebhookSubscriberSerializer(subscribers, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = WebhookSubscriberSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class WebhookSubscriberDetailView(APIView):
    """구독자 상세 / 수정 / 삭제

    GET    /api/v1/webhooks/subscribers/{id}/
    PUT    /api/v1/webhooks/subscribers/{id}/
    DELETE /api/v1/webhooks/subscribers/{id}/
    """

    permission_classes = [IsOfficeStaff]

    def _get_subscriber(self, pk):
        try:
            return WebhookSubscriber.objects.get(pk=pk)
        except WebhookSubscriber.DoesNotExist:
            return None

    def get(self, request, pk):
        subscriber = self._get_subscriber(pk)
        if not subscriber:
            return Response(
                {'detail': '구독자를 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(WebhookSubscriberSerializer(subscriber).data)

    def put(self, request, pk):
        subscriber = self._get_subscriber(pk)
        if not subscriber:
            return Response(
                {'detail': '구독자를 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = WebhookSubscriberSerializer(
            subscriber, data=request.data, partial=True,
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        subscriber = self._get_subscriber(pk)
        if not subscriber:
            return Response(
                {'detail': '구독자를 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        subscriber.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WebhookLogListView(APIView):
    """웹훅 로그 조회

    GET /api/v1/webhooks/logs/
    """

    permission_classes = [IsOfficeStaff]

    def get(self, request):
        logs = WebhookLog.objects.select_related('subscriber').all()[:100]

        event = request.query_params.get('event')
        if event:
            logs = logs.filter(event=event)

        success = request.query_params.get('success')
        if success is not None:
            logs = logs.filter(success=success.lower() == 'true')

        serializer = WebhookLogSerializer(logs, many=True)
        return Response(serializer.data)
