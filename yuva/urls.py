from django.urls import path
from . import views

urlpatterns = [
    # ==========================================
    # 1. TEMPLATE URLs
    # ==========================================
    path('', views.member_dashboard, name='home'),
    path('dashboard/', views.member_dashboard, name='dashboard'),
    path('savings/', views.member_savings_view, name='savings'),
    path('loans/', views.member_loans_view, name='loans'),
    path('passbook/', views.member_passbook_view, name='passbook'),
    path('profile/', views.member_profile, name='profile'),
    path('request-loan/', views.request_loan, name='request_loan'),
    
    # ==========================================
    # 2. AUTHENTICATION URLs
    # ==========================================
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'),

    # ==========================================
    # 3. API URLs
    # ==========================================
    path('api/dashboard/', views.DashboardAPI.as_view(), name='api_dashboard'),
    path('api/savings/', views.SavingsAPI.as_view(), name='api_savings'),
    path('api/loans/', views.LoansAPI.as_view(), name='api_loans'),
    path('api/passbook/', views.PassbookAPI.as_view(), name='api_passbook'),
    path('api/profile/', views.ProfileAPI.as_view(), name='api_profile'),
    
    # Notifications & Documents
    path('api/notifications/', views.NotificationsAPI.as_view(), name='api_notifications'),
    path('api/notifications/<int:notification_id>/delete/', views.delete_notification, name='delete_notification'),
    path('api/upload-doc/', views.DocumentUploadAPI.as_view(), name='api_upload_doc'),
    
    # Repayments
    path('api/repayments/', views.RepaymentsAPI.as_view(), name='api_repayments'),

    # ==========================================
    # 4. ADMIN & RAZORPAY URLs
    # ==========================================
    path('api/admin/loans/', views.AdminLoanManagementAPI.as_view(), name='api_admin_loans'),
    path('api/admin/loans/<int:loan_id>/', views.AdminLoanManagementAPI.as_view(), name='api_admin_loan_detail'),
    
    path('api/create-razorpay-order/', views.RazorpayOrderAPI.as_view(), name='api_create_razorpay_order'),
    path('api/verify-razorpay-payment/', views.RazorpayVerifyAPI.as_view(), name='api_verify_razorpay_payment'),
]