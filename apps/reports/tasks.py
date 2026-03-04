"""
리포트 Celery 태스크
"""
import logging
from datetime import date

from django.utils import timezone

from config.celery import app

logger = logging.getLogger(__name__)


SERVICE_MAP = {
    'INVENTORY_LEDGER': 'get_inventory_ledger',
    'SHIPMENT_SUMMARY': 'get_shipment_summary_flat',
    'WORKER_PRODUCTIVITY': 'get_worker_productivity',
    'SAFETY_STOCK_ALERT': 'get_safety_stock_alerts',
}

COLUMN_MAP = None  # 지연 import


def _get_column_map():
    from .views import (
        LEDGER_COLUMNS, SHIPMENT_COLUMNS, WORKER_COLUMNS, SAFETY_COLUMNS,
    )
    return {
        'INVENTORY_LEDGER': (LEDGER_COLUMNS, '재고원장'),
        'SHIPMENT_SUMMARY': (SHIPMENT_COLUMNS, '출고요약'),
        'WORKER_PRODUCTIVITY': (WORKER_COLUMNS, '작업자생산성'),
        'SAFETY_STOCK_ALERT': (SAFETY_COLUMNS, '안전재고알림'),
    }


def _deserialize_params(params):
    """JSON params의 날짜 문자열을 date 객체로 변환"""
    out = {}
    for k, v in params.items():
        if k in ('date_from', 'date_to') and isinstance(v, str):
            out[k] = date.fromisoformat(v)
        else:
            out[k] = v
    return out


@app.task(bind=True, max_retries=2, default_retry_delay=60)
def generate_report_excel(self, report_file_id):
    """비동기 리포트 엑셀 생성"""
    from .models import ReportFile
    from .excel import build_workbook, workbook_to_file
    from . import services

    try:
        rf = ReportFile.objects.get(pk=report_file_id)
        rf.status = 'PROCESSING'
        rf.save(update_fields=['status'])

        func_name = SERVICE_MAP[rf.report_type]
        func = getattr(services, func_name)
        params = _deserialize_params(rf.params)
        data = func(**params)

        col_map = _get_column_map()
        columns, sheet_title = col_map[rf.report_type]

        wb = build_workbook(data, columns, sheet_title)
        filename = f'{sheet_title}_{timezone.localtime().strftime("%Y%m%d_%H%M%S")}.xlsx'
        content_file = workbook_to_file(wb, filename)

        rf.file.save(filename, content_file, save=False)
        rf.file_name = filename
        rf.row_count = len(data)
        rf.status = 'COMPLETED'
        rf.completed_at = timezone.now()
        rf.save()

        logger.info('리포트 생성 완료: %s (ID=%d, %d행)', sheet_title, rf.id, len(data))

    except Exception as exc:
        logger.exception('리포트 생성 실패: ID=%d', report_file_id)
        ReportFile.objects.filter(pk=report_file_id).update(
            status='FAILED',
            error_message=str(exc)[:500],
        )
        raise self.retry(exc=exc)
