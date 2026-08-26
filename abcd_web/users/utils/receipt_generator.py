import io
import os
import math
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, Flowable
from django.conf import settings

# -------------------------------------------------------------------
# BACKGROUND CANVAS DECORATION
# -------------------------------------------------------------------

def _draw_wave_band(canvas, x_start, y_start, x_end, y_end, color, alpha, line_width, wave_amplitude, num_lines, direction='tl'):
    """
    Draws a band of flowing parallel wavy curves.
    direction: 'tl' = top-left corner, 'br' = bottom-right corner
    """
    canvas.saveState()
    canvas.setStrokeColor(color)
    canvas.setStrokeAlpha(alpha)
    canvas.setLineWidth(line_width)

    for i in range(num_lines):
        t = i / max(num_lines - 1, 1)  # 0..1
        p = canvas.beginPath()

        if direction == 'tl':
            # Curves flow from left edge down to top edge right
            sx = x_start
            sy = y_start - t * (y_start - y_end) * 0.6
            ex = x_end + t * (x_end - x_start) * 0.3
            ey = y_start
            # Control points create the S-wave shape
            cp1x = sx + (ex - sx) * 0.25
            cp1y = sy - wave_amplitude * (1 - t * 0.5)
            cp2x = sx + (ex - sx) * 0.65
            cp2y = ey + wave_amplitude * (1 - t * 0.3)
            p.moveTo(sx, sy)
            p.curveTo(cp1x, cp1y, cp2x, cp2y, ex, ey)
        else:
            # Curves flow from right edge up to bottom edge left
            sx = x_end
            sy = y_start + t * (y_end - y_start) * 0.6
            ex = x_start - t * (x_end - x_start) * 0.3
            ey = y_start
            cp1x = sx - (sx - ex) * 0.25
            cp1y = sy + wave_amplitude * (1 - t * 0.5)
            cp2x = sx - (sx - ex) * 0.65
            cp2y = ey - wave_amplitude * (1 - t * 0.3)
            p.moveTo(sx, sy)
            p.curveTo(cp1x, cp1y, cp2x, cp2y, ex, ey)

        canvas.drawPath(p, fill=0, stroke=1)
    canvas.restoreState()


