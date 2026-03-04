"""
어댑터 테스트

B2B 엑셀 파서, 사방넷 주문 수집, 송장 역전송 테스트.
"""
import io
from unittest.mock import patch, MagicMock

import openpyxl
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User, SystemConfig
from apps.clients.models import Client
from apps.inventory.models import Product, Location, InventoryBalance
from apps.waves.models import OutboundOrder, OutboundOrderItem
from apps.printing.models import Carrier

from apps.adapters.b2b.excel_parser import B2BExcelParser
from apps.adapters.sabangnet.mappers import map_order, map_carrier_code
from apps.adapters.sabangnet.order_poller import SabangnetOrderPoller
from apps.adapters.sabangnet.invoice_sender import SabangnetInvoiceSender


def _make_excel(rows):
    """테스트용 엑셀 파일 생성"""
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    buf.name = 'test.xlsx'
    return buf


class AdaptersTestMixin:
    """어댑터 테스트 공통 데이터"""

    def setUp(self):
        self.client_obj = Client.objects.create(
            company_name='테스트 거래처',
            business_number='123-45-67890',
            contact_person='홍길동',
            contact_phone='010-1234-5678',
            contact_email='test@test.com',
            invoice_email='invoice@test.com',
        )
        self.product = Product.objects.create(
            barcode='SKU-A001', name='상품A', client=self.client_obj,
        )
        self.product2 = Product.objects.create(
            barcode='SKU-B002', name='상품B', client=self.client_obj,
        )
        self.loc_storage = Location.objects.create(
            barcode='STOR-01', zone_type='STORAGE',
        )

        InventoryBalance.objects.create(
            product=self.product, location=self.loc_storage,
            client=self.client_obj, on_hand_qty=100,
        )
        InventoryBalance.objects.create(
            product=self.product2, location=self.loc_storage,
            client=self.client_obj, on_hand_qty=50,
        )

        self.office_user = User.objects.create_user(
            email='office@test.com', password='test1234',
            name='오피스', role='office', is_approved=True,
        )
        self.client_user = User.objects.create_user(
            email='client@test.com', password='test1234',
            name='거래처유저', role='client', is_approved=True,
        )

        self.api = APIClient()


# ------------------------------------------------------------------
# B2B 엑셀 파서 테스트
# ------------------------------------------------------------------

