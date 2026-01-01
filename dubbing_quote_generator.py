#!/usr/bin/env python3
"""
AI Dubbing Quote Generator
AI 더빙 견적서 자동 생성기

분당 단가:
- 국내: 영화 4만원, 드라마/예능 3만원, 다큐/팟캐스트/vlog/교육 2만원
- 글로벌: 영화 $30, 드라마/예능 $20, 다큐/팟캐스트/vlog/교육 $15

할인:
- ME 파일 제공: 10%
- 번역 대본/자막 제공: 10%
- 50편 이상: 20%

턴어라운드:
- 기본: 주 3편
- 급행(주 10편): 2배 가격
"""

import os
import sys
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

# Excel/PDF 라이브러리 임포트
try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
    from openpyxl.utils import get_column_letter
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False
    print("Warning: openpyxl not installed. Run: pip install openpyxl")

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    print("Warning: reportlab not installed. Run: pip install reportlab")


class Genre(Enum):
    """콘텐츠 장르"""
    MOVIE = "영화"
    DRAMA_VARIETY = "드라마/예능"
    DOCUMENTARY = "다큐멘터리"
    PODCAST = "팟캐스트"
    VLOG = "1인 Vlog"
    EDUCATION = "교육 컨텐츠"


class Currency(Enum):
    """통화"""
    KRW = "KRW"
    USD = "USD"


class TurnaroundType(Enum):
    """턴어라운드 타입"""
    STANDARD = "standard"  # 주 3편
    EXPRESS = "express"    # 주 10편 (2배 가격)


# 분당 단가 설정
PRICES = {
    Currency.KRW: {
        Genre.MOVIE: 40000,
        Genre.DRAMA_VARIETY: 30000,
        Genre.DOCUMENTARY: 20000,
        Genre.PODCAST: 20000,
        Genre.VLOG: 20000,
        Genre.EDUCATION: 20000,
    },
    Currency.USD: {
        Genre.MOVIE: 30,
        Genre.DRAMA_VARIETY: 20,
        Genre.DOCUMENTARY: 15,
        Genre.PODCAST: 15,
        Genre.VLOG: 15,
        Genre.EDUCATION: 15,
    }
}

# 1편 = 60분
MINUTES_PER_EPISODE = 60

# 할인율
DISCOUNT_ME_FILE = 0.10      # ME 파일 제공 시 10%
DISCOUNT_SCRIPT = 0.10       # 번역 대본/자막 제공 시 10%
DISCOUNT_BULK = 0.20         # 50편 이상 시 20%
BULK_THRESHOLD = 50          # 대량 주문 기준

# 급행 배율
EXPRESS_MULTIPLIER = 2.0

# 주당 제작 편수
STANDARD_EPISODES_PER_WEEK = 3
EXPRESS_EPISODES_PER_WEEK = 10


@dataclass
class QuoteRequest:
    """견적 요청 정보"""
    client_name: str
    project_name: str
    genre: Genre
    currency: Currency
    episode_count: int
    minutes_per_episode: int = MINUTES_PER_EPISODE
    has_me_file: bool = False
    has_script: bool = False
    turnaround: TurnaroundType = TurnaroundType.STANDARD
    contact_email: str = ""
    notes: str = ""


@dataclass
class QuoteResult:
    """견적 결과"""
    request: QuoteRequest
    base_price_per_minute: float = 0
    total_minutes: int = 0
    base_total: float = 0
    me_discount: float = 0
    script_discount: float = 0
    bulk_discount: float = 0
    express_surcharge: float = 0
    final_total: float = 0
    estimated_weeks: int = 0
    created_at: datetime = field(default_factory=datetime.now)

    def calculate(self):
        """견적 계산"""
        req = self.request

        # 분당 단가
        self.base_price_per_minute = PRICES[req.currency][req.genre]

        # 총 분수
        self.total_minutes = req.episode_count * req.minutes_per_episode

        # 기본 총액
        self.base_total = self.base_price_per_minute * self.total_minutes

        # 할인 계산 (기본 총액 기준)
        discount_total = 0

        if req.has_me_file:
            self.me_discount = self.base_total * DISCOUNT_ME_FILE
            discount_total += self.me_discount

        if req.has_script:
            self.script_discount = self.base_total * DISCOUNT_SCRIPT
            discount_total += self.script_discount

        if req.episode_count >= BULK_THRESHOLD:
            self.bulk_discount = self.base_total * DISCOUNT_BULK
            discount_total += self.bulk_discount

        # 할인 적용된 금액
        discounted_total = self.base_total - discount_total

        # 급행 추가 요금
        if req.turnaround == TurnaroundType.EXPRESS:
            self.express_surcharge = discounted_total  # 2배이므로 원래 금액만큼 추가
            discounted_total *= EXPRESS_MULTIPLIER

        self.final_total = discounted_total

        # 예상 소요 기간
        eps_per_week = (EXPRESS_EPISODES_PER_WEEK
                       if req.turnaround == TurnaroundType.EXPRESS
                       else STANDARD_EPISODES_PER_WEEK)
        self.estimated_weeks = (req.episode_count + eps_per_week - 1) // eps_per_week

        return self


