from django.contrib import admin
from .models import Member, Loan, LoanInstallment, SavingsTransaction, Repayment, Notification, Document

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

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('member', 'file', 'uploaded_at')
    list_filter = ('uploaded_at',)