class B2BExcelParserTest(TestCase):
    """B2BExcelParser.parse() 테스트"""

    def test_parse_basic(self):
        """기본 파싱"""
        file = _make_excel([
            ['발주번호', '상품코드', '수량', '수취인명', '연락처', '배송지'],
            ['B2B-001', 'SKU-A001', 3, '홍길동', '010-0000-0000', '서울'],
        ])
        parser = B2BExcelParser()
        orders = parser.parse(file)

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]['source_order_id'], 'B2B-001')
        self.assertEqual(orders[0]['recipient_name'], '홍길동')
        self.assertEqual(len(orders[0]['items']), 1)
        self.assertEqual(orders[0]['items'][0]['sku'], 'SKU-A001')
        self.assertEqual(orders[0]['items'][0]['qty'], 3)

    def test_group_by_order_id(self):
        """같은 발주번호 → 하나의 주문으로 그룹핑"""
        file = _make_excel([
            ['발주번호', '상품코드', '수량', '수취인명', '연락처', '배송지'],
            ['B2B-001', 'SKU-A001', 3, '홍길동', '010-0000-0000', '서울'],
            ['B2B-001', 'SKU-B002', 2, '홍길동', '010-0000-0000', '서울'],
            ['B2B-002', 'SKU-A001', 1, '김영희', '010-1111-1111', '부산'],
        ])
        parser = B2BExcelParser()
        orders = parser.parse(file)

        self.assertEqual(len(orders), 2)
        order1 = next(o for o in orders if o['source_order_id'] == 'B2B-001')
        self.assertEqual(len(order1['items']), 2)

    def test_missing_required_column(self):
        """필수 컬럼 누락 → ValueError"""
        file = _make_excel([
            ['발주번호', '상품코드'],  # '수량', '수취인명' 등 누락
            ['B2B-001', 'SKU-A001'],
        ])
        parser = B2BExcelParser()
        with self.assertRaises(ValueError) as ctx:
            parser.parse(file)
        self.assertIn('필수 컬럼 누락', str(ctx.exception))

    def test_empty_data(self):
        """데이터 없음 → ValueError"""
        file = _make_excel([
            ['발주번호', '상품코드', '수량', '수취인명', '연락처', '배송지'],
        ])
        parser = B2BExcelParser()
        with self.assertRaises(ValueError) as ctx:
            parser.parse(file)
        self.assertIn('데이터가 없습니다', str(ctx.exception))

    def test_invalid_qty(self):
        """수량 비숫자 → ValueError"""
        file = _make_excel([
            ['발주번호', '상품코드', '수량', '수취인명', '연락처', '배송지'],
            ['B2B-001', 'SKU-A001', 'abc', '홍길동', '010-0000', '서울'],
        ])
        parser = B2BExcelParser()
        with self.assertRaises(ValueError) as ctx:
            parser.parse(file)
        self.assertIn('숫자가 아닙니다', str(ctx.exception))

    def test_optional_columns(self):
        """선택 컬럼 (우편번호, 배송메모) 포함"""
        file = _make_excel([
            ['발주번호', '상품코드', '수량', '수취인명', '연락처', '배송지', '우편번호', '배송메모'],
            ['B2B-001', 'SKU-A001', 3, '홍길동', '010-0000', '서울', '06234', '부재시 문앞'],
        ])
        parser = B2BExcelParser()
        orders = parser.parse(file)

        self.assertEqual(orders[0]['recipient_zip'], '06234')
        self.assertEqual(orders[0]['shipping_memo'], '부재시 문앞')

    def test_skip_empty_rows(self):
        """빈 행 스킵"""
        file = _make_excel([
            ['발주번호', '상품코드', '수량', '수취인명', '연락처', '배송지'],
            ['B2B-001', 'SKU-A001', 3, '홍길동', '010-0000', '서울'],
            [None, None, None, None, None, None],
            ['B2B-002', 'SKU-B002', 1, '김영희', '010-1111', '부산'],
        ])
        parser = B2BExcelParser()
        orders = parser.parse(file)
        self.assertEqual(len(orders), 2)


# ------------------------------------------------------------------
# B2B 업로드 API 테스트
# ------------------------------------------------------------------

