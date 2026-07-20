from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('members/', views.admin_manage_members, name='admin_members'),
    path('loans/', views.admin_manage_loans, name='admin_loans'),
    path('savings/', views.admin_manage_savings, name='admin_savings'),
]