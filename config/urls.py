from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('meals.urls')),
    path('guide/', TemplateView.as_view(template_name='guide.html'), name='guide'),
]
