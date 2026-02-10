"""
URL 설정

프로젝트의 URL 패턴을 정의합니다.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from django.http import JsonResponse

# 대시보드 뷰 (임시로 TemplateView 사용, 추후 별도 뷰로 분리)
from apps.accounts.views import DashboardView


def health_check(request):
    """Railway healthcheck 엔드포인트"""
    return JsonResponse({'status': 'ok'})


urlpatterns = [
    # Healthcheck (Railway용)
    path('health/', health_check, name='health_check'),

    # Django 관리자
    path('admin/', admin.site.urls),

    # 대시보드 (홈)
    path('', DashboardView.as_view(), name='dashboard'),

    # 계정 관련
    path('accounts/', include('apps.accounts.urls')),

    # API v1
    path('api/v1/', include('apps.accounts.api_urls')),
    path('api/v1/', include('apps.clients.api_urls')),

    # 거래처 관리
    path('clients/', include('apps.clients.urls')),

    # 바코드 검수
    path('inspection/', include('apps.inspection.urls')),

    # Phase 3 이후 추가될 URL들
    # path('works/', include('apps.works.urls')),
    # path('storage/', include('apps.storage.urls')),
    # path('invoices/', include('apps.invoices.urls')),
    # path('contracts/', include('apps.contracts.urls')),
]

# 개발 환경에서 미디어 파일 서빙
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

    # Debug Toolbar
    try:
        import debug_toolbar
        urlpatterns = [
            path('__debug__/', include(debug_toolbar.urls)),
        ] + urlpatterns
    except ImportError:
        pass
