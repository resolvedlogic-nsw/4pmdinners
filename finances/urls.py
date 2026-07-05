from django.urls import path
from . import views

app_name = 'finances'

urlpatterns = [
    path('', views.report_view, name='report_latest'),
    path('upload/', views.upload_view, name='upload'),
    path('report/<int:batch_id>/', views.report_view, name='report'),
    path('report/<int:batch_id>/pdf/', views.report_pdf_view, name='report_pdf'),

]
