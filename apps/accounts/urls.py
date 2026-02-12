"""
계정 URL 설정

사용자 인증 및 관리 관련 URL 패턴을 정의합니다.
"""
from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    # 인증
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.CustomLogoutView.as_view(), name='logout'),
    path('register/', views.RegisterView.as_view(), name='register'),

    # 프로필
    path('profile/', views.ProfileView.as_view(), name='profile'),

    # 사용자 관리 (관리자용)
    path('users/', views.UserListView.as_view(), name='user_list'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user_detail'),
    path('users/<int:pk>/approve/', views.UserApprovalView.as_view(), name='user_approval'),
    path('users/<int:pk>/toggle-active/', views.UserToggleActiveView.as_view(), name='user_toggle_active'),

    # Slack 연동
    path('slack/interactive/', views.SlackInteractiveView.as_view(), name='slack_interactive'),
]