def format_currency(amount: float, currency: Currency) -> str:
    """통화 포맷팅"""
    if currency == Currency.KRW:
        return f"₩{amount:,.0f}"
    else:
        return f"${amount:,.2f}"


def generate_quote_text(result: QuoteResult) -> str:
    """견적서 텍스트 생성"""
    req = result.request
    curr = req.currency

    lines = []
    lines.append("=" * 60)
    lines.append("              AI DUBBING QUOTE / AI 더빙 견적서")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"견적일 / Quote Date: {result.created_at.strftime('%Y-%m-%d')}")
    lines.append(f"유효기간 / Valid Until: {(result.created_at + timedelta(days=30)).strftime('%Y-%m-%d')}")
    lines.append("")
    lines.append("-" * 60)
    lines.append("고객 정보 / Client Information")
    lines.append("-" * 60)
    lines.append(f"고객명 / Client: {req.client_name}")
    lines.append(f"프로젝트 / Project: {req.project_name}")
    if req.contact_email:
        lines.append(f"이메일 / Email: {req.contact_email}")
    lines.append("")
    lines.append("-" * 60)
    lines.append("프로젝트 상세 / Project Details")
    lines.append("-" * 60)
    lines.append(f"장르 / Genre: {req.genre.value}")
    lines.append(f"편수 / Episodes: {req.episode_count}편")
    lines.append(f"편당 분량 / Minutes per Episode: {req.minutes_per_episode}분")
    lines.append(f"총 분량 / Total Minutes: {result.total_minutes}분")
    lines.append("")
    lines.append(f"ME 파일 제공 / ME File Provided: {'예/Yes' if req.has_me_file else '아니오/No'}")
    lines.append(f"번역 대본 제공 / Script Provided: {'예/Yes' if req.has_script else '아니오/No'}")
    lines.append(f"제작 속도 / Turnaround: {'급행 (주 10편) / Express (10 eps/week)' if req.turnaround == TurnaroundType.EXPRESS else '표준 (주 3편) / Standard (3 eps/week)'}")
    lines.append("")
    lines.append("-" * 60)
    lines.append("견적 내역 / Quote Breakdown")
    lines.append("-" * 60)
    lines.append(f"분당 단가 / Rate per Minute: {format_currency(result.base_price_per_minute, curr)}")
    lines.append(f"기본 금액 / Base Total: {format_currency(result.base_total, curr)}")
    lines.append("")

    # 할인 내역
    if result.me_discount > 0 or result.script_discount > 0 or result.bulk_discount > 0:
        lines.append("할인 내역 / Discounts:")
        if result.me_discount > 0:
            lines.append(f"  - ME 파일 제공 할인 (10%): -{format_currency(result.me_discount, curr)}")
        if result.script_discount > 0:
            lines.append(f"  - 번역 대본 제공 할인 (10%): -{format_currency(result.script_discount, curr)}")
        if result.bulk_discount > 0:
            lines.append(f"  - 대량 주문 할인 (20%): -{format_currency(result.bulk_discount, curr)}")
        lines.append("")

    # 급행 추가 요금
    if result.express_surcharge > 0:
        lines.append("추가 요금 / Surcharges:")
        lines.append(f"  - 급행 제작 (x2): +{format_currency(result.express_surcharge, curr)}")
        lines.append("")

    lines.append("-" * 60)
    lines.append(f"최종 견적 금액 / FINAL TOTAL: {format_currency(result.final_total, curr)}")
    lines.append("-" * 60)
    lines.append("")
    lines.append(f"예상 제작 기간 / Estimated Duration: {result.estimated_weeks}주 / {result.estimated_weeks} weeks")
    lines.append("")

    if req.notes:
        lines.append("-" * 60)
        lines.append("비고 / Notes:")
        lines.append(req.notes)
        lines.append("")

    lines.append("=" * 60)
    lines.append("감사합니다. / Thank you for your inquiry.")
    lines.append("=" * 60)

    return "\n".join(lines)


