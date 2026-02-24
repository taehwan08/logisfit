"""
이메일 발송 유틸 모듈

Resend API를 사용하여 이메일을 발송합니다.
RESEND_API_KEY가 설정되지 않으면 콘솔 로그로 fallback합니다.
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def send_email(to, subject, html_content):
    """
    Resend API를 통해 이메일을 발송합니다.

    Args:
        to: 수신자 이메일 주소 (str 또는 list)
        subject: 이메일 제목
        html_content: HTML 본문

    Returns:
        bool: 발송 성공 여부
    """
    api_key = getattr(settings, 'RESEND_API_KEY', '')
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@logisfit.co.kr')

    if not api_key:
        logger.warning(
            '[이메일 발송 스킵] RESEND_API_KEY 미설정\n'
            '  TO: %s\n  SUBJECT: %s\n  BODY:\n%s',
            to, subject, html_content,
        )
        return True  # 개발환경에서는 성공으로 처리

    try:
        import resend
        resend.api_key = api_key

        if isinstance(to, str):
            to = [to]

        params = {
            "from": from_email,
            "to": to,
            "subject": subject,
            "html": html_content,
        }

        logger.info('이메일 발송 시도: from=%s, to=%s, subject=%s', from_email, to, subject)
        result = resend.Emails.send(params)
        email_id = result.get('id', '') if isinstance(result, dict) else getattr(result, 'id', '')
        logger.info('이메일 발송 성공: to=%s, subject=%s, id=%s', to, subject, email_id)
        return True

    except Exception as e:
        logger.error('이메일 발송 실패: from=%s, to=%s, subject=%s, error=%s', from_email, to, subject, e, exc_info=True)
        return False


def send_password_reset_code(email, code):
    """
    비밀번호 리셋 인증번호 이메일을 발송합니다.

    Args:
        email: 수신자 이메일
        code: 6자리 인증번호

    Returns:
        bool: 발송 성공 여부
    """
    expiry_minutes = getattr(settings, 'PASSWORD_RESET_CODE_EXPIRY_MINUTES', 10)

    subject = f'[LogisFit] 비밀번호 재설정 인증번호: {code}'

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
                    <table width="460" cellpadding="0" cellspacing="0" style="background-color:#ffffff; border-radius:12px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.08);">
                        <!-- 헤더 -->
                        <tr>
                            <td style="background-color:#2c3e50; padding:28px 32px; text-align:center;">
                                <h1 style="margin:0; color:#ffffff; font-size:22px; font-weight:700; letter-spacing:-0.3px;">LogisFit</h1>
                                <p style="margin:6px 0 0; color:#94a3b8; font-size:13px;">3PL 물류 관리 시스템</p>
                            </td>
                        </tr>

                        <!-- 본문 -->
                        <tr>
                            <td style="padding:36px 32px 20px;">
                                <h2 style="margin:0 0 8px; color:#1e293b; font-size:18px; font-weight:600;">비밀번호 재설정</h2>
                                <p style="margin:0 0 24px; color:#64748b; font-size:14px; line-height:1.6;">
                                    아래 인증번호를 입력하여 비밀번호를 재설정하세요.
                                </p>

                                <!-- 인증번호 -->
                                <div style="background-color:#f8fafc; border:2px solid #e2e8f0; border-radius:10px; padding:24px; text-align:center; margin-bottom:24px;">
                                    <p style="margin:0 0 8px; color:#64748b; font-size:12px; font-weight:600; text-transform:uppercase; letter-spacing:1px;">인증번호</p>
                                    <p style="margin:0; color:#1e293b; font-size:36px; font-weight:800; letter-spacing:8px; font-family:monospace;">{code}</p>
                                </div>

                                <p style="margin:0; color:#94a3b8; font-size:13px; line-height:1.5;">
                                    이 인증번호는 <strong style="color:#e74c3c;">{expiry_minutes}분</strong> 동안 유효합니다.<br>
                                    본인이 요청하지 않은 경우 이 이메일을 무시하세요.
                                </p>
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

    return send_email(email, subject, html_content)


def send_shipment_notification(order):
    """
    출고 완료 알림 이메일을 등록자에게 발송합니다.

    Args:
        order: FulfillmentOrder 인스턴스

    Returns:
        bool: 발송 성공 여부 (등록자 없거나 이메일 없으면 False)
    """
    if not order.created_by:
        logger.warning('출고 알림 발송 스킵: 등록자(created_by) 없음 (주문 #%s)', order.order_number)
        return False
    if not order.created_by.email:
        logger.warning('출고 알림 발송 스킵: 등록자 이메일 없음 (주문 #%s, 등록자=%s)', order.order_number, order.created_by.name)
        return False

    to_email = order.created_by.email
    platform_display = order.get_platform_display()
    shipped_at = order.shipped_at.strftime('%Y-%m-%d %H:%M') if order.shipped_at else '-'
    shipped_by_name = order.shipped_by.name if order.shipped_by else '-'
    client_name = order.client.name if order.client else '-'

    subject = f'[LogisFit] 출고완료 알림 - {order.order_number}'

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
                    <table width="520" cellpadding="0" cellspacing="0" style="background-color:#ffffff; border-radius:12px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.08);">
                        <!-- 헤더 -->
                        <tr>
                            <td style="background-color:#2c3e50; padding:28px 32px; text-align:center;">
                                <h1 style="margin:0; color:#ffffff; font-size:22px; font-weight:700; letter-spacing:-0.3px;">LogisFit</h1>
                                <p style="margin:6px 0 0; color:#94a3b8; font-size:13px;">3PL 물류 관리 시스템</p>
                            </td>
                        </tr>

                        <!-- 본문 -->
                        <tr>
                            <td style="padding:36px 32px 20px;">
                                <div style="display:inline-block; background-color:#d1fae5; color:#065f46; font-size:13px; font-weight:600; padding:4px 12px; border-radius:20px; margin-bottom:16px;">
                                    &#10004; 출고완료
                                </div>
                                <h2 style="margin:0 0 8px; color:#1e293b; font-size:18px; font-weight:600;">출고 완료 알림</h2>
                                <p style="margin:0 0 24px; color:#64748b; font-size:14px; line-height:1.6;">
                                    등록하신 출고 주문이 출고 완료 처리되었습니다.
                                </p>

                                <!-- 주문 정보 테이블 -->
                                <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; overflow:hidden; margin-bottom:24px;">
                                    <tr>
                                        <td style="padding:12px 16px; color:#64748b; font-size:13px; font-weight:600; border-bottom:1px solid #e2e8f0; width:120px;">발주번호</td>
                                        <td style="padding:12px 16px; color:#1e293b; font-size:14px; font-weight:500; border-bottom:1px solid #e2e8f0;">{order.order_number}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding:12px 16px; color:#64748b; font-size:13px; font-weight:600; border-bottom:1px solid #e2e8f0; width:120px;">거래처</td>
                                        <td style="padding:12px 16px; color:#1e293b; font-size:14px; border-bottom:1px solid #e2e8f0;">{client_name}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding:12px 16px; color:#64748b; font-size:13px; font-weight:600; border-bottom:1px solid #e2e8f0; width:120px;">플랫폼</td>
                                        <td style="padding:12px 16px; color:#1e293b; font-size:14px; border-bottom:1px solid #e2e8f0;">{platform_display}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding:12px 16px; color:#64748b; font-size:13px; font-weight:600; border-bottom:1px solid #e2e8f0; width:120px;">상품명</td>
                                        <td style="padding:12px 16px; color:#1e293b; font-size:14px; border-bottom:1px solid #e2e8f0;">{order.product_name}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding:12px 16px; color:#64748b; font-size:13px; font-weight:600; border-bottom:1px solid #e2e8f0; width:120px;">발주수량</td>
                                        <td style="padding:12px 16px; color:#1e293b; font-size:14px; border-bottom:1px solid #e2e8f0;">{order.order_quantity:,}개</td>
                                    </tr>
                                    <tr>
                                        <td style="padding:12px 16px; color:#64748b; font-size:13px; font-weight:600; border-bottom:1px solid #e2e8f0; width:120px;">확정수량</td>
                                        <td style="padding:12px 16px; color:#1e293b; font-size:14px; border-bottom:1px solid #e2e8f0;">{order.confirmed_quantity:,}개</td>
                                    </tr>
                                    <tr>
                                        <td style="padding:12px 16px; color:#64748b; font-size:13px; font-weight:600; width:120px;">출고일시</td>
                                        <td style="padding:12px 16px; color:#1e293b; font-size:14px;">{shipped_at}</td>
                                    </tr>
                                </table>

                                <p style="margin:0; color:#94a3b8; font-size:13px; line-height:1.5;">
                                    출고처리자: <strong style="color:#475569;">{shipped_by_name}</strong>
                                </p>
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

    return send_email(to_email, subject, html_content)
