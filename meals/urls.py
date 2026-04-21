from django.urls import path
from . import views

app_name = 'meals'

urlpatterns = [
    # Public / auth
    path('', views.index, name='index'),
    path('login/', views.family_login, name='family_login'),
    path('logout/', views.family_logout, name='family_logout'),
    path('families/json/', views.families_json, name='families_json'),

    # Family (user) views
    path('summary/', views.user_summary, name='user_summary'),
    path('qr/generate/', views.generate_qr, name='generate_qr'),
    path('qr/display/<uuid:nonce_id>/', views.qr_display, name='qr_display'),
    path('qr/status/<uuid:nonce_id>/', views.qr_status, name='qr_status'),
    path('pin/change/', views.change_pin, name='change_pin'),

    # Kiosk views
    path('kiosk/', views.kiosk_login, name='kiosk_login'),
    path('kiosk/home/', views.kiosk_home, name='kiosk_home'),
    path('kiosk/logout/', views.kiosk_logout, name='kiosk_logout'),
    path('kiosk/scanner/', views.kiosk_scanner, name='kiosk_scanner'),
    path('kiosk/manual/', views.kiosk_manual, name='kiosk_manual'),
    path('kiosk/family/<int:family_id>/', views.kiosk_family_detail, name='kiosk_family_detail'),
    path('api/kiosk/topup/', views.api_kiosk_topup, name='api_kiosk_topup'),
    path('api/kiosk/family/add/', views.api_kiosk_add_family, name='api_kiosk_add_family'),

    
    # API endpoints
    path('api/qr/redeem/', views.api_redeem_qr, name='api_redeem_qr'),
    path('api/kiosk/deduct/', views.api_kiosk_deduct, name='api_kiosk_deduct'),
]