def draw_background(canvas, doc):
    """
    Renders a premium vector background with gentle, transparent
    flowing lines in the corners at ~25-30 degree angles.
    """
    canvas.saveState()
    width, height = doc.pagesize

    # 1. Soft off-white page fill
    canvas.setFillColor(colors.HexColor('#FDFAFD'))
    canvas.rect(0, 0, width, height, fill=1, stroke=0)

    # =====================================================================
    # 2. TOP-LEFT CORNER — Gentle, transparent wave fill + few soft lines
    # =====================================================================
    # Very light, transparent filled shape (wide & shallow ~25-30°)
    canvas.saveState()
    canvas.setFillColor(colors.HexColor('#F3E5F5'))
    canvas.setFillAlpha(0.20)
    p = canvas.beginPath()
    p.moveTo(0, height)
    p.lineTo(0, height - 100)
    p.curveTo(80, height - 75, 200, height - 30, 320, height - 15)
    p.curveTo(360, height - 10, 390, height - 5, 420, height)
    p.close()
    canvas.drawPath(p, fill=1, stroke=0)
    canvas.restoreState()

    # Second inner layer, even softer
    canvas.saveState()
    canvas.setFillColor(colors.HexColor('#E1BEE7'))
    canvas.setFillAlpha(0.12)
    p2 = canvas.beginPath()
    p2.moveTo(0, height)
    p2.lineTo(0, height - 60)
    p2.curveTo(60, height - 40, 150, height - 18, 250, height - 8)
    p2.curveTo(280, height - 5, 310, height - 2, 330, height)
    p2.close()
    canvas.drawPath(p2, fill=1, stroke=0)
    canvas.restoreState()

    # 6 gentle flowing lines at shallow ~25-30° angle (very transparent)
    tl_lines = [
        ('#F8BBD0', 0.22),   # lightest pink
        ('#E8B5D5', 0.20),
        ('#E1BEE7', 0.18),   # lavender
        ('#CE93D8', 0.16),   # medium purple
        ('#BA68C8', 0.14),   # purple
        ('#AB47BC', 0.12),   # deepest
    ]

    for i, (col, alpha) in enumerate(tl_lines):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor(col))
        canvas.setStrokeAlpha(alpha)
        canvas.setLineWidth(1.0)
        t = i / max(len(tl_lines) - 1, 1)
        p = canvas.beginPath()
        # Shallow curve: wide horizontal span, small vertical drop
        start_y = height - 15 - t * 85  # left edge Y (small vertical range)
        end_x = 100 + t * 310            # top edge X (wide horizontal span)
        # Gentle bezier for ~25-30° sweep
        cp1x = end_x * 0.3
        cp1y = start_y + 10
        cp2x = end_x * 0.65
        cp2y = height - 3
        p.moveTo(0, start_y)
        p.curveTo(cp1x, cp1y, cp2x, cp2y, end_x, height)
        canvas.drawPath(p, fill=0, stroke=1)
        canvas.restoreState()

    # =====================================================================
    # 3. BOTTOM-RIGHT CORNER — Mirror of top-left
    # =====================================================================
    canvas.saveState()
    canvas.setFillColor(colors.HexColor('#F3E5F5'))
    canvas.setFillAlpha(0.20)
    p = canvas.beginPath()
    p.moveTo(width, 0)
    p.lineTo(width, 100)
    p.curveTo(width - 80, 75, width - 200, 30, width - 320, 15)
    p.curveTo(width - 360, 10, width - 390, 5, width - 420, 0)
    p.close()
    canvas.drawPath(p, fill=1, stroke=0)
    canvas.restoreState()

    canvas.saveState()
    canvas.setFillColor(colors.HexColor('#E1BEE7'))
    canvas.setFillAlpha(0.12)
    p2 = canvas.beginPath()
    p2.moveTo(width, 0)
    p2.lineTo(width, 60)
    p2.curveTo(width - 60, 40, width - 150, 18, width - 250, 8)
    p2.curveTo(width - 280, 5, width - 310, 2, width - 330, 0)
    p2.close()
    canvas.drawPath(p2, fill=1, stroke=0)
    canvas.restoreState()

    # 6 gentle flowing lines (mirror)
    for i, (col, alpha) in enumerate(tl_lines):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor(col))
        canvas.setStrokeAlpha(alpha)
        canvas.setLineWidth(1.0)
        t = i / max(len(tl_lines) - 1, 1)
        p = canvas.beginPath()
        start_y = 15 + t * 85
        end_x = width - 100 - t * 310
        cp1x = width - (width - end_x) * 0.3
        cp1y = start_y - 10
        cp2x = width - (width - end_x) * 0.65
        cp2y = 3
        p.moveTo(width, start_y)
        p.curveTo(cp1x, cp1y, cp2x, cp2y, end_x, 0)
        canvas.drawPath(p, fill=0, stroke=1)
        canvas.restoreState()

    # =====================================================================
    # 4. Rounded rectangle inner border
    # =====================================================================
    canvas.setStrokeColor(colors.HexColor('#E1BEE7'))
    canvas.setStrokeAlpha(0.6)
    canvas.setLineWidth(0.8)
    canvas.roundRect(22, 22, width - 44, height - 44, 8)

    # =====================================================================
    # 5. "This is ABCD's system generated receipt." — bottom-left, above border
    # =====================================================================
    canvas.setFillColor(colors.HexColor('#888888'))
    canvas.setFillAlpha(1)
    canvas.setFont('Helvetica', 7.5)
    canvas.drawString(38, 32, "This is ABCD's system generated receipt.")

    # =====================================================================
    # 6. Faint watermark logo in center
    # =====================================================================
    watermark_path = os.path.join(settings.BASE_DIR, 'static/data/favicon/web-app-manifest-512x512.png')
    if os.path.exists(watermark_path):
        canvas.saveState()
        canvas.setFillAlpha(0.04) # slightly less transparent watermark (changed from 0.025)
        canvas.setStrokeAlpha(0.04)
        canvas.drawImage(watermark_path, (width - 300) / 2, (height - 300) / 2, width=300, height=300, mask='auto')
        canvas.restoreState()

    canvas.restoreState()


# -------------------------------------------------------------------
# CUSTOM FLOWABLES
# -------------------------------------------------------------------

