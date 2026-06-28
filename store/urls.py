# store/urls.py
from django.urls import path
from . import views

app_name = 'store'

urlpatterns = [
    path('',                views.product_list,   name='product_list'),
    path('sizes/',          views.size_chart,      name='size_chart'),
    path('cart/',           views.cart_view,       name='cart'),
    path('cart/add/',       views.cart_add,        name='cart_add'),
    path('cart/update/',    views.cart_update,     name='cart_update'),
    path('checkout/',       views.checkout,        name='checkout'),
    path('success/',        views.order_success,   name='success'),
    path('cancel/',         views.order_cancel,    name='cancel'),
    path('<slug:slug>/',    views.product_detail,  name='product_detail'),
]
