from django import forms
from .models import ImportBatch


class UploadForm(forms.ModelForm):
    class Meta:
        model = ImportBatch
        fields = ['source', 'label', 'uploaded_file']
        widgets = {
            'label': forms.TextInput(attrs={'placeholder': "e.g. June 2026"}),
        }
