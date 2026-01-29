"""
거래처 API URL 라우팅
"""
from rest_framework.routers import DefaultRouter
from .api_views import ClientViewSet, PriceContractViewSet

router = DefaultRouter()
router.register(r'clients', ClientViewSet, basename='client')
router.register(r'price-contracts', PriceContractViewSet, basename='price-contract')

urlpatterns = router.urls
