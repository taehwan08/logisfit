"""
운영 알림 이메일 모듈

화주사 대상 일일 출고 요약 이메일을 발송합니다.
"""
import logging

from django.utils import timezone

from apps.accounts.email import send_email

logger = logging.getLogger(__name__)


def send_daily_shipment_summary(client, date=None):
    """화주사에게 일일 출고 요약 이메일 발송

    Args:
        client: Client 인스턴스
        date: 대상 날짜 (기본: 오늘)

    Returns:
        bool: 발송 성공 여부
    """
    from apps.waves.models import OutboundOrder

    if date is None:
        date = timezone.localdate()

    shipped_orders = OutboundOrder.objects.filter(
        client=client,
        status='SHIPPED',
        shipped_at__date=date,
    ).select_related('carrier')

    shipped_count = shipped_orders.count()
    if shipped_count == 0:
        return False

    held_count = OutboundOrder.objects.filter(
        client=client,
        status='HELD',
    ).count()

    # 수신자: 화주사에 소속된 사용자 이메일
    to_emails = list(
        client.users.filter(
            is_active=True, role='client',
        ).values_list('email', flat=True)
    )
    if not to_emails:
        # fallback: 거래처 담당자 이메일
        to_emails = [client.contact_email]

    date_str = date.strftime('%Y-%m-%d')
    subject = f'[LogisFit] 일일 출고 요약 — {client.company_name} ({date_str})'

    # 출고 건별 테이블 행 생성
    order_rows = ''
    for o in shipped_orders[:50]:
        shipped_time = (
            timezone.localtime(o.shipped_at).strftime('%H:%M')
            if o.shipped_at else '-'
        )
        carrier_name = o.carrier.name if o.carrier else '-'
        order_rows += f"""
        <tr>
            <td style="padding:8px 12px; border-bottom:1px solid #e2e8f0; font-size:13px; color:#1e293b;">{o.wms_order_id}</td>
            <td style="padding:8px 12px; border-bottom:1px solid #e2e8f0; font-size:13px; color:#1e293b;">{o.recipient_name}</td>
            <td style="padding:8px 12px; border-bottom:1px solid #e2e8f0; font-size:13px; color:#1e293b;">{carrier_name}</td>
            <td style="padding:8px 12px; border-bottom:1px solid #e2e8f0; font-size:13px; color:#1e293b;">{o.tracking_number or '-'}</td>
            <td style="padding:8px 12px; border-bottom:1px solid #e2e8f0; font-size:13px; color:#1e293b;">{shipped_time}</td>
        </tr>"""

    overflow_note = ''
    if shipped_count > 50:
        overflow_note = f'<p style="margin:8px 0 0; color:#94a3b8; font-size:12px;">...외 {shipped_count - 50}건</p>'

    held_section = ''
    if held_count > 0:
        held_section = f"""
        <div style="background-color:#fef3c7; border:1px solid #f59e0b; border-radius:8px; padding:12px 16px; margin-bottom:24px;">
            <p style="margin:0; color:#92400e; font-size:14px; font-weight:600;">
                보류 중인 주문: {held_count}건
            </p>
            <p style="margin:4px 0 0; color:#92400e; font-size:13px;">
                재고 부족 등의 사유로 보류된 주문이 있습니다.
            </p>
        </div>"""

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin:0; padding:0; background-color:#f4f6f9; font-family:'Noto Sans KR', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f6f9; padding:40px 0;">
            <tr>
                <td align="center">
                    <table width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff; border-radius:12px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.08);">
                        <!-- 헤더 -->
                        <tr>
                            <td style="background-color:#2c3e50; padding:28px 32px; text-align:center;">
                                <h1 style="margin:0; color:#ffffff; font-size:22px; font-weight:700;">LogisFit</h1>
                                <p style="margin:6px 0 0; color:#94a3b8; font-size:13px;">일일 출고 요약</p>
                            </td>
                        </tr>

                        <!-- 본문 -->
                        <tr>
                            <td style="padding:36px 32px 20px;">
                                <h2 style="margin:0 0 8px; color:#1e293b; font-size:18px; font-weight:600;">
                                    {client.company_name} — {date_str} 출고 현황
                                </h2>

                                <!-- 요약 -->
                                <div style="background-color:#f0fdf4; border:1px solid #86efac; border-radius:8px; padding:16px; margin:16px 0 24px; text-align:center;">
                                    <p style="margin:0; color:#166534; font-size:28px; font-weight:700;">{shipped_count}건</p>
                                    <p style="margin:4px 0 0; color:#166534; font-size:14px;">출고 완료</p>
                                </div>

                                {held_section}

                                <!-- 출고 목록 -->
                                <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e2e8f0; border-radius:8px; overflow:hidden;">
                                    <thead>
                                        <tr style="background-color:#f8fafc;">
                                            <th style="padding:10px 12px; text-align:left; font-size:12px; color:#64748b; font-weight:600; border-bottom:2px solid #e2e8f0;">주문번호</th>
                                            <th style="padding:10px 12px; text-align:left; font-size:12px; color:#64748b; font-weight:600; border-bottom:2px solid #e2e8f0;">수취인</th>
                                            <th style="padding:10px 12px; text-align:left; font-size:12px; color:#64748b; font-weight:600; border-bottom:2px solid #e2e8f0;">택배사</th>
                                            <th style="padding:10px 12px; text-align:left; font-size:12px; color:#64748b; font-weight:600; border-bottom:2px solid #e2e8f0;">송장번호</th>
                                            <th style="padding:10px 12px; text-align:left; font-size:12px; color:#64748b; font-weight:600; border-bottom:2px solid #e2e8f0;">출고시각</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {order_rows}
                                    </tbody>
                                </table>
                                {overflow_note}
                            </td>
                        </tr>

                        <!-- 푸터 -->
                        <tr>
                            <td style="padding:20px 32px 28px; border-top:1px solid #f1f5f9;">
                                <p style="margin:0; color:#cbd5e1; font-size:11px; text-align:center;">
                                    &copy; LogisFit. 이 이메일은 자동 발송되었습니다.
                                </p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    return send_email(to_emails, subject, html_content)
