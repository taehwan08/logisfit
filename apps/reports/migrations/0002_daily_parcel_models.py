# Generated manually — 일일 출고 리포트 모델

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('reports', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='DailyParcelReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report_date', models.DateField(unique=True, verbose_name='리포트 날짜')),
                ('file_name', models.CharField(max_length=200, verbose_name='업로드 파일명')),
                ('total_orders', models.IntegerField(default=0, verbose_name='총 출고건수')),
                ('single_count', models.IntegerField(default=0, verbose_name='단포 건수')),
                ('combo_count', models.IntegerField(default=0, verbose_name='합포 건수')),
                ('uploaded_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='parcel_reports',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='업로드자',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='최초 등록')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='최종 수정')),
            ],
            options={
                'verbose_name': '일일 출고 리포트',
                'verbose_name_plural': '일일 출고 리포트',
                'db_table': 'daily_parcel_reports',
                'ordering': ['-report_date'],
            },
        ),
        migrations.CreateModel(
            name='DailyParcelBrand',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('brand_name', models.CharField(max_length=100, verbose_name='브랜드')),
                ('single_count', models.IntegerField(default=0, verbose_name='단포')),
                ('combo_count', models.IntegerField(default=0, verbose_name='합포')),
                ('total_count', models.IntegerField(default=0, verbose_name='합계')),
                ('report', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='brands',
                    to='reports.dailyparcelreport',
                    verbose_name='리포트',
                )),
            ],
            options={
                'verbose_name': '브랜드별 출고',
                'verbose_name_plural': '브랜드별 출고',
                'db_table': 'daily_parcel_brands',
                'ordering': ['-total_count'],
            },
        ),
    ]
