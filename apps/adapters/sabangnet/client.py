"""
사방넷 REST API 클라이언트

SystemConfig에서 인증정보를 조회하여 사방넷 API를 호출합니다.
"""
import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from apps.accounts.models import get_config

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30  # 초


class SabangnetClient:
    """사방넷 REST API 클라이언트"""

    def __init__(self):
        self.api_url = get_config('sabangnet_api_url', '')
        self.api_key = get_config('sabangnet_api_key', '')
        self.company_id = get_config('sabangnet_company_id', '')
        self.session = self._build_session()

    def _build_session(self):
        """리트라이 설정된 HTTP 세션 생성"""
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    def _headers(self):
        return {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
        }

    def fetch_new_orders(self, from_date, to_date):
        """신규 주문 조회

        Args:
            from_date: 조회 시작일 (YYYY-MM-DD)
            to_date: 조회 종료일 (YYYY-MM-DD)

        Returns:
            list[dict]: 사방넷 주문 데이터 리스트
        """
        if not self.api_url:
            logger.warning('sabangnet_api_url 미설정')
            return []

        # TODO: 실제 사방넷 API 스펙에 맞게 구현
        # 사방넷 API 문서에 따라 엔드포인트, 파라미터, 페이징 처리 필요
        endpoint = f'{self.api_url}/api/orders'
        params = {
            'company_id': self.company_id,
            'from_date': from_date,
            'to_date': to_date,
            'status': 'NEW',
        }

        try:
            resp = self.session.get(
                endpoint,
                headers=self._headers(),
                params=params,
                timeout=DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            orders = data.get('orders', [])
            logger.info('사방넷 주문 %d건 조회', len(orders))
            return orders
        except requests.RequestException as e:
            logger.error('사방넷 주문 조회 실패: %s', e)
            return []

    def register_invoice(self, source_order_id, tracking_number, carrier_code):
        """송장 등록 (역전송)

        Args:
            source_order_id: 사방넷 주문번호
            tracking_number: 송장번호
            carrier_code: 택배사 코드

        Returns:
            bool: 성공 여부
        """
        if not self.api_url:
            logger.warning('sabangnet_api_url 미설정')
            return False

        # TODO: 실제 사방넷 API 스펙에 맞게 구현
        endpoint = f'{self.api_url}/api/invoices'
        payload = {
            'company_id': self.company_id,
            'order_id': source_order_id,
            'tracking_number': tracking_number,
            'carrier_code': carrier_code,
        }

        try:
            resp = self.session.post(
                endpoint,
                headers=self._headers(),
                json=payload,
                timeout=DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
            logger.info(
                '사방넷 송장 등록 성공: order=%s tracking=%s',
                source_order_id, tracking_number,
            )
            return True
        except requests.RequestException as e:
            logger.error(
                '사방넷 송장 등록 실패: order=%s error=%s',
                source_order_id, e,
            )
            return False
