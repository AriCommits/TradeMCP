from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('greeks-viz/', include('greeks_viz.urls')),
]
