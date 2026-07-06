from datetime import date, datetime
from io import BytesIO

import pandas as pd
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import logout
from django.db.models import Sum, F, Q
from django.db.models.functions import TruncWeek, TruncMonth
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from xhtml2pdf import pisa

from .forms import UploadForm, TransactionReviewFormSet
from .models import ImportBatch, Transaction
from .services import importers


def _read_upload(batch):
    path = batch.uploaded_file.path
    is_excel = path.lower().endswith(('.xlsx', '.xls'))
    if batch.source == 'square':
        return pd.read_excel(path, sheet_name=0) if is_excel else pd.read_csv(path)
    if batch.source == 'stripe_ytd':
        return pd.read_csv(path)

    if is_excel:
        xl = pd.ExcelFile(path)
        sheet = next((s for s in xl.sheet_names if 'itemised' in s.lower() or 'reconcil' in s.lower()), xl.sheet_names[0])
        return xl.parse(sheet)
    return pd.read_csv(path)


def custom_logout(request):
    logout(request)
    return redirect('login')


def _needs_review(batch):
    """Trigger condition for the interceptor: any row in this batch still
    has an unresolved ministry or a blank description."""
    return Transaction.objects.filter(batch=batch).filter(
        Q(ministry='Unknown') | Q(item='')
    ).exists()


def _report_url_for(batch):
    """
    Starting point for 'go look at the report' right after an upload or a
    review save. Uses the month/source the uploader picked for this batch —
    a reasonable default view — but the report itself groups by each
    transaction's real date, so anything that actually belongs to a
    different month (payout lag, month-end straddle) will show up there
    instead once you navigate the Month dropdown.
    """
    return f"{reverse('finances:report')}?month={batch.report_month:%Y-%m-%d}&source={batch.source}"


# ---------------------------------------------------------------------------
# Upload + review interceptor
# ---------------------------------------------------------------------------

SORT_FIELDS = {
    'uploaded': ('-uploaded_at', 'uploaded'),
    'uploaded_asc': ('uploaded_at', 'uploaded'),
    'month': ('-report_month', 'month'),
    'month_asc': ('report_month', 'month'),
    'source': ('source', 'source'),
    'source_desc': ('-source', 'source'),
}


@staff_member_required(login_url='/login/')
def upload_view(request):
    if request.method == 'POST':
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            batch = form.save()
            try:
                df = _read_upload(batch)
                if batch.source == 'square':
                    importers.import_square(df, batch)
                elif batch.source == 'stripe':
                    importers.import_stripe(df, batch)
                elif batch.source == 'stripe_ytd':
                    importers.import_stripe_ytd(df, batch)

                if batch.source == 'stripe_ytd':
                    return redirect('finances:upload')

                if _needs_review(batch):
                    return redirect('finances:review', batch_id=batch.id)
                return redirect(_report_url_for(batch))
            except Exception as e:
                batch.delete()
                form.add_error(None, f"Error processing file: {str(e)}")
    else:
        form = UploadForm()

    sort_key = request.GET.get('sort', 'uploaded')
    order_field, _ = SORT_FIELDS.get(sort_key, SORT_FIELDS['uploaded'])
    batches = ImportBatch.objects.all().order_by(order_field)
    return render(request, 'finances/upload.html', {
        'form': form, 'batches': batches, 'current_sort': sort_key,
    })


@staff_member_required(login_url='/login/')
def review_view(request, batch_id):
    batch = get_object_or_404(ImportBatch, id=batch_id)
    qs = Transaction.objects.filter(batch=batch).filter(
        Q(ministry='Unknown') | Q(item='')
    ).order_by('date', 'id')

    if request.method == 'POST':
        formset = TransactionReviewFormSet(request.POST, queryset=qs)
        if formset.is_valid():
            formset.save()
            return redirect(_report_url_for(batch))
    else:
        formset = TransactionReviewFormSet(queryset=qs)

    return render(request, 'finances/review.html', {'batch': batch, 'formset': formset})


# ---------------------------------------------------------------------------
# Reporting
#
# A report is a (calendar month, source) pair, built from each
# transaction's own `date` field — NOT from a single upload batch. This
# matters because one upload can legitimately span a month boundary:
# Stripe's payout-effective date lags the file's nominal month for some
# transactions, and a Square month-end POS export can catch a transaction
# or two from the next day. Grouping by real date means those transactions
# land in the report they actually belong to, even if several different
# uploads end up contributing rows to the same reported month.
#
# ImportBatch.report_month is still useful as a label for the "All Uploads"
# list (what you told the system this file was for) — it just isn't what
# the report page filters by any more.
# ---------------------------------------------------------------------------

