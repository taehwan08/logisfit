"""
시스템 설정 초기 데이터 시딩
"""
from django.db import migrations


INITIAL_CONFIGS = [
    {
        'key': 'wave_times',
        'value': ["09:00", "12:00", "15:00"],
        'description': '웨이브 생성 시간',
    },
    {
        'key': 'default_allocation_rule',
        'value': 'FIFO',
        'description': '기본 재고 할당 규칙',
    },
    {
        'key': 'archive_after_days',
        'value': 365,
        'description': '히스토리 아카이빙 기준일',
    },
    {
        'key': 'webhook_max_retries',
        'value': 3,
        'description': 'Webhook 최대 재시도',
    },
    {
        'key': 'sabangnet_polling_interval_minutes',
        'value': 5,
        'description': '사방넷 폴링 주기(분)',
    },
]


def forward(apps, schema_editor):
    SystemConfig = apps.get_model('accounts', 'SystemConfig')
    for cfg in INITIAL_CONFIGS:
        SystemConfig.objects.get_or_create(
            key=cfg['key'],
            defaults={
                'value': cfg['value'],
                'description': cfg['description'],
            },
        )


def backward(apps, schema_editor):
    SystemConfig = apps.get_model('accounts', 'SystemConfig')
    keys = [cfg['key'] for cfg in INITIAL_CONFIGS]
    SystemConfig.objects.filter(key__in=keys).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_add_system_config'),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
