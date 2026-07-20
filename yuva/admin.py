from django.contrib import admin
from .models import Member, Loan, SavingsTransaction, Repayment, Notification, Document

admin.site.register(Member)
admin.site.register(Loan)
admin.site.register(SavingsTransaction)
admin.site.register(Repayment)
admin.site.register(Notification)
admin.site.register(Document)