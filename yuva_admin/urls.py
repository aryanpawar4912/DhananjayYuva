from django.urls import path
from yuva_admin import views

urlpatterns = [
    path('', views.admin_dashboard_v2, name='admin_dashboard'),
    path('dashboard/', views.admin_dashboard_v2, name='admin_dashboard'),
    path('members/', views.admin_member_list, name='admin_members'),
    path('loans/', views.admin_loan_list, name='admin_loans'),
    
    # API endpoints
    path('api/dashboard-metrics/', views.DashboardMetricsAPI.as_view(), name='dashboard-metrics'),
    path('api/members/', views.admin_member_list_api, name='api_member_list'),
    path('api/members/create/', views.MemberDetailAPI.as_view(), name='api_member_create'),
    path('api/members/<int:pk>/', views.MemberDetailAPI.as_view(), name='api_member_detail'),
    path('api/loans/', views.admin_loan_list_api, name='admin_loan_list_api'),
    path('api/loans/<int:pk>/', views.LoanDetailAPI.as_view(), name='admin_loan_detail_api'),
]