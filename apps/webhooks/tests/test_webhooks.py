"""
웹훅 테스트

publish_event, deliver_webhook, HMAC 서명, 구독자 CRUD API,
waves 출고 연동 테스트.
"""
import hashlib
import hmac
import json
from unittest.mock import patch, MagicMock

import requests

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client
from apps.inventory.models import Product, Location, InventoryBalance
from apps.waves.models import OutboundOrder, OutboundOrderItem
from apps.waves.services import WaveService, ShipmentService

from apps.webhooks.models import WebhookSubscriber, WebhookLog, WebhookEvents
from apps.webhooks.services import publish_event, deliver


class WebhookTestMixin:
    """웹훅 테스트 공통"""

    def setUp(self):
        self.office_user = User.objects.create_user(
            email='office@test.com', password='test1234',
            name='오피스', role='office', is_approved=True,
        )
        self.client_user = User.objects.create_user(
            email='client@test.com', password='test1234',
            name='거래처유저', role='client', is_approved=True,
        )
        self.api = APIClient()

    def _create_subscriber(self, **kwargs):
        defaults = {
            'name': '테스트 구독자',
            'url': 'https://example.com/webhook',
            'events': [WebhookEvents.ORDER_SHIPPED],
            'is_active': True,
        }
        defaults.update(kwargs)
        return WebhookSubscriber.objects.create(**defaults)


# ------------------------------------------------------------------
# publish_event 테스트
# ------------------------------------------------------------------

class PublishEventTest(WebhookTestMixin, TestCase):

    @patch('apps.webhooks.tasks.deliver_webhook')
    def test_publish_dispatches_to_subscribers(self, mock_task):
        mock_task.delay = MagicMock()
        sub1 = self._create_subscriber(
            name='구독자1', events=[WebhookEvents.ORDER_SHIPPED],
        )
        sub2 = self._create_subscriber(
            name='구독자2', events=[WebhookEvents.ORDER_SHIPPED],
        )

        publish_event(WebhookEvents.ORDER_SHIPPED, {'order': 'WO-001'})

        self.assertEqual(mock_task.delay.call_count, 2)

    @patch('apps.webhooks.tasks.deliver_webhook')
    def test_publish_skips_inactive(self, mock_task):
        mock_task.delay = MagicMock()
        self._create_subscriber(is_active=False)

        publish_event(WebhookEvents.ORDER_SHIPPED, {'order': 'WO-001'})
        mock_task.delay.assert_not_called()

    @patch('apps.webhooks.tasks.deliver_webhook')
    def test_publish_skips_non_subscribed_events(self, mock_task):
        mock_task.delay = MagicMock()
        self._create_subscriber(events=[WebhookEvents.ORDER_CANCELLED])

        publish_event(WebhookEvents.ORDER_SHIPPED, {'order': 'WO-001'})
        mock_task.delay.assert_not_called()

    @patch('apps.webhooks.tasks.deliver_webhook')
    def test_publish_no_subscribers(self, mock_task):
        mock_task.delay = MagicMock()
        publish_event(WebhookEvents.ORDER_SHIPPED, {'order': 'WO-001'})
        mock_task.delay.assert_not_called()


# ------------------------------------------------------------------
# deliver 테스트
# ------------------------------------------------------------------