def generate_excel(result: QuoteResult, filename: str) -> bool:
    """Excel 파일 생성"""
    if not EXCEL_AVAILABLE:
        print("Error: openpyxl is not installed")
        return False

    req = result.request
    curr = req.currency
    wb = Workbook()
    ws = wb.active
    ws.title = "Quote"

    # 스타일 정의
    header_font = Font(bold=True, size=16)
    section_font = Font(bold=True, size=12)
    bold_font = Font(bold=True)
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font_white = Font(bold=True, color="FFFFFF")
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    row = 1

    # 제목
    ws.merge_cells('A1:D1')
    ws['A1'] = "AI DUBBING QUOTE / AI 더빙 견적서"
    ws['A1'].font = header_font
    ws['A1'].alignment = Alignment(horizontal='center')
    row += 2

    # 견적 정보
    ws[f'A{row}'] = "견적일 / Quote Date:"
    ws[f'B{row}'] = result.created_at.strftime('%Y-%m-%d')
    row += 1
    ws[f'A{row}'] = "유효기간 / Valid Until:"
    ws[f'B{row}'] = (result.created_at + timedelta(days=30)).strftime('%Y-%m-%d')
    row += 2

    # 고객 정보 섹션
    ws[f'A{row}'] = "고객 정보 / Client Information"
    ws[f'A{row}'].font = section_font
    ws.merge_cells(f'A{row}:D{row}')
    row += 1

    ws[f'A{row}'] = "고객명 / Client"
    ws[f'B{row}'] = req.client_name
    row += 1
    ws[f'A{row}'] = "프로젝트 / Project"
    ws[f'B{row}'] = req.project_name
    row += 1
    if req.contact_email:
        ws[f'A{row}'] = "이메일 / Email"
        ws[f'B{row}'] = req.contact_email
        row += 1
    row += 1

    # 프로젝트 상세 섹션
    ws[f'A{row}'] = "프로젝트 상세 / Project Details"
    ws[f'A{row}'].font = section_font
    ws.merge_cells(f'A{row}:D{row}')
    row += 1

    details = [
        ("장르 / Genre", req.genre.value),
        ("편수 / Episodes", f"{req.episode_count}편"),
        ("편당 분량 / Min per Episode", f"{req.minutes_per_episode}분"),
        ("총 분량 / Total Minutes", f"{result.total_minutes}분"),
        ("ME 파일 제공 / ME File", "예/Yes" if req.has_me_file else "아니오/No"),
        ("번역 대본 제공 / Script", "예/Yes" if req.has_script else "아니오/No"),
        ("제작 속도 / Turnaround", "급행/Express" if req.turnaround == TurnaroundType.EXPRESS else "표준/Standard"),
    ]

    for label, value in details:
        ws[f'A{row}'] = label
        ws[f'B{row}'] = value
        row += 1
    row += 1

    # 견적 내역 섹션
    ws[f'A{row}'] = "견적 내역 / Quote Breakdown"
    ws[f'A{row}'].font = section_font
    ws.merge_cells(f'A{row}:D{row}')
    row += 1

    # 테이블 헤더
    headers = ["항목 / Item", "내용 / Details", "금액 / Amount"]
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=row, column=col, value=header)
        cell.font = header_font_white
        cell.fill = header_fill
        cell.border = thin_border
        cell.alignment = Alignment(horizontal='center')
    row += 1

    # 기본 금액
    items = [
        ("분당 단가 / Rate per Min", f"{result.total_minutes}분 × {format_currency(result.base_price_per_minute, curr)}", format_currency(result.base_total, curr)),
    ]

    # 할인
    if result.me_discount > 0:
        items.append(("ME 파일 할인 / ME Discount", "10%", f"-{format_currency(result.me_discount, curr)}"))
    if result.script_discount > 0:
        items.append(("대본 할인 / Script Discount", "10%", f"-{format_currency(result.script_discount, curr)}"))
    if result.bulk_discount > 0:
        items.append(("대량 할인 / Bulk Discount", "20%", f"-{format_currency(result.bulk_discount, curr)}"))

    # 급행
    if result.express_surcharge > 0:
        items.append(("급행 추가 / Express Surcharge", "x2", f"+{format_currency(result.express_surcharge, curr)}"))

    for item in items:
        for col, value in enumerate(item, 1):
            cell = ws.cell(row=row, column=col, value=value)
            cell.border = thin_border
        row += 1

    # 최종 금액
    ws[f'A{row}'] = "최종 금액 / FINAL TOTAL"
    ws[f'A{row}'].font = bold_font
    ws.merge_cells(f'A{row}:B{row}')
    ws[f'C{row}'] = format_currency(result.final_total, curr)
    ws[f'C{row}'].font = bold_font
    for col in range(1, 4):
        ws.cell(row=row, column=col).border = thin_border
    row += 2

    # 예상 기간
    ws[f'A{row}'] = "예상 제작 기간 / Estimated Duration"
    ws[f'B{row}'] = f"{result.estimated_weeks}주 / {result.estimated_weeks} weeks"
    row += 2

    # 비고
    if req.notes:
        ws[f'A{row}'] = "비고 / Notes"
        ws[f'A{row}'].font = section_font
        row += 1
        ws[f'A{row}'] = req.notes
        ws.merge_cells(f'A{row}:D{row}')

    # 열 너비 조정
    ws.column_dimensions['A'].width = 30
    ws.column_dimensions['B'].width = 35
    ws.column_dimensions['C'].width = 20
    ws.column_dimensions['D'].width = 15

    wb.save(filename)
    return True


