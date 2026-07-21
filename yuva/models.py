from datetime import datetime, timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class Member(models.Model):
    ROLE_CHOICES = [('member', 'Member'), ('user', 'User')]

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, null=True, blank=True
    )
    phone = models.CharField(max_length=15, blank=True, null=True)
    village = models.CharField(max_length=100, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    role = models.CharField(
        max_length=20, choices=ROLE_CHOICES, default='member'
    )

    def __str__(self):
        username = self.user.username if self.user else 'Unnamed Member'
        return f'{username} - {self.get_role_display()}'


class Loan(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
    ]
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    interest_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=10.0
    )
    tenure_months = models.IntegerField(default=12)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending'
    )
    date = models.DateTimeField(auto_now_add=True)

    @property
    def emi_amount(self):
        if not self.amount or not self.interest_rate or not self.tenure_months:
            return Decimal('0.00')

        p = float(self.amount)
        r = float(self.interest_rate) / 100 / 12
        n = int(self.tenure_months)

        if r == 0:
            return round(Decimal(p / n), 2)

        emi = p * r * ((1 + r) ** n) / (((1 + r) ** n) - 1)
        return round(Decimal(emi), 2)

    def __str__(self):
        username = (
            self.member.user.username
            if self.member and self.member.user
            else 'Unknown'
        )
        return f'{username} - ₹{self.amount} ({self.status})'


class LoanInstallment(models.Model):
    loan = models.ForeignKey(
        Loan, on_delete=models.CASCADE, related_name='installments'
    )
    installment_number = models.IntegerField()
    due_date = models.DateField()
    principal_amount = models.DecimalField(max_digits=10, decimal_places=2)
    interest_amount = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    is_paid = models.BooleanField(default=False)

    def __str__(self):
        return f'Installment #{self.installment_number} for Loan #{self.loan.id} - ₹{self.total_amount}'


class SavingsTransaction(models.Model):
    TYPE_CHOICES = [('deposit', 'Deposit'), ('withdrawal', 'Withdrawal')]
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        username = (
            self.member.user.username
            if self.member and self.member.user
            else 'Unknown'
        )
        return f'{username} - {self.transaction_type} - ₹{self.amount}'


class Repayment(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Repayment for Loan #{self.loan.id} - ₹{self.amount_paid}'


class Notification(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        username = (
            self.member.user.username
            if self.member and self.member.user
            else 'Unknown'
        )
        return f'Notification for {username}'


class Document(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='documents')
    file = models.FileField(upload_to='documents/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Document {self.id} - {self.member.user.username}"


# ==========================================
# SIGNALS
# ==========================================
@receiver(post_save, sender=Loan)
def handle_loan_approval(sender, instance, created, **kwargs):
    if not created and instance.status == 'approved':
        if not LoanInstallment.objects.filter(loan=instance).exists():
            p = float(instance.amount)
            r = float(instance.interest_rate) / 100 / 12
            n = int(instance.tenure_months)
            emi = float(instance.emi_amount)

            remaining_principal = p
            base_date = instance.date.date() if instance.date else datetime.now().date()

            for i in range(1, n + 1):
                interest_comp = remaining_principal * r
                principal_comp = emi - interest_comp
                remaining_principal -= principal_comp
                due_date = base_date + timedelta(days=30 * i)

                LoanInstallment.objects.create(
                    loan=instance,
                    installment_number=i,
                    due_date=due_date,
                    principal_amount=round(Decimal(principal_comp), 2),
                    interest_amount=round(Decimal(interest_comp), 2),
                    total_amount=round(Decimal(emi), 2),
                )

            Notification.objects.create(
                member=instance.member,
                message=f'Your loan request #{instance.id} for ₹{instance.amount} has been APPROVED! Repayment schedule has been generated.',
            )
    elif not created and instance.status == 'rejected':
        Notification.objects.create(
            member=instance.member,
            message=f'Your loan request #{instance.id} for ₹{instance.amount} has been rejected.',
        )


@receiver(post_save, sender=User)
def create_user_member(sender, instance, created, **kwargs):
    if created:
        Member.objects.get_or_create(user=instance)