class RotatedImage(Flowable):
    """Renders a rotated image (for digital signature)."""
    def __init__(self, path, width, height, rotation):
        Flowable.__init__(self)
        self.path = path
        self.width = width
        self.height = height
        self.rotation = rotation

    def draw(self):
        self.canv.saveState()
        self.canv.translate(self.width / 2, self.height / 2)
        self.canv.rotate(self.rotation)
        self.canv.translate(-self.width / 2, -self.height / 2)
        self.canv.drawImage(self.path, 0, 0, width=self.width, height=self.height, mask='auto')
        self.canv.restoreState()


class RoundedImage(Flowable):
    """Renders a circular-clipped image (for brand favicon)."""
    def __init__(self, path, size):
        Flowable.__init__(self)
        self.path = path
        self.size = size
        self.width = size
        self.height = size

    def draw(self):
        self.canv.saveState()
        path = self.canv.beginPath()
        r = self.size / 2.0
        path.circle(r, r, r)
        self.canv.clipPath(path, stroke=0, fill=0)
        self.canv.drawImage(self.path, 0, 0, width=self.size, height=self.size, mask='auto')
        self.canv.restoreState()


# -------------------------------------------------------------------
# INTERNAL HELPERS
# -------------------------------------------------------------------

def _build_header(elements, styles):
    """Builds the brand identity block: logo → favicon + title + subtitle → line."""
    # 1. Main Logo (centered, correct aspect ratio ~2.678:1)
    logo_path = os.path.join(settings.BASE_DIR, 'static/data/light-logo.png')
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=1.3 * inch, height=0.485 * inch)
        logo.hAlign = 'CENTER'
        elements.append(logo)
        elements.append(Spacer(1, 8))

    # 2. Favicon + "ABCD Coaching & Library" + "Any Body Can Do"
    favicon_path = os.path.join(settings.BASE_DIR, 'static/data/favicon/web-app-manifest-512x512.png')
    fav_img = None
    if os.path.exists(favicon_path):
        fav_img = RoundedImage(favicon_path, size=0.45 * inch)

    title_style = ParagraphStyle(
        'HeaderTitle', parent=styles['Normal'],
        fontSize=17, leading=20, spaceAfter=1,
        textColor=colors.HexColor('#1a1a1a'),
        fontName='Helvetica-Bold'
    )
    sub_style = ParagraphStyle(
        'HeaderSub', parent=styles['Normal'],
        fontSize=12, leading=15, spaceBefore=0,
        textColor=colors.HexColor('#8e24aa'),
        fontName='Helvetica-Oblique'
    )

    text_block = [
        Paragraph("ABCD Coaching &amp; Library", title_style),
        Paragraph("Any Body Can Do", sub_style),
    ]

    tbl = Table([[fav_img, text_block]], colWidths=[0.55 * inch, 3.0 * inch])
    tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (1, 0), (1, 0), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    tbl.hAlign = 'CENTER'
    elements.append(tbl)
    elements.append(Spacer(1, 14))

    # 3. Thin purple divider line
    line = Table([[""]], colWidths=[6.2 * inch])
    line.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (-1, -1), 0.8, colors.HexColor('#D1A3E0')),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    line.hAlign = 'CENTER'
    elements.append(line)
    elements.append(Spacer(1, 16))


def _build_info_section(elements, styles, transaction):
    """Builds: Fee Receipt title → address → receipt/date row → student details."""
    # 1. "Fee Receipt" heading (clean)
    elements.append(Paragraph("Fee Receipt", ParagraphStyle(
        'ReceiptTitle', parent=styles['Normal'],
        alignment=1, fontSize=19, leading=23,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#6A1B9A')
    )))
    elements.append(Spacer(1, 6))

    # 2. Address (centered, after heading)
    elements.append(Paragraph(
        "ABCD Coaching &amp; Library, Bareth Rd., Opposite to Block Office,<br/>"
        "Ganj Basoda, M.P., India - 464221",
        ParagraphStyle('Addr', parent=styles['Normal'],
                       alignment=1, fontSize=9.5, leading=13,
                       textColor=colors.HexColor('#555555'))
    ))
    elements.append(Spacer(1, 18))

    # 3. Receipt No (left) / Date (right)
    row = [[
        f"Receipt No :  {transaction.receipt_number}",
        f"Date :  {transaction.payment_date.strftime('%d/%m/%Y')}"
    ]]
    t = Table(row, colWidths=[3.1 * inch, 3.1 * inch])
    t.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#222222')),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    t.hAlign = 'CENTER'
    elements.append(t)
    elements.append(Spacer(1, 14))

    # 4. Student details
    lbl = ParagraphStyle('ToLbl', parent=styles['Normal'], fontSize=12, leading=15,
                         fontName='Helvetica-Bold', textColor=colors.HexColor('#7b1fa2'))
    det = ParagraphStyle('Det', parent=styles['Normal'], fontSize=10, leading=15, fontName='Helvetica')

    elements.append(Paragraph("To,", lbl))
    elements.append(Paragraph(f"Student Name :  {transaction.student.full_name}", det))
    elements.append(Paragraph(f"Mobile No :  {transaction.student.mobile_number or 'N/A'}", det))
    elements.append(Paragraph(f"Service :  {transaction.service_snapshot}", det))
    elements.append(Spacer(1, 20))