def generate_pdf(result: QuoteResult, filename: str) -> bool:
    """PDF 파일 생성 (reportlab 사용)"""
    if not PDF_AVAILABLE:
        print("Error: reportlab is not installed")
        return False

    req = result.request
    curr = req.currency

    doc = SimpleDocTemplate(filename, pagesize=A4,
                           rightMargin=20*mm, leftMargin=20*mm,
                           topMargin=20*mm, bottomMargin=20*mm)
    elements = []
    styles = getSampleStyleSheet()

    # 커스텀 스타일
    title_style = ParagraphStyle('Title', parent=styles['Heading1'],
                                  fontSize=18, alignment=1, spaceAfter=20)
    heading_style = ParagraphStyle('Heading', parent=styles['Heading2'],
                                    fontSize=12, spaceBefore=15, spaceAfter=10)
    normal_style = styles['Normal']

    # 제목
    elements.append(Paragraph("AI DUBBING QUOTE", title_style))
    elements.append(Spacer(1, 5*mm))

    # 견적 정보
    elements.append(Paragraph(f"Quote Date: {result.created_at.strftime('%Y-%m-%d')}", normal_style))
    elements.append(Paragraph(f"Valid Until: {(result.created_at + timedelta(days=30)).strftime('%Y-%m-%d')}", normal_style))
    elements.append(Spacer(1, 5*mm))

    # 고객 정보
    elements.append(Paragraph("Client Information", heading_style))
    client_data = [
        ["Client:", req.client_name],
        ["Project:", req.project_name],
    ]
    if req.contact_email:
        client_data.append(["Email:", req.contact_email])

    client_table = Table(client_data, colWidths=[50*mm, 100*mm])
    client_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(client_table)
    elements.append(Spacer(1, 5*mm))

    # 프로젝트 상세
    elements.append(Paragraph("Project Details", heading_style))
    details_data = [
        ["Genre:", req.genre.value],
        ["Episodes:", f"{req.episode_count}"],
        ["Minutes per Episode:", f"{req.minutes_per_episode}"],
        ["Total Minutes:", f"{result.total_minutes}"],
        ["ME File Provided:", "Yes" if req.has_me_file else "No"],
        ["Script Provided:", "Yes" if req.has_script else "No"],
        ["Turnaround:", "Express (10 eps/week)" if req.turnaround == TurnaroundType.EXPRESS else "Standard (3 eps/week)"],
    ]

    details_table = Table(details_data, colWidths=[50*mm, 100*mm])
    details_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(details_table)
    elements.append(Spacer(1, 5*mm))

    # 견적 내역
    elements.append(Paragraph("Quote Breakdown", heading_style))

    quote_data = [["Item", "Details", "Amount"]]

    # 기본 금액
    quote_data.append([
        "Base Rate",
        f"{result.total_minutes} min x {format_currency(result.base_price_per_minute, curr)}",
        format_currency(result.base_total, curr)
    ])

    # 할인
    if result.me_discount > 0:
        quote_data.append(["ME File Discount", "10%", f"-{format_currency(result.me_discount, curr)}"])
    if result.script_discount > 0:
        quote_data.append(["Script Discount", "10%", f"-{format_currency(result.script_discount, curr)}"])
    if result.bulk_discount > 0:
        quote_data.append(["Bulk Discount (50+ eps)", "20%", f"-{format_currency(result.bulk_discount, curr)}"])

    # 급행
    if result.express_surcharge > 0:
        quote_data.append(["Express Surcharge", "x2", f"+{format_currency(result.express_surcharge, curr)}"])

    # 최종 금액
    quote_data.append(["FINAL TOTAL", "", format_currency(result.final_total, curr)])

    quote_table = Table(quote_data, colWidths=[60*mm, 50*mm, 50*mm])
    quote_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E6E6E6')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    elements.append(quote_table)
    elements.append(Spacer(1, 5*mm))

    # 예상 기간
    elements.append(Paragraph(f"Estimated Duration: {result.estimated_weeks} weeks", normal_style))

    # 비고
    if req.notes:
        elements.append(Spacer(1, 5*mm))
        elements.append(Paragraph("Notes", heading_style))
        elements.append(Paragraph(req.notes, normal_style))

    elements.append(Spacer(1, 10*mm))
    thank_style = ParagraphStyle('Thanks', parent=normal_style, alignment=1, fontName='Helvetica-Oblique')
    elements.append(Paragraph("Thank you for your inquiry.", thank_style))

    doc.build(elements)
    return True


