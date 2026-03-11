"""
일일택배사업부 리포트 서비스

사방넷 출고 엑셀 파일을 업로드하면 브랜드별 단포/합포 출고건수를 집계한다.
"""
import pandas as pd
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill


def process_daily_parcel_report(uploaded_file) -> BytesIO:
    """
    업로드된 엑셀 파일을 받아 브랜드별 단포/합포 집계 엑셀을 BytesIO로 반환

    Args:
        uploaded_file: Django UploadedFile (.xls 또는 .xlsx)

    Returns:
        BytesIO: 집계 결과 엑셀 파일
    """
    # 1. 파일 읽기 (.xls와 .xlsx 모두 지원)
    df = pd.read_excel(uploaded_file, header=0)

    # 2. 컬럼 추출 (BM=64, BN=65 인덱스)
    if len(df.columns) < 66:
        raise ValueError(
            f'컬럼 수가 부족합니다. (필요: 66개 이상, 현재: {len(df.columns)}개)\n'
            '사방넷 출고 데이터 엑셀 파일인지 확인해주세요.'
        )

    col_brand = df.columns[64]  # 출력양식명 = 브랜드
    col_check = df.columns[65]  # 출력메모 = 합포 판별

    # 3. 단포/합포 판별
    df['포장구분'] = df[col_check].astype(str).apply(
        lambda x: '합포' if '합' in x else '단포'
    )

    # 4. 브랜드별 집계
    summary = df.groupby([col_brand, '포장구분']).size().reset_index(name='출고건수')
    summary = summary.rename(columns={col_brand: '브랜드'})
    brands = sorted(summary['브랜드'].unique(), key=str)

    # 5. 모든 브랜드에 단포/합포 둘 다 보장 (없으면 0)
    full_index = pd.MultiIndex.from_product(
        [brands, ['단포', '합포']], names=['브랜드', '포장구분']
    )
    summary = (
        summary
        .set_index(['브랜드', '포장구분'])
        .reindex(full_index, fill_value=0)
        .reset_index()
    )

    # 6. openpyxl로 엑셀 생성 (스타일 포함)
    wb = Workbook()
    ws = wb.active
    ws.title = '일일택배사업부'

    # 스타일 정의
    header_font = Font(name='Arial', bold=True, size=11, color='FFFFFF')
    header_fill = PatternFill('solid', fgColor='4472C4')
    header_align = Alignment(horizontal='center', vertical='center')
    normal_font = Font(name='Arial', size=10)
    bold_font = Font(name='Arial', bold=True, size=10)
    center_align = Alignment(horizontal='center', vertical='center')
    left_align = Alignment(horizontal='left', vertical='center')
    number_align = Alignment(horizontal='right', vertical='center')
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin'),
    )

    # 헤더 행
    for col_idx, header in enumerate(['브랜드', '포장구분', '출고건수'], 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border

    # 데이터 행
    row_num = 2
    for brand in brands:
        for i, pack_type in enumerate(['단포', '합포']):
            count = summary.loc[
                (summary['브랜드'] == brand) & (summary['포장구분'] == pack_type),
                '출고건수'
            ].values[0]

            # 브랜드명: 단포 행에만 표시
            c1 = ws.cell(row=row_num, column=1, value=str(brand) if i == 0 else '')
            c1.font = bold_font if i == 0 else normal_font
            c1.alignment = left_align
            c1.border = thin_border

            c2 = ws.cell(row=row_num, column=2, value=pack_type)
            c2.font = normal_font
            c2.alignment = center_align
            c2.border = thin_border

            c3 = ws.cell(row=row_num, column=3, value=int(count))
            c3.font = normal_font
            c3.alignment = number_align
            c3.number_format = '#,##0'
            c3.border = thin_border

            row_num += 1

    # 열 너비 / 틀 고정
    ws.column_dimensions['A'].width = 22
    ws.column_dimensions['B'].width = 12
    ws.column_dimensions['C'].width = 12
    ws.freeze_panes = 'A2'

    # BytesIO로 반환
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output
