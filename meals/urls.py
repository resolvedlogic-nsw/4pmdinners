from django.urls import path
from . import views

urlpatterns = [

    # ── Home ──────────────────────────────────────────────────────────────────
    path('', views.home, name='home'),

    # ── Settings (staff only) ─────────────────────────────────────────────────
    path('settings/', views.settings_home, name='settings_home'),
    path('settings/branch/add/', views.settings_branch_add, name='settings_branch_add'),
    path('settings/branch/<int:branch_id>/edit/', views.settings_branch_edit, name='settings_branch_edit'),
    path('settings/branch/<int:branch_id>/delete/', views.settings_branch_delete, name='settings_branch_delete'),
    path('settings/branch/<int:branch_id>/products/', views.settings_products, name='settings_products'),
    path('settings/product/<int:product_id>/delete/', views.settings_product_delete, name='settings_product_delete'),

    # ── Branch-scoped family routes ───────────────────────────────────────────
    path('<slug:branch_slug>/', views.branch_index, name='branch_index'),
    path('<slug:branch_slug>/login/', views.family_login, name='branch_family_login'),
    path('<slug:branch_slug>/logout/', views.family_logout, name='branch_family_logout'),
    path('<slug:branch_slug>/register/', views.family_register, name='branch_family_register'),
    path('<slug:branch_slug>/recover/', views.family_recover_pin, name='branch_recover_pin'),
    path('<slug:branch_slug>/families/json/', views.families_json, name='branch_families_json'),
    path('<slug:branch_slug>/summary/', views.user_summary, name='branch_user_summary'),
    path('<slug:branch_slug>/family/children/', views.family_manage_children, name='branch_family_manage_children'),
    path('<slug:branch_slug>/qr/generate/', views.generate_qr, name='branch_generate_qr'),
    path('<slug:branch_slug>/qr/display/<uuid:nonce_id>/', views.qr_display, name='branch_qr_display'),
    path('<slug:branch_slug>/qr/status/<uuid:nonce_id>/', views.qr_status, name='branch_qr_status'),
    path('<slug:branch_slug>/pin/change/', views.change_pin, name='branch_change_pin'),

    # ── Online top-up (Square) ────────────────────────────────────────────────
    path('<slug:branch_slug>/topup/', views.topup_select, name='branch_topup_select'),
    path('<slug:branch_slug>/topup/checkout/', views.topup_checkout, name='branch_topup_checkout'),
    path('<slug:branch_slug>/topup/success/', views.topup_success, name='branch_topup_success'),
    path('<slug:branch_slug>/topup/cancel/', views.topup_cancel, name='branch_topup_cancel'),
    path('<slug:branch_slug>/topup/webhook/', views.topup_webhook, name='branch_topup_webhook'),

    # ── Branch-scoped kiosk routes ────────────────────────────────────────────
    path('<slug:branch_slug>/kiosk/', views.kiosk_login, name='branch_kiosk_login'),
    path('<slug:branch_slug>/kiosk/home/', views.kiosk_home, name='branch_kiosk_home'),
    path('<slug:branch_slug>/kiosk/logout/', views.kiosk_logout, name='branch_kiosk_logout'),
    path('<slug:branch_slug>/kiosk/scanner/', views.kiosk_scanner, name='branch_kiosk_scanner'),
    path('<slug:branch_slug>/kiosk/manual/', views.kiosk_manual, name='branch_kiosk_manual'),
    path('<slug:branch_slug>/kiosk/family/<int:family_id>/', views.kiosk_family_detail, name='branch_kiosk_family_detail'),
    path('<slug:branch_slug>/kiosk/family/<int:family_id>/children/', views.kiosk_manage_children, name='branch_kiosk_manage_children'),
    path('<slug:branch_slug>/kiosk/bulk/', views.kiosk_bulk_checkin, name='branch_kiosk_bulk_checkin'),
    path('<slug:branch_slug>/kiosk/attendance/', views.kiosk_view_attendance, name='branch_kiosk_view_attendance'),
    path('<slug:branch_slug>/kiosk/export/attendance/', views.kiosk_export_attendance, name='branch_kiosk_export_attendance'),
    path('<slug:branch_slug>/kiosk/export/roster/', views.kiosk_export_roster, name='branch_kiosk_export_roster'),
    path('<slug:branch_slug>/kiosk/export/transactions/', views.kiosk_export_transactions, name='branch_kiosk_export_transactions'),

    # ── Branch-scoped API endpoints ───────────────────────────────────────────
    path('<slug:branch_slug>/api/qr/redeem/', views.api_redeem_qr, name='branch_api_redeem_qr'),
    path('<slug:branch_slug>/api/kiosk/deduct/', views.api_kiosk_deduct, name='branch_api_kiosk_deduct'),
    path('<slug:branch_slug>/api/kiosk/topup/', views.api_kiosk_topup, name='branch_api_kiosk_topup'),
    path('<slug:branch_slug>/api/kiosk/family/add/', views.api_kiosk_add_family, name='branch_api_kiosk_add_family'),
    path('<slug:branch_slug>/api/kiosk/child/add/', views.api_kiosk_add_child, name='branch_api_kiosk_add_child'),
    path('<slug:branch_slug>/api/kiosk/child/delete/', views.api_kiosk_delete_child, name='branch_api_kiosk_delete_child'),
]