def interactive_mode():
    """대화형 모드로 견적 생성"""
    print("\n" + "=" * 60)
    print("     AI 더빙 견적서 생성기 / AI Dubbing Quote Generator")
    print("=" * 60 + "\n")

    # 고객 정보
    client_name = input("고객명 / Client Name: ").strip() or "Guest Client"
    project_name = input("프로젝트명 / Project Name: ").strip() or "Untitled Project"
    contact_email = input("이메일 / Email (optional): ").strip()

    # 통화 선택
    print("\n통화 선택 / Select Currency:")
    print("  1. 원화 (KRW)")
    print("  2. 달러 (USD)")
    curr_choice = input("선택 / Choice [1]: ").strip() or "1"
    currency = Currency.USD if curr_choice == "2" else Currency.KRW

    # 장르 선택
    print("\n장르 선택 / Select Genre:")
    genres = list(Genre)
    for i, g in enumerate(genres, 1):
        price = PRICES[currency][g]
        unit = "원/분" if currency == Currency.KRW else "$/min"
        print(f"  {i}. {g.value} ({price:,}{unit})")

    genre_choice = input("선택 / Choice [1]: ").strip() or "1"
    try:
        genre = genres[int(genre_choice) - 1]
    except (ValueError, IndexError):
        genre = Genre.MOVIE

    # 편수 및 분량
    print("\n물량 입력 / Enter Volume:")
    ep_input = input("편수 / Number of Episodes [1]: ").strip() or "1"
    try:
        episode_count = int(ep_input)
    except ValueError:
        episode_count = 1

    min_input = input("편당 분량 (분) / Minutes per Episode [60]: ").strip() or "60"
    try:
        minutes_per_episode = int(min_input)
    except ValueError:
        minutes_per_episode = 60

    # 할인 조건
    print("\n할인 조건 / Discount Conditions:")
    has_me = input("ME 파일 제공 가능? / ME File Available? (y/N): ").strip().lower() == 'y'
    has_script = input("번역 대본/자막 제공 가능? / Script Available? (y/N): ").strip().lower() == 'y'

    # 턴어라운드
    print("\n제작 속도 / Turnaround Speed:")
    print("  1. 표준 (주 3편) / Standard (3 eps/week)")
    print("  2. 급행 (주 10편, 2배 가격) / Express (10 eps/week, 2x price)")
    ta_choice = input("선택 / Choice [1]: ").strip() or "1"
    turnaround = TurnaroundType.EXPRESS if ta_choice == "2" else TurnaroundType.STANDARD

    # 비고
    notes = input("\n비고 / Notes (optional): ").strip()

    # 견적 생성
    request = QuoteRequest(
        client_name=client_name,
        project_name=project_name,
        genre=genre,
        currency=currency,
        episode_count=episode_count,
        minutes_per_episode=minutes_per_episode,
        has_me_file=has_me,
        has_script=has_script,
        turnaround=turnaround,
        contact_email=contact_email,
        notes=notes,
    )

    result = QuoteResult(request=request)
    result.calculate()

    # 결과 출력
    print("\n" + generate_quote_text(result))

    # 파일 저장
    print("\n파일 저장 / Save Files:")
    base_filename = f"quote_{client_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    save_files = input("Excel/PDF 파일을 저장하시겠습니까? / Save Excel/PDF? (Y/n): ").strip().lower()
    if save_files != 'n':
        output_dir = input("저장 경로 / Output Directory [./]: ").strip() or "."

        excel_file = os.path.join(output_dir, f"{base_filename}.xlsx")
        pdf_file = os.path.join(output_dir, f"{base_filename}.pdf")

        if generate_excel(result, excel_file):
            print(f"  Excel 저장 완료: {excel_file}")

        if generate_pdf(result, pdf_file):
            print(f"  PDF 저장 완료: {pdf_file}")

    print("\n견적서 생성이 완료되었습니다. / Quote generation complete.")
    return result


