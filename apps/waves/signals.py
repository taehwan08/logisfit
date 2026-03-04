"""
웨이브 관리 시그널

주문 검수 완료 시 송장 출력 등 후속 처리를 위한 시그널.
"""
import django.dispatch

# 주문 검수 완료 시 발행 (sender=OutboundOrder, order=instance, user=request.user)
order_inspected = django.dispatch.Signal()
