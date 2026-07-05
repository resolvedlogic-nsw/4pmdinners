from datetime import date

from django import forms
from django.utils import timezone

from .models import ImportBatch, Transaction

MONTH_CHOICES = [
    (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
    (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
    (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December'),
]


def _year_choices():
    current = timezone.now().year
    # A few years back (older reports) through one year ahead (planning).
    return [(y, y) for y in range(current - 4, current + 2)]


class UploadForm(forms.ModelForm):
    """
    Month + Year dropdowns replace the old free-text label. They're not
    model fields — clean() combines them into report_month, always pinned
    to the 1st of the month, so querying/sorting by date stays clean.
    """
    month = forms.ChoiceField(choices=MONTH_CHOICES, label="Month")
    year = forms.ChoiceField(choices=_year_choices, label="Year")

    class Meta:
        model = ImportBatch
        fields = ['source', 'uploaded_file']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        now = timezone.now()
        self.fields['month'].initial = now.month
        self.fields['year'].initial = now.year

    def clean(self):
        cleaned = super().clean()
        month = cleaned.get('month')
        year = cleaned.get('year')
        if month and year:
            cleaned['report_month'] = date(int(year), int(month), 1)
        return cleaned

    def save(self, commit=True):
        batch = super().save(commit=False)
        batch.report_month = self.cleaned_data['report_month']
        if commit:
            batch.save()
        return batch


class TransactionReviewForm(forms.ModelForm):
    """One row of the post-upload review formset — only the two fields the
    interceptor cares about are editable here."""

    class Meta:
        model = Transaction
        fields = ['ministry', 'item']
        widgets = {
            'ministry': forms.TextInput(attrs={'size': 20}),
            'item': forms.TextInput(attrs={'size': 40}),
        }


TransactionReviewFormSet = forms.modelformset_factory(
    Transaction,
    form=TransactionReviewForm,
    extra=0,
)
