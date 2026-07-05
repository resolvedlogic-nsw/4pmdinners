from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from finances.views import custom_logout

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', auth_views.LoginView.as_view(template_name='finances/login.html',redirect_authenticated_user=True,next_page='/finances/'), name='login'),
    path('logout/', custom_logout, name='logout'),
    path('store/', include('store.urls')),
    path('finances/', include('finances.urls')),
    path('', include('meals.urls')),
]