class DeliverTest(WebhookTestMixin, TestCase):

    @patch('apps.webhooks.services.requests.post')
    def test_deliver_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        sub = self._create_subscriber()
        payload = {'order': 'WO-001'}

        log = deliver(sub.id, WebhookEvents.ORDER_SHIPPED, payload)

        self.assertTrue(log.success)
        self.assertEqual(log.status_code, 200)
        self.assertEqual(log.attempts, 1)
        self.assertEqual(log.event, WebhookEvents.ORDER_SHIPPED)

    @patch('apps.webhooks.services.requests.post')
    def test_deliver_failure(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_post.return_value = mock_resp

        sub = self._create_subscriber()
        log = deliver(sub.id, WebhookEvents.ORDER_SHIPPED, {'order': 'WO-001'})

        self.assertFalse(log.success)
        self.assertEqual(log.status_code, 500)

    @patch('apps.webhooks.services.requests.post')
    def test_deliver_connection_error(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError('Connection refused')

        sub = self._create_subscriber()
        log = deliver(sub.id, WebhookEvents.ORDER_SHIPPED, {'order': 'WO-001'})

        self.assertFalse(log.success)
        self.assertIn('Connection refused', log.error_message)

    @patch('apps.webhooks.services.requests.post')
    def test_deliver_hmac_signature(self, mock_post):
        """secret_key → HMAC-SHA256 서명 헤더 포함"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        sub = self._create_subscriber(secret_key='my-secret')
        payload = {'order': 'WO-001'}

        deliver(sub.id, WebhookEvents.ORDER_SHIPPED, payload)

        call_kwargs = mock_post.call_args
        headers = call_kwargs.kwargs.get('headers') or call_kwargs[1].get('headers')

        self.assertIn('X-Webhook-Signature', headers)
        self.assertIn('X-Webhook-Event', headers)
        self.assertEqual(headers['X-Webhook-Event'], WebhookEvents.ORDER_SHIPPED)

        # 서명 검증
        body = json.dumps(payload, ensure_ascii=False, default=str)
        expected_sig = hmac.new(
            b'my-secret', body.encode('utf-8'), hashlib.sha256,
        ).hexdigest()
        self.assertEqual(headers['X-Webhook-Signature'], expected_sig)

    @patch('apps.webhooks.services.requests.post')
    def test_deliver_no_signature_without_secret(self, mock_post):
        """secret_key 없으면 서명 헤더 미포함"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        sub = self._create_subscriber(secret_key='')
        deliver(sub.id, WebhookEvents.ORDER_SHIPPED, {'order': 'WO-001'})

        call_kwargs = mock_post.call_args
        headers = call_kwargs.kwargs.get('headers') or call_kwargs[1].get('headers')
        self.assertNotIn('X-Webhook-Signature', headers)

    def test_deliver_nonexistent_subscriber(self):
        log = deliver(99999, WebhookEvents.ORDER_SHIPPED, {})
        self.assertIsNone(log)

    @patch('apps.webhooks.services.requests.post')
    def test_creates_log_record(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        sub = self._create_subscriber()
        deliver(sub.id, WebhookEvents.ORDER_SHIPPED, {'test': True})

        self.assertEqual(WebhookLog.objects.filter(subscriber=sub).count(), 1)


# ------------------------------------------------------------------
# 구독자 CRUD API 테스트
# ------------------------------------------------------------------

class SubscriberListViewTest(WebhookTestMixin, TestCase):

    def test_list_subscribers(self):
        self._create_subscriber(name='구독자1')
        self._create_subscriber(name='구독자2')

        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/webhooks/subscribers/')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 2)

    def test_create_subscriber(self):
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.post('/api/v1/webhooks/subscribers/', {
            'name': '새 구독자',
            'url': 'https://example.com/hook',
            'events': [WebhookEvents.ORDER_SHIPPED, WebhookEvents.ORDER_CANCELLED],
        }, format='json')

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['name'], '새 구독자')
        self.assertTrue(WebhookSubscriber.objects.filter(name='새 구독자').exists())

    def test_create_validates_events(self):
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.post('/api/v1/webhooks/subscribers/', {
            'name': 'bad',
            'url': 'https://example.com/hook',
            'events': ['INVALID_EVENT'],
        }, format='json')

        self.assertEqual(resp.status_code, 400)

    def test_secret_key_write_only(self):
        """secret_key는 응답에 포함되지 않음"""
        sub = self._create_subscriber(secret_key='my-secret')

        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/webhooks/subscribers/')

        self.assertNotIn('secret_key', resp.data[0])

    def test_permission_denied_for_client(self):
        self.api.force_authenticate(user=self.client_user)
        resp = self.api.get('/api/v1/webhooks/subscribers/')
        self.assertEqual(resp.status_code, 403)


class SubscriberDetailViewTest(WebhookTestMixin, TestCase):

    def test_get_subscriber(self):
        sub = self._create_subscriber()
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get(f'/api/v1/webhooks/subscribers/{sub.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['name'], sub.name)

    def test_update_subscriber(self):
        sub = self._create_subscriber()
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.put(
            f'/api/v1/webhooks/subscribers/{sub.id}/',
            {'name': '변경됨', 'is_active': False},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)

        sub.refresh_from_db()
        self.assertEqual(sub.name, '변경됨')
        self.assertFalse(sub.is_active)

    def test_delete_subscriber(self):
        sub = self._create_subscriber()
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.delete(f'/api/v1/webhooks/subscribers/{sub.id}/')
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(WebhookSubscriber.objects.filter(pk=sub.id).exists())

    def test_not_found(self):
        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/webhooks/subscribers/99999/')
        self.assertEqual(resp.status_code, 404)


class WebhookLogListViewTest(WebhookTestMixin, TestCase):

    @patch('apps.webhooks.services.requests.post')
    def test_list_logs(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        sub = self._create_subscriber()
        deliver(sub.id, WebhookEvents.ORDER_SHIPPED, {'test': True})

        self.api.force_authenticate(user=self.office_user)
        resp = self.api.get('/api/v1/webhooks/logs/')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['event'], WebhookEvents.ORDER_SHIPPED)


# ------------------------------------------------------------------
# waves 출고 연동 테스트
# ------------------------------------------------------------------

class ShipmentWebhookIntegrationTest(TestCase):
    """출고 확정 시 ORDER_SHIPPED 웹훅 발행 확인"""

    def setUp(self):
        self.client_obj = Client.objects.create(
            company_name='테스트', business_number='123-45-67890',
            contact_person='홍', contact_phone='010',
            contact_email='t@t.com', invoice_email='i@t.com',
        )
        self.product = Product.objects.create(
            barcode='SKU-001', name='상품', client=self.client_obj,
        )
        self.loc_storage = Location.objects.create(
            barcode='STOR-01', zone_type='STORAGE',
        )
        self.loc_outbound = Location.objects.create(
            barcode='OUT-01', zone_type='OUTBOUND_STAGING',
        )
        InventoryBalance.objects.create(
            product=self.product, location=self.loc_storage,
            client=self.client_obj, on_hand_qty=100, allocated_qty=10,
        )
        self.office_user = User.objects.create_user(
            email='office@test.com', password='test1234',
            name='오피스', role='office', is_approved=True,
        )

    @patch('apps.webhooks.services.requests.post')
    def test_ship_publishes_order_shipped(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        # 구독자 등록
        sub = WebhookSubscriber.objects.create(
            name='외부 시스템',
            url='https://example.com/webhook',
            events=[WebhookEvents.ORDER_SHIPPED],
        )

        # 주문 → 웨이브 → 출고존 재고 → INSPECTED → 출고
        order = OutboundOrder.objects.create(
            source='TEST', source_order_id='T-001',
            client=self.client_obj, status='ALLOCATED',
            recipient_name='수취인', recipient_phone='010',
            recipient_address='서울', ordered_at=timezone.now(),
        )
        OutboundOrderItem.objects.create(
            order=order, product=self.product, qty=3,
        )
        wave = WaveService.create_wave(
            wave_time='09:00', created_by=self.office_user,
        )

        # 출고존에 재고 배치
        InventoryBalance.objects.update_or_create(
            product=self.product, location=wave.outbound_zone,
            client=self.client_obj,
            defaults={'on_hand_qty': 3},
        )

        order.refresh_from_db()
        order.status = 'INSPECTED'
        order.save(update_fields=['status'])

        ShipmentService.confirm_shipment(
            order=order, tracking_number='TRACK-001',
            performed_by=self.office_user,
        )

        # 웹훅 호출 확인
        self.assertTrue(mock_post.called)
        call_kwargs = mock_post.call_args
        body = json.loads(call_kwargs.kwargs.get('data') or call_kwargs[1].get('data'))
        self.assertEqual(body['wms_order_id'], order.wms_order_id)
        self.assertEqual(body['tracking_number'], 'TRACK-001')

        # 로그 확인
        log = WebhookLog.objects.filter(
            subscriber=sub,
            event=WebhookEvents.ORDER_SHIPPED,
        ).first()
        self.assertIsNotNone(log)
        self.assertTrue(log.success)
