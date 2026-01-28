"""
거래처 API URL 라우팅
"""
from rest_framework.routers import DefaultRouter
from .api_views import ClientViewSet, PriceContractViewSet, PalletStoragePriceViewSet

router = DefaultRouter()
router.register(r'clients', ClientViewSet, basename='client')
router.register(r'price-contracts', PriceContractViewSet, basename='price-contract')
router.register(r'pallet-prices', PalletStoragePriceViewSet, basename='pallet-price')

urlpatterns = router.urls
