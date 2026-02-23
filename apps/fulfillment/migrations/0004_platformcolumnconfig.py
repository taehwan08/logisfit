# Generated manually for platform column configuration
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fulfillment', '0003_restructure_for_bulk_paste'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlatformColumnConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('platform', models.CharField(
                    choices=[
                        ('coupang', '쿠팡'), ('kurly', '컬리'), ('oliveyoung', '올리브영'),
                        ('smartstore', '스마트스토어'), ('offline', '오프라인마트'),
                        ('export', '해외수출'), ('other', '기타'),
                    ],
                    max_length=20, verbose_name='플랫폼',
                )),
                ('name', models.CharField(max_length=100, verbose_name='컬럼명', help_text='한글 표시명 (예: 배송유형)')),
                ('key', models.CharField(max_length=100, verbose_name='컬럼 키', help_text='내부 저장 키 (영문, 예: delivery_type)')),
                ('column_type', models.CharField(
                    choices=[('text', '텍스트'), ('number', '숫자'), ('date', '날짜')],
                    default='text', max_length=20, verbose_name='타입',
                )),
                ('display_order', models.IntegerField(default=0, verbose_name='표시 순서')),
                ('is_required', models.BooleanField(default=False, verbose_name='필수 여부')),
                ('is_active', models.BooleanField(default=True, verbose_name='활성 상태')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='등록일시')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='수정일시')),
            ],
            options={
                'verbose_name': '플랫폼 컬럼 설정',
                'verbose_name_plural': '플랫폼 컬럼 설정 목록',
                'db_table': 'fulfillment_platform_column_configs',
                'ordering': ['platform', 'display_order', 'id'],
                'indexes': [
                    models.Index(fields=['platform', 'is_active'], name='idx_platform_col_active'),
                ],
                'constraints': [
                    models.UniqueConstraint(fields=['platform', 'key'], name='uq_platform_column_key'),
                ],
            },
        ),
    ]
