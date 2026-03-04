"""
웹훅 관리 모델

외부 시스템에 이벤트를 전달하기 위한 웹훅 구독 및 배달 로그.
"""
from django.db import models


class WebhookEvents:
    """웹훅 이벤트 타입 상수"""
    ORDER_RECEIVED = 'ORDER_RECEIVED'
    ORDER_ALLOCATED = 'ORDER_ALLOCATED'
    ORDER_PICKED = 'ORDER_PICKED'
    ORDER_SHIPPED = 'ORDER_SHIPPED'
    ORDER_HELD = 'ORDER_HELD'
    ORDER_CANCELLED = 'ORDER_CANCELLED'
    INVENTORY_CHANGED = 'INVENTORY_CHANGED'

    ALL = [
        ORDER_RECEIVED, ORDER_ALLOCATED, ORDER_PICKED,
        ORDER_SHIPPED, ORDER_HELD, ORDER_CANCELLED,
        INVENTORY_CHANGED,
    ]


class WebhookSubscriber(models.Model):
    """웹훅 구독자"""

    name = models.CharField('구독자명', max_length=100)
    url = models.URLField('수신 URL')
    events = models.JSONField('구독 이벤트', default=list)
    is_active = models.BooleanField('활성', default=True)
    secret_key = models.CharField(
        '서명 키', max_length=200, blank=True, default='',
    )
    created_at = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        verbose_name = '웹훅 구독자'
        verbose_name_plural = '웹훅 구독자'
        db_table = 'webhook_subscribers'

    def __str__(self):
        return f'{self.name} ({self.url})'


class WebhookLog(models.Model):
    """웹훅 배달 로그"""

    subscriber = models.ForeignKey(
        WebhookSubscriber, on_delete=models.CASCADE,
        related_name='logs', verbose_name='구독자',
    )
    event = models.CharField('이벤트', max_length=50)
    payload = models.JSONField('페이로드')
    status_code = models.IntegerField('응답코드', null=True, blank=True)
    attempts = models.IntegerField('시도횟수', default=0)
    success = models.BooleanField('성공', default=False)
    error_message = models.TextField('오류메시지', blank=True, default='')
    created_at = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        verbose_name = '웹훅 로그'
        verbose_name_plural = '웹훅 로그'
        db_table = 'webhook_logs'
        ordering = ['-created_at']

    def __str__(self):
        status = '성공' if self.success else '실패'
        return f'{self.subscriber.name} - {self.event} ({status})'