class B2BUploadViewTest(AdaptersTestMixin, TestCase):
    """POST /api/v1/adapters/b2b/upload/"""

    def _upload(self, file, client_id=None):
        if client_id is None:
            client_id = self.client_obj.pk
        return self.api.post(
            '/api/v1/adapters/b2b/upload/',
            {'file': file, 'client_id': client_id},
            format='multipart',
        )

    def test_upload_creates_orders(self):
        file = _make_excel([
            ['발주번호', '상품코드', '수량', '수취인명', '연락처', '배송지'],
            ['B2B-001', 'SKU-A001', 3, '홍길동', '010-0000', '서울'],
            ['B2B-002', 'SKU-B002', 2, '김영희', '010-1111', '부산'],
        ])
        self.api.force_authenticate(user=self.office_user)
        resp = self._upload(file)

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['created_count'], 2)
        self.assertEqual(resp.data['total_parsed'], 2)

        # DB 확인
        self.assertEqual(
            OutboundOrder.objects.filter(source='B2B_EXCEL').count(), 2,
        )

    def test_allocated_on_sufficient_stock(self):
        """재고 충분 → ALLOCATED"""
        file = _make_excel([
            ['발주번호', '상품코드', '수량', '수취인명', '연락처', '배송지'],
            ['B2B-001', 'SKU-A001', 3, '홍길동', '010-0000', '서울'],
        ])
        self.api.force_authenticate(user=self.office_user)
        self._upload(file)

        order = OutboundOrder.objects.get(
            source='B2B_EXCEL', source_order_id='B2B-001',
        )
        self.assertEqual(order.status, 'ALLOCATED')
        self.assertEqual(order.order_type, 'B2B')

    def test_held_on_insufficient_stock(self):
        """재고 부족 → HELD"""
        file = _make_excel([
            ['발주번호', '상품코드', '수량', '수취인명', '연락처', '배송지'],
            ['B2B-001', 'SKU-A001', 999, '홍길동', '010-0000', '서울'],
        ])
        self.api.force_authenticate(user=self.office_user)
        self._upload(file)

        order = OutboundOrder.objects.get(
            source='B2B_EXCEL', source_order_id='B2B-001',
        )
        self.assertEqual(order.status, 'HELD')

    def test_duplicate_skipped(self):
        """중복 주문 스킵"""
        OutboundOrder.objects.create(
            source='B2B_EXCEL', source_order_id='B2B-001',
            client=self.client_obj, status='ALLOCATED',
            recipient_name='기존', recipient_phone='010',
            recipient_address='서울', ordered_at=timezone.now(),
        )
        file = _make_excel([
            ['발주번호', '상품코드', '수량', '수취인명', '연락처', '배송지'],
            ['B2B-001', 'SKU-A001', 3, '홍길동', '010-0000', '서울'],
        ])
        self.api.force_authenticate(user=self.office_user)
        resp = self._upload(file)

        self.assertEqual(resp.data['created_count'], 0)
        self.assertEqual(resp.data['skipped_count'], 1)

    def test_invalid_product(self):
        """존재하지 않는 상품코드 → 에러"""
        file = _make_excel([
            ['발주번호', '상품코드', '수량', '수취인명', '연락처', '배송지'],
            ['B2B-001', 'NO-SUCH-SKU', 3, '홍길동', '010-0000', '서울'],
        ])
        self.api.force_authenticate(user=self.office_user)
        resp = self._upload(file)

        self.assertEqual(resp.data['error_count'], 1)
        self.assertIn('상품', resp.data['errors'][0]['error'])

    def test_invalid_client(self):
        file = _make_excel([
            ['발주번호', '상품코드', '수량', '수취인명', '연락처', '배송지'],
            ['B2B-001', 'SKU-A001', 3, '홍길동', '010-0000', '서울'],
        ])
        self.api.force_authenticate(user=self.office_user)
        resp = self._upload(file, client_id=99999)
        self.assertEqual(resp.status_code, 404)

    def test_permission_denied_for_client_role(self):
        file = _make_excel([
            ['발주번호', '상품코드', '수량', '수취인명', '연락처', '배송지'],
            ['B2B-001', 'SKU-A001', 3, '홍길동', '010-0000', '서울'],
        ])
        self.api.force_authenticate(user=self.client_user)
        resp = self._upload(file)
        self.assertEqual(resp.status_code, 403)


# ------------------------------------------------------------------
# 사방넷 매퍼 테스트
# ------------------------------------------------------------------

class SabangnetMapperTest(TestCase):
    """mappers.py 테스트"""

    def test_map_order(self):
        raw = {
            'order_id': 'SB-12345',
            'buyer_name': '홍길동',
            'buyer_phone': '010-0000-0000',
            'buyer_address': '서울 강남구',
            'buyer_zip': '06234',
            'memo': '부재시 문앞',
            'order_date': '2026-03-04T10:00:00',
            'items': [
                {'sku': 'SKU-A001', 'qty': 3, 'item_id': 'ITEM-1'},
                {'sku': 'SKU-B002', 'qty': 2, 'item_id': 'ITEM-2'},
            ],
        }
        result = map_order(raw, client_id=1)

        self.assertEqual(result['source'], 'SABANGNET')
        self.assertEqual(result['source_order_id'], 'SB-12345')
        self.assertEqual(result['client_id'], 1)
        self.assertEqual(result['shipping']['recipient_name'], '홍길동')
        self.assertEqual(len(result['items']), 2)
        self.assertEqual(result['items'][0]['sku'], 'SKU-A001')
        self.assertEqual(result['items'][0]['qty'], 3)

    def test_map_carrier_code(self):
        self.assertEqual(map_carrier_code('CJ대한통운'), 'CJ')
        self.assertEqual(map_carrier_code('한진택배'), 'HANJIN')
        self.assertEqual(map_carrier_code('UNKNOWN'), 'UNKNOWN')


# ------------------------------------------------------------------
# 사방넷 주문 수집 테스트
# ------------------------------------------------------------------

