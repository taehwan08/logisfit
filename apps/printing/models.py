"""
출력 관리 모델

Phase 3에서 구현 — 송장 라벨, 거래명세서, 바코드 라벨 출력 등
"""
from django.db import models


class Printer(models.Model):
    """
    프린터 모델 (스텁)

    Phase 3에서 상세 구현. 현재는 accounts.WorkerProfile FK 참조를 위한 최소 정의.
    """

    name = models.CharField('프린터명', max_length=100)
    is_active = models.BooleanField('활성 상태', default=True)
    created_at = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        verbose_name = '프린터'
        verbose_name_plural = '프린터 목록'
        db_table = 'printers'

    def __str__(self):
        return self.name


class Carrier(models.Model):
    """
    택배사 모델 (스텁)

    Phase 3에서 상세 구현. 현재는 clients.Client FK 참조를 위한 최소 정의.
    """

    name = models.CharField('택배사명', max_length=100)
    code = models.CharField('택배사 코드', max_length=20, unique=True)
    is_active = models.BooleanField('활성 상태', default=True)
    created_at = models.DateTimeField('등록일시', auto_now_add=True)

    class Meta:
        verbose_name = '택배사'
        verbose_name_plural = '택배사 목록'
        db_table = 'carriers'

    def __str__(self):
        return self.name
