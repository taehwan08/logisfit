"""
출력 관리 Celery 태스크
"""
from config.celery import app


@app.task(bind=True, max_retries=2, default_retry_delay=5)
def send_to_printer_task(self, print_job_id):
    """프린터 전송 비동기 태스크"""
    from .services import PrintService
    PrintService.send_to_printer(print_job_id)
