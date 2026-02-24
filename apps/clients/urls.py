"""
거래처 URL 라우팅
"""
from django.urls import path

from . import views

app_name = 'clients'

urlpatterns = [
    # 거래처 CRUD
    path('', views.ClientListView.as_view(), name='client_list'),
    path('create/', views.ClientCreateView.as_view(), name='client_create'),
    path('<int:pk>/', views.ClientDetailView.as_view(), name='client_detail'),
    path('<int:pk>/update/', views.ClientUpdateView.as_view(), name='client_update'),
    path('<int:pk>/delete/', views.ClientDeleteView.as_view(), name='client_delete'),

    # 단가 계약 (개별)
    path('<int:client_id>/price-contract/create/',
         views.PriceContractCreateView.as_view(), name='price_contract_create'),
    path('price-contract/<int:pk>/update/',
         views.PriceContractUpdateView.as_view(), name='price_contract_update'),
    path('price-contract/<int:pk>/delete/',
         views.PriceContractDeleteView.as_view(), name='price_contract_delete'),

    # 단가 계약 (일괄 등록)
    path('<int:client_id>/price-contracts/bulk/',
         views.PriceContractBulkCreateView.as_view(), name='price_contract_bulk'),

    # 거래처-사용자 매칭
    path('<int:pk>/users/add/', views.add_client_user, name='add_client_user'),
    path('<int:pk>/users/remove/', views.remove_client_user, name='remove_client_user'),
]
