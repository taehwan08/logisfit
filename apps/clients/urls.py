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

    # 단가 계약
    path('<int:client_id>/price-contract/create/',
         views.PriceContractCreateView.as_view(), name='price_contract_create'),
    path('price-contract/<int:pk>/update/',
         views.PriceContractUpdateView.as_view(), name='price_contract_update'),
    path('price-contract/<int:pk>/delete/',
         views.PriceContractDeleteView.as_view(), name='price_contract_delete'),

    # 파레트 보관료
    path('<int:client_id>/pallet-price/create/',
         views.PalletStoragePriceCreateView.as_view(), name='pallet_price_create'),
    path('pallet-price/<int:pk>/update/',
         views.PalletStoragePriceUpdateView.as_view(), name='pallet_price_update'),
    path('pallet-price/<int:pk>/delete/',
         views.PalletStoragePriceDeleteView.as_view(), name='pallet_price_delete'),
]
