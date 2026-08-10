from django.contrib import admin
from .models import Member, Loan, LoanInstallment, SavingsTransaction, Repayment, Notification, AdminNotice, ChatRoom, ChatMessage, Document, WeeklyCollection, AttendanceRecord, IncomeExpense, Product, Bill, Meeting

@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'village', 'role')
    search_fields = ('user__username', 'phone', 'village')
    list_filter = ('role', 'village')

@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ('id', 'member', 'amount', 'interest_rate', 'tenure_months', 'status', 'date')
    list_filter = ('status', 'date')
    search_fields = ('member__user__username',)

@admin.register(LoanInstallment)
class LoanInstallmentAdmin(admin.ModelAdmin):
    list_display = ('loan', 'installment_number', 'due_date', 'total_amount', 'is_paid')
    list_filter = ('is_paid', 'due_date')

@admin.register(SavingsTransaction)
class SavingsTransactionAdmin(admin.ModelAdmin):
    list_display = ('member', 'amount', 'transaction_type', 'date')
    list_filter = ('transaction_type', 'date')

@admin.register(Repayment)
class RepaymentAdmin(admin.ModelAdmin):
    list_display = ('loan', 'amount_paid', 'date')
    list_filter = ('date',)

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('member', 'message', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')

@admin.register(AdminNotice)
class AdminNoticeAdmin(admin.ModelAdmin):
    list_display = ('title', 'target_member', 'is_active', 'expires_at', 'created_at')
    list_filter = ('is_active', 'created_at', 'expires_at')
    search_fields = ('title', 'message')

@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ('member', 'subject', 'created_at', 'updated_at')
    search_fields = ('member__user__username', 'subject')
    list_filter = ('created_at', 'updated_at')

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('room', 'sender', 'created_at', 'is_read')
    search_fields = ('room__member__user__username', 'content')
    list_filter = ('sender', 'is_read', 'created_at')

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('member', 'file', 'uploaded_at')
    list_filter = ('uploaded_at',)

@admin.register(WeeklyCollection)
class WeeklyCollectionAdmin(admin.ModelAdmin):
    list_display = ('member', 'amount', 'payment_date', 'created_at')
    list_filter = ('payment_date', 'created_at')
    search_fields = ('member__user__username',)

@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('member', 'date', 'status', 'fine_amount', 'meeting')
    list_filter = ('status', 'date', 'meeting')
    search_fields = ('member__user__username',)

@admin.register(IncomeExpense)
class IncomeExpenseAdmin(admin.ModelAdmin):
    list_display = ('category', 'entry_type', 'amount', 'date')
    list_filter = ('entry_type', 'date')
    search_fields = ('category', 'description')

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'daily_price', 'is_for_sale', 'is_for_lease')
    list_filter = ('is_for_sale', 'is_for_lease')
    search_fields = ('name',)

@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ('id', 'member', 'product', 'total_amount', 'bill_date')
    list_filter = ('bill_date',)
    search_fields = ('member__user__username', 'product__name')

@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ('title', 'date', 'created_by', 'created_at')
    list_filter = ('date', 'created_at')
    search_fields = ('title', 'description')