class SabangnetOrderPollerTest(AdaptersTestMixin, TestCase):
    """SabangnetOrderPoller.poll_orders() 테스트"""

    def setUp(self):
        super().setUp()
        SystemConfig.objects.create(
            key='sabangnet_client_id', value=self.client_obj.pk,
        )
        SystemConfig.objects.create(
            key='sabangnet_api_url', value='https://api.sabangnet.test',
        )
        SystemConfig.objects.create(
            key='sabangnet_api_key', value='test-key',
        )
        SystemConfig.objects.create(
            key='sabangnet_company_id', value='COMP-001',
        )

    @patch.object(SabangnetOrderPoller, '__init__', lambda self: None)
    def test_poll_creates_orders(self):
        poller = SabangnetOrderPoller()
        poller.client = MagicMock()
        poller.client.fetch_new_orders.return_value = [
            {
                'order_id': 'SB-001',
                'buyer_name': '홍길동',
                'buyer_phone': '010-0000-0000',
                'buyer_address': '서울',
                'buyer_zip': '',
                'memo': '',
                'order_date': timezone.now().isoformat(),
                'items': [
                    {'sku': 'SKU-A001', 'qty': 3, 'item_id': 'I1'},
                ],
            },
        ]

        result = poller.poll_orders()

        self.assertEqual(result['created'], 1)
        order = OutboundOrder.objects.get(
            source='SABANGNET', source_order_id='SB-001',
        )
        self.assertEqual(order.status, 'ALLOCATED')
        self.assertEqual(order.items.count(), 1)

    @patch.object(SabangnetOrderPoller, '__init__', lambda self: None)
    def test_poll_skips_duplicates(self):
        """이미 존재하는 주문 → 스킵"""
        OutboundOrder.objects.create(
            source='SABANGNET', source_order_id='SB-001',
            client=self.client_obj, status='ALLOCATED',
            recipient_name='기존', recipient_phone='010',
            recipient_address='서울', ordered_at=timezone.now(),
        )

        poller = SabangnetOrderPoller()
        poller.client = MagicMock()
        poller.client.fetch_new_orders.return_value = [
            {
                'order_id': 'SB-001',
                'buyer_name': '홍길동',
                'buyer_phone': '010',
                'buyer_address': '서울',
                'buyer_zip': '',
                'memo': '',
                'order_date': timezone.now().isoformat(),
                'items': [{'sku': 'SKU-A001', 'qty': 1, 'item_id': ''}],
            },
        ]

        result = poller.poll_orders()
        self.assertEqual(result['skipped'], 1)
        self.assertEqual(result['created'], 0)

    def test_poll_no_client_id_config(self):
        """sabangnet_client_id 미설정"""
        SystemConfig.objects.filter(key='sabangnet_client_id').delete()

        poller = SabangnetOrderPoller()
        result = poller.poll_orders()
        self.assertIn('error', result)


# ------------------------------------------------------------------
# 사방넷 송장 역전송 테스트
# ------------------------------------------------------------------

class SabangnetInvoiceSenderTest(AdaptersTestMixin, TestCase):
    """SabangnetInvoiceSender.send_invoice() 테스트"""

    def _make_shipped_order(self, source='SABANGNET'):
        carrier = Carrier.objects.create(name='CJ대한통운', code='CJ')
        order = OutboundOrder.objects.create(
            source=source, source_order_id='SB-001',
            client=self.client_obj, status='SHIPPED',
            recipient_name='홍길동', recipient_phone='010',
            recipient_address='서울', ordered_at=timezone.now(),
            tracking_number='TRACK-123', carrier=carrier,
        )
        return order

    @patch('apps.adapters.sabangnet.invoice_sender.SabangnetClient')
    def test_send_invoice_success(self, MockClient):
        mock_client = MockClient.return_value
        mock_client.register_invoice.return_value = True

        order = self._make_shipped_order()
        sender = SabangnetInvoiceSender()
        sender.client = mock_client

        result = sender.send_invoice(order)

        self.assertTrue(result)
        mock_client.register_invoice.assert_called_once_with(
            source_order_id='SB-001',
            tracking_number='TRACK-123',
            carrier_code='CJ',
        )

    def test_skip_non_sabangnet_order(self):
        """사방넷 주문이 아니면 스킵"""
        order = self._make_shipped_order(source='OTHER')
        sender = SabangnetInvoiceSender()
        result = sender.send_invoice(order)
        self.assertFalse(result)

    def test_skip_no_tracking_number(self):
        """송장번호 없으면 스킵"""
        order = self._make_shipped_order()
        order.tracking_number = ''
        order.save(update_fields=['tracking_number'])

        sender = SabangnetInvoiceSender()
        result = sender.send_invoice(order)
        self.assertFalse(result)
