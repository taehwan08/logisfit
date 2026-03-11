"""
일일택배사업부 리포트 서비스

사방넷 출고 엑셀 파일을 업로드하면 브랜드별 단포/합포 출고건수를 집계한다.
pandas 미사용 — openpyxl(.xlsx) + xlrd(.xls) 만 사용.
"""
import os
from collections import defaultdict
from io import BytesIO

import openpyxl
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
import xlrd


def _read_rows_xlsx(uploaded_file):
    """xlsx 파일에서 데이터 행을 읽어 리스트로 반환 (헤더 제외)"""
    wb = openpyxl.load_workbook(uploaded_file, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        raise ValueError('엑셀 파일이 비어 있습니다.')
    return rows[0], rows[1:]  # header, data_rows


def _read_rows_xls(uploaded_file):
    """xls 파일에서 데이터 행을 읽어 리스트로 반환 (헤더 제외)"""
    content = uploaded_file.read()
    wb = xlrd.open_workbook(file_contents=content)
    ws = wb.sheet_by_index(0)
    if ws.nrows == 0:
        raise ValueError('엑셀 파일이 비어 있습니다.')
    header = [ws.cell_value(0, c) for c in range(ws.ncols)]
    data_rows = []
    for r in range(1, ws.nrows):
        data_rows.append(tuple(ws.cell_value(r, c) for c in range(ws.ncols)))
    return header, data_rows


def process_daily_parcel_report(uploaded_file) -> BytesIO:
    """
    업로드된 엑셀 파일을 받아 브랜드별 단포/합포 집계 엑셀을 BytesIO로 반환

    Args:
        uploaded_file: Django UploadedFile (.xls 또는 .xlsx)

    Returns:
        BytesIO: 집계 결과 엑셀 파일
    """
    # 1. 파일 확장자 판별 후 읽기
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext == '.xls':
        header, data_rows = _read_rows_xls(uploaded_file)
    else:
        header, data_rows = _read_rows_xlsx(uploaded_file)

    # 2. 컬럼 수 검증 (BM=64, BN=65 인덱스)
    num_cols = len(header)
    if num_cols < 66:
        raise ValueError(
            f'컬럼 수가 부족합니다. (필요: 66개 이상, 현재: {num_cols}개)\n'
            '사방넷 출고 데이터 엑셀 파일인지 확인해주세요.'
        )

    # 3. 브랜드별 단포/합포 집계
    counts = defaultdict(lambda: {'단포': 0, '합포': 0})

    for row in data_rows:
        if len(row) < 66:
            continue

        brand = str(row[64]).strip() if row[64] is not None else ''
        memo = str(row[65]).strip() if row[65] is not None else ''

        if not brand:
            continue

        pack_type = '합포' if '합' in memo else '단포'
        counts[brand][pack_type] += 1

    if not counts:
        raise ValueError('집계할 데이터가 없습니다. 파일 내용을 확인해주세요.')

    brands = sorted(counts.keys())

    # 4. openpyxl로 엑셀 생성 (스타일 포함)
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
    for col_idx, col_header in enumerate(['브랜드', '포장구분', '출고건수'], 1):
        cell = ws.cell(row=1, column=col_idx, value=col_header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border

    # 데이터 행
    row_num = 2
    for brand in brands:
        for i, pack_type in enumerate(['단포', '합포']):
            count = counts[brand][pack_type]

            # 브랜드명: 단포 행에만 표시
            c1 = ws.cell(row=row_num, column=1, value=brand if i == 0 else '')
            c1.font = bold_font if i == 0 else normal_font
            c1.alignment = left_align
            c1.border = thin_border

            c2 = ws.cell(row=row_num, column=2, value=pack_type)
            c2.font = normal_font
            c2.alignment = center_align
            c2.border = thin_border

            c3 = ws.cell(row=row_num, column=3, value=count)
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
