from django.urls import path
from yuva_admin import views

urlpatterns = [
    # ==========================================
    # 1. TEMPLATE RENDERING VIEWS (HTML Pages)
    # ==========================================
    path('', views.admin_dashboard_v2, name='admin_dashboard_root'),
    path('dashboard/', views.admin_dashboard_v2, name='admin_dashboard'),
    path('members/', views.admin_member_list, name='admin_members'),
    path('loans/', views.admin_loan_list, name='admin_loans'),
    path('collections/', views.admin_collections_view, name='admin_collections'),
    path('attendance/', views.admin_attendance_view, name='admin_attendance'),
    path('meetings/', views.admin_meetings_view, name='admin_meetings'),
    path('finance/', views.admin_finance_view, name='admin_finance'),
    path('reports/', views.admin_reports_view, name='admin_reports'),
    path('chat/', views.admin_chat_view, name='admin_chat'),
    
    # ==========================================
    # 2. DASHBOARD, FINANCE & REPORTS APIs
    # ==========================================
    path('api/dashboard-metrics/', views.DashboardMetricsAPI.as_view(), name='dashboard_metrics'),
    path('api/finance/', views.AdminFinanceAPI.as_view(), name='admin_finance_api'),
    path('api/reports/', views.AdminReportAPI.as_view(), name='admin_report_api'),

    # ==========================================
    # 3. MEMBER & LOAN APIs
    # ==========================================
    path('api/members/', views.admin_member_list_api, name='api_member_list'),
    path('api/members/create/', views.MemberDetailAPI.as_view(), name='api_member_create'),
    path('api/members/<int:pk>/', views.MemberDetailAPI.as_view(), name='api_member_detail'),
    path('api/loans/', views.admin_loan_list_api, name='admin_loan_list_api'),
    path('api/loans/<int:pk>/', views.LoanDetailAPI.as_view(), name='admin_loan_detail_api'),
    
    # ==========================================
    # 4. COLLECTIONS & RENTAL ITEMS APIs (Fixed)
    # ==========================================
    path('api/admin/collections/', views.AdminCollectionAPI.as_view(), name='admin_collections_api'),
    path('api/admin/rental-items/', views.AdminRentalItemAPI.as_view(), name='admin_rental_items_api'),
    path('api/admin/rental-items/<int:pk>/', views.AdminRentalItemDetailAPI.as_view(), name='admin_rental_item_detail_api'),

    # ==========================================
    # 5. MEETINGS & ATTENDANCE APIs
    # ==========================================
    path('api/admin/meetings/', views.AdminMeetingAPI.as_view(), name='api_admin_meetings'),
    path('api/admin/attendance/', views.AdminAttendanceAPI.as_view(), name='api_admin_attendance'),
    path('api/member/attendance/', views.MemberAttendanceAPI.as_view(), name='api_member_attendance'),
    
    # ==========================================
    # 6. CHAT APIs (Fixed)
    # ==========================================
    path('api/chat/rooms/', views.AdminChatRoomsAPI.as_view(), name='admin_chat_rooms_api'),
    path('api/chat/send/', views.AdminChatSendAPI.as_view(), name='admin_chat_send_api'),
    path('api/chat/<int:member_id>/', views.AdminChatRoomAPI.as_view(), name='admin_chat_room_api'),
]