def quick_quote(
    genre: str,
    episodes: int,
    minutes: int = 60,
    currency: str = "KRW",
    me_file: bool = False,
    script: bool = False,
    express: bool = False,
    client: str = "Client",
    project: str = "Project",
    output_dir: str = "."
) -> QuoteResult:
    """빠른 견적 생성 (스크립트용)"""

    # 장르 매핑
    genre_map = {
        "movie": Genre.MOVIE,
        "drama": Genre.DRAMA_VARIETY,
        "variety": Genre.DRAMA_VARIETY,
        "documentary": Genre.DOCUMENTARY,
        "podcast": Genre.PODCAST,
        "vlog": Genre.VLOG,
        "education": Genre.EDUCATION,
        "영화": Genre.MOVIE,
        "드라마": Genre.DRAMA_VARIETY,
        "예능": Genre.DRAMA_VARIETY,
        "다큐": Genre.DOCUMENTARY,
        "팟캐스트": Genre.PODCAST,
        "브이로그": Genre.VLOG,
        "교육": Genre.EDUCATION,
    }

    genre_enum = genre_map.get(genre.lower(), Genre.MOVIE)
    currency_enum = Currency.USD if currency.upper() == "USD" else Currency.KRW
    turnaround = TurnaroundType.EXPRESS if express else TurnaroundType.STANDARD

    request = QuoteRequest(
        client_name=client,
        project_name=project,
        genre=genre_enum,
        currency=currency_enum,
        episode_count=episodes,
        minutes_per_episode=minutes,
        has_me_file=me_file,
        has_script=script,
        turnaround=turnaround,
    )

    result = QuoteResult(request=request)
    result.calculate()

    # 파일 생성
    base_filename = f"quote_{client.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    excel_file = os.path.join(output_dir, f"{base_filename}.xlsx")
    pdf_file = os.path.join(output_dir, f"{base_filename}.pdf")

    generate_excel(result, excel_file)
    generate_pdf(result, pdf_file)

    print(generate_quote_text(result))
    print(f"\nFiles saved:")
    print(f"  Excel: {excel_file}")
    print(f"  PDF: {pdf_file}")

    return result


def main():
    """메인 함수"""
    import argparse

    parser = argparse.ArgumentParser(description="AI Dubbing Quote Generator")
    parser.add_argument("-i", "--interactive", action="store_true", help="Run in interactive mode")
    parser.add_argument("-g", "--genre", help="Genre: movie, drama, documentary, podcast, vlog, education")
    parser.add_argument("-e", "--episodes", type=int, help="Number of episodes")
    parser.add_argument("-m", "--minutes", type=int, default=60, help="Minutes per episode (default: 60)")
    parser.add_argument("-c", "--currency", default="KRW", help="Currency: KRW or USD")
    parser.add_argument("--me-file", action="store_true", help="ME file provided (10%% discount)")
    parser.add_argument("--script", action="store_true", help="Script provided (10%% discount)")
    parser.add_argument("--express", action="store_true", help="Express turnaround (2x price)")
    parser.add_argument("--client", default="Client", help="Client name")
    parser.add_argument("--project", default="Project", help="Project name")
    parser.add_argument("-o", "--output", default=".", help="Output directory")

    args = parser.parse_args()

    if args.interactive or (not args.genre and not args.episodes):
        interactive_mode()
    else:
        if not args.genre or not args.episodes:
            parser.print_help()
            print("\nError: --genre and --episodes are required in command mode")
            sys.exit(1)

        quick_quote(
            genre=args.genre,
            episodes=args.episodes,
            minutes=args.minutes,
            currency=args.currency,
            me_file=args.me_file,
            script=args.script,
            express=args.express,
            client=args.client,
            project=args.project,
            output_dir=args.output,
        )


if __name__ == "__main__":
    main()
