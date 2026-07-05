from datetime import datetime
from io import BytesIO

import pandas as pd
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import logout
from django.db.models import Sum, F, Q
from django.db.models.functions import TruncWeek
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
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
                return redirect('finances:report', batch_id=batch.id)
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
            return redirect('finances:report', batch_id=batch.id)
    else:
        formset = TransactionReviewFormSet(queryset=qs)

    return render(request, 'finances/review.html', {'batch': batch, 'formset': formset})


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _resolve_batch(request, batch_id=None):
    """
    Figures out which ImportBatch the report page/PDF should show.

    Priority: an explicit batch_id (old-style links / the review redirect)
    wins outright. Otherwise we resolve from the Month dropdown + Source
    radio (default 'square'). If that exact month/source combo doesn't
    exist, we fall back to whichever source *does* have data for that
    month, so picking a month never dead-ends on an empty report.
    """
    batches = ImportBatch.objects.exclude(source='stripe_ytd')

    requested_batch_id = request.GET.get('batch_id') or batch_id
    if requested_batch_id:
        return get_object_or_404(ImportBatch, id=requested_batch_id), batches

    month_str = request.GET.get('month')
    source = request.GET.get('source') or 'square'

    report_month = None
    if month_str:
        try:
            report_month = datetime.strptime(month_str, '%Y-%m-%d').date()
        except ValueError:
            report_month = None

    if report_month is None:
        batch = batches.order_by('-report_month').first()
        return batch, batches

    batch = batches.filter(report_month=report_month, source=source).first()
    if batch is None:
        batch = batches.filter(report_month=report_month).exclude(source=source).first()
    return batch, batches


def _report_context(batch, qs):
    by_ministry = qs.values('ministry').annotate(
        gross=Sum('gross'), fees=Sum('fees'), net=Sum('net'), qty=Sum('qty')
    ).order_by('ministry')

    if batch.source == 'stripe':
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
        'batch': batch, 'transactions': qs.order_by('date', 'ministry'),
        'by_ministry': by_ministry, 'by_time': by_time, 'time_label': time_label,
        'by_item': by_item, 'totals': totals,
    }


@staff_member_required(login_url='/login/')
def report_view(request, batch_id=None):
    batch, batches = _resolve_batch(request, batch_id)
    if batch is None:
        return redirect('finances:upload')

    qs = Transaction.objects.filter(batch=batch)
    ministry = request.GET.get('ministry') or ''
    if ministry:
        qs = qs.filter(ministry=ministry)

    ministries = Transaction.objects.filter(batch=batch).values_list('ministry', flat=True).distinct().order_by('ministry')
    months = batches.values_list('report_month', flat=True).distinct().order_by('-report_month')

    context = _report_context(batch, qs)
    context.update({
        'batches': batches,
        'ministries': ministries,
        'selected_ministry': ministry,
        'months': months,
        'selected_source': batch.source,
    })
    return render(request, 'finances/report.html', context)


@staff_member_required(login_url='/login/')
def report_pdf_view(request, batch_id=None):
    batch, _batches = _resolve_batch(request, batch_id)
    if batch is None:
        return redirect('finances:upload')

    qs = Transaction.objects.filter(batch=batch)
    ministry = request.GET.get('ministry') or ''
    if ministry:
        qs = qs.filter(ministry=ministry)

    context = _report_context(batch, qs)
    context['selected_ministry'] = ministry
    html = render_to_string('finances/report_pdf.html', context)

    result = BytesIO()
    pisa.CreatePDF(html, dest=result)

    month_label = batch.report_month.strftime('%Y-%m')
    safe_ministry = f"_{ministry.replace(' ', '_')}" if ministry else ""
    filename = f"{batch.get_source_display()}_{month_label}{safe_ministry}.pdf"
    response = HttpResponse(result.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response