SOURCE_LABELS = dict(ImportBatch.SOURCE_CHOICES)


class ReportPeriod:
    """Stand-in for the old 'batch' template variable. Templates keep
    referencing `batch.report_month` / `batch.get_source_display` /
    `batch.source` unchanged — this just supplies those from a
    (month, source) pair instead of a single ImportBatch row."""

    def __init__(self, source, report_month):
        self.source = source
        self.report_month = report_month

    def get_source_display(self):
        return SOURCE_LABELS.get(self.source, self.source)


def _resolve_period(request):
    """
    Resolves the (year, month, source) triple the report page/PDF should
    show, from the Month dropdown + Source radio (default 'square'). If
    that exact month/source combo has no data, falls back to whichever
    source *does* have data for that month, so picking a month never
    dead-ends on an empty report.
    """
    month_str = request.GET.get('month')
    source = request.GET.get('source') or 'square'

    month_date = None
    if month_str:
        try:
            month_date = datetime.strptime(month_str, '%Y-%m-%d').date()
        except ValueError:
            month_date = None

    if month_date is None:
        latest = Transaction.objects.order_by('-date').values_list('date', flat=True).first()
        if latest is None:
            return None, None, None
        month_date = latest.replace(day=1)

    has_data = Transaction.objects.filter(
        source=source, date__year=month_date.year, date__month=month_date.month
    ).exists()
    if not has_data:
        other = 'stripe' if source == 'square' else 'square'
        if Transaction.objects.filter(
            source=other, date__year=month_date.year, date__month=month_date.month
        ).exists():
            source = other

    return month_date.year, month_date.month, source


def _report_context(period, qs):
    by_ministry = qs.values('ministry').annotate(
        gross=Sum('gross'), fees=Sum('fees'), net=Sum('net'), qty=Sum('qty')
    ).order_by('ministry')

    if period.source == 'stripe':
        by_time = qs.annotate(time_period=TruncWeek('date')).values('time_period').annotate(
            gross=Sum('gross'), fees=Sum('fees'), net=Sum('net')
        ).order_by('time_period')
        time_label = 'Week Starting (Mon)'
    else:
        by_time = qs.annotate(time_period=F('date')).values('time_period').annotate(
            gross=Sum('gross'), fees=Sum('fees'), net=Sum('net')
        ).order_by('time_period')
        time_label = 'Date'

    by_item = qs.values('ministry', 'item').annotate(
        gross=Sum('gross'), fees=Sum('fees'), net=Sum('net'), qty=Sum('qty')
    ).order_by('ministry', 'item')
    totals = qs.aggregate(gross=Sum('gross'), fees=Sum('fees'), net=Sum('net'))

    return {
        'batch': period, 'transactions': qs.order_by('date', 'ministry'),
        'by_ministry': by_ministry, 'by_time': by_time, 'time_label': time_label,
        'by_item': by_item, 'totals': totals,
    }


@staff_member_required(login_url='/login/')
def report_view(request):
    year, month, source = _resolve_period(request)
    if year is None:
        return redirect('finances:upload')

    qs = Transaction.objects.filter(source=source, date__year=year, date__month=month)
    ministry = request.GET.get('ministry') or ''
    if ministry:
        qs = qs.filter(ministry=ministry)

    ministries = Transaction.objects.filter(
        source=source, date__year=year, date__month=month
    ).values_list('ministry', flat=True).distinct().order_by('ministry')

    months = Transaction.objects.annotate(month=TruncMonth('date')).values_list(
        'month', flat=True
    ).distinct().order_by('-month')

    period = ReportPeriod(source, date(year, month, 1))
    context = _report_context(period, qs)
    context.update({
        'ministries': ministries,
        'selected_ministry': ministry,
        'months': months,
        'selected_source': source,
    })
    return render(request, 'finances/report.html', context)


@staff_member_required(login_url='/login/')
def report_pdf_view(request):
    year, month, source = _resolve_period(request)
    if year is None:
        return redirect('finances:upload')

    qs = Transaction.objects.filter(source=source, date__year=year, date__month=month)
    ministry = request.GET.get('ministry') or ''
    if ministry:
        qs = qs.filter(ministry=ministry)

    period = ReportPeriod(source, date(year, month, 1))
    context = _report_context(period, qs)
    context['selected_ministry'] = ministry
    html = render_to_string('finances/report_pdf.html', context)

    result = BytesIO()
    pisa.CreatePDF(html, dest=result)

    month_label = period.report_month.strftime('%Y-%m')
    safe_ministry = f"_{ministry.replace(' ', '_')}" if ministry else ""
    filename = f"{period.get_source_display()}_{month_label}{safe_ministry}.pdf"
    response = HttpResponse(result.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response