def _build_payment_table(elements, styles, transaction):
    """Builds: Payment Details capsule separator → data table."""
    # 1. "Payment Details" capsule divider
    div = Table([["", "Payment Details", ""]], colWidths=[2.1 * inch, 2.0 * inch, 2.1 * inch])
    div.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (0, 0), 0.6, colors.HexColor('#D1A3E0')),
        ('LINEBELOW', (2, 0), (2, 0), 0.6, colors.HexColor('#D1A3E0')),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#F3E5F5')),
        ('TEXTCOLOR', (1, 0), (1, 0), colors.HexColor('#6A1B9A')),
        ('FONTNAME', (1, 0), (1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (1, 0), (1, 0), 10.5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    div.hAlign = 'CENTER'
    elements.append(div)
    elements.append(Spacer(1, 14))

    # 2. Table
    header = ['Month Paid', 'Amount Paid', 'Expiry Date', 'Payment Date']
    data = [header]
    months = transaction.months_snapshot or []
    n = len(months)
    expiry = transaction.expiry_date.strftime('%d/%m/%Y') if transaction.expiry_date else "N/A"
    pay_dt = transaction.payment_date.strftime('%d/%m/%Y')

    for m in months:
        amt = m.get('amount')
        if amt == "Paid":
            display = "Paid"
        else:
            try:
                display = f"Rs. {int(amt)}"
            except Exception:
                display = f"Rs. {amt}"
        data.append([m.get('month'), display, expiry, pay_dt])

    tbl = Table(data, colWidths=[2.0 * inch, 1.4 * inch, 1.4 * inch, 1.4 * inch])
    ts = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#7b1fa2')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E1BEE7')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9.5),
        ('FONTSIZE', (0, 1), (-1, -1), 9.5),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ])
    if n > 1:
        ts.add('SPAN', (2, 1), (2, n))
        ts.add('SPAN', (3, 1), (3, n))
    tbl.setStyle(ts)
    elements.append(tbl)
    elements.append(Spacer(1, 40))


def _build_footer(elements, styles):
    """Right-aligned signature block (system text is drawn on canvas)."""
    sig_path = os.path.join(settings.BASE_DIR, 'static/data/signature.png')
    sig = ""
    if os.path.exists(sig_path):
        sig = RotatedImage(sig_path, width=1.4 * inch, height=0.45 * inch, rotation=8)

    ft = Table([
        ["", sig],
        ["", Paragraph("<b>Authorized Signatory</b>", ParagraphStyle(
            'Sig', parent=styles['Normal'], alignment=1, fontSize=9,
            fontName='Helvetica-Bold', textColor=colors.HexColor('#6A1B9A')
        ))],
    ], colWidths=[4.0 * inch, 2.2 * inch])
    ft.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    ft.hAlign = 'CENTER'
    elements.append(ft)


# -------------------------------------------------------------------
# MAIN GENERATOR
# -------------------------------------------------------------------

def generate_fee_receipt_pdf(transaction):
    """
    ABCD Fee Receipt Generator — premium branded PDF.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        rightMargin=50, leftMargin=50,
        topMargin=40, bottomMargin=50
    )

    elements = []
    styles = getSampleStyleSheet()

    _build_header(elements, styles)
    _build_info_section(elements, styles, transaction)
    _build_payment_table(elements, styles, transaction)
    _build_footer(elements, styles)

    doc.build(elements, onFirstPage=draw_background, onLaterPages=draw_background)
    buf.seek(0)
    return buf
