"""
출력 관리 뷰
"""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.waves.permissions import IsFieldStaff

from .models import PrintJob
from .serializers import PrintJobSerializer
from .services import PrintService


class PendingPrintJobsView(APIView):
    """미출력 건 조회

    GET /api/v1/printing/pending/
    """

    permission_classes = [IsFieldStaff]

    def get(self, request):
        jobs = (
            PrintJob.objects
            .filter(status='PENDING')
            .select_related('order', 'printer', 'carrier', 'printed_by')
        )
        serializer = PrintJobSerializer(jobs, many=True)
        return Response(serializer.data)


class ReprintView(APIView):
    """재출력 API

    POST /api/v1/printing/reprint/{print_job_id}/
    PENDING 또는 FAILED 상태의 PrintJob을 재전송합니다.
    """

    permission_classes = [IsFieldStaff]

    def post(self, request, print_job_id):
        try:
            print_job = PrintJob.objects.select_related(
                'order', 'printer', 'carrier',
            ).get(pk=print_job_id)
        except PrintJob.DoesNotExist:
            return Response(
                {'detail': '출력 작업을 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if print_job.status == 'PRINTED':
            return Response(
                {'detail': '이미 출력 완료된 작업입니다.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 프린터 재할당 (작업자의 현재 프린터)
        profile = getattr(request.user, 'worker_profile', None)
        if profile and profile.assigned_printer:
            print_job.printer = profile.assigned_printer
            print_job.save(update_fields=['printer'])

        # 재전송
        print_job.printed_by = request.user
        print_job.save(update_fields=['printed_by'])

        from .tasks import send_to_printer_task
        send_to_printer_task.delay(print_job.id)

        return Response({
            'success': True,
            'print_job_id': print_job.id,
            'status': print_job.status,
        })
