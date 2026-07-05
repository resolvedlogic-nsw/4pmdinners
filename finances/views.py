from io import BytesIO

import pandas as pd
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from xhtml2pdf import pisa
from django.db.models.functions import TruncWeek
from django.db.models import F
import html
from .forms import UploadForm
from .models import ImportBatch, Transaction
from .services import importers
from django.contrib.auth import logout
from django.shortcuts import redirect

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
                return redirect('finances:report', batch_id=batch.id)
            except Exception as e:
                batch.delete()
                form.add_error(None, f"Error processing file: {str(e)}")
    else:
        form = UploadForm()

    batches = ImportBatch.objects.all()
    return render(request, 'finances/upload.html', {'form': form, 'batches': batches})


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
    # Exclude YTD files from the main report dropdown
    batches = ImportBatch.objects.exclude(source='stripe_ytd')
    requested_batch_id = request.GET.get('batch_id') or batch_id

    if requested_batch_id:
        batch = get_object_or_404(ImportBatch, id=requested_batch_id)
    else:
        batch = batches.first()

    if batch is None:
        return redirect('finances:upload')

    qs = Transaction.objects.filter(batch=batch)
    ministry = request.GET.get('ministry') or ''
    if ministry:
        qs = qs.filter(ministry=ministry)

    ministries = Transaction.objects.filter(batch=batch).values_list('ministry', flat=True).distinct().order_by('ministry')

    context = _report_context(batch, qs)
    context.update({'batches': batches, 'ministries': ministries, 'selected_ministry': ministry})
    return render(request, 'finances/report.html', context)


@staff_member_required(login_url='/login/')
def report_pdf_view(request, batch_id):
    batch = get_object_or_404(ImportBatch, id=batch_id)
    qs = Transaction.objects.filter(batch=batch)
    ministry = request.GET.get('ministry') or ''
    if ministry:
        qs = qs.filter(ministry=ministry)

    context = _report_context(batch, qs)
    context['selected_ministry'] = ministry
    html = render_to_string('finances/report_pdf.html', context)

    result = BytesIO()
    pisa.CreatePDF(html, dest=result)

    safe_label = batch.label.replace(' ', '_')
    filename = f"{batch.get_source_display()}_{safe_label}.pdf"
    response = HttpResponse(result.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response
