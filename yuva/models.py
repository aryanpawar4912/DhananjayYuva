from datetime import timedelta
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


class Member(models.Model):
    class Role(models.TextChoices):
        MEMBER = 'member', 'Member'
        USER = 'user', 'User'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True
    )
    phone = models.CharField(max_length=15, blank=True, null=True)
    village = models.CharField(max_length=100, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.MEMBER
    )

    def __str__(self):
        username = self.user.username if self.user else 'Unnamed Member'
        return f'{username} - {self.get_role_display()}'


class Loan(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        COMPLETED = 'completed', 'Completed'

    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=10.0)
    tenure_months = models.IntegerField(default=12)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    date = models.DateTimeField(auto_now_add=True)

    @property
    def emi_amount(self):
        if not self.amount or not self.interest_rate or not self.tenure_months:
            return Decimal('0.00')

        p = Decimal(str(self.amount))
        r = Decimal(str(self.interest_rate)) / Decimal('100') / Decimal('12')
        n = int(self.tenure_months)

        if r == Decimal('0'):
            return round(p / Decimal(n), 2)

        # EMI = P * r * (1 + r)^n / ((1 + r)^n - 1)
        emi = p * r * ((Decimal('1') + r) ** n) / (((Decimal('1') + r) ** n) - Decimal('1'))
        return round(emi, 2)

    def __str__(self):
        username = (
            self.member.user.username
            if self.member and self.member.user
            else 'Unknown'
        )
        return f'{username} - ₹{self.amount} ({self.get_status_display()})'


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
    class Type(models.TextChoices):
        DEPOSIT = 'deposit', 'Deposit'
        WITHDRAWAL = 'withdrawal', 'Withdrawal'

    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=Type.choices)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        username = (
            self.member.user.username
            if self.member and self.member.user
            else 'Unknown'
        )
        return f'{username} - {self.get_transaction_type_display()} - ₹{self.amount}'


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
        username = self.member.user.username if self.member and self.member.user else 'Unknown'
        return f"Document {self.id} - {username}"


# ==========================================
# SIGNALS
# ==========================================
@receiver(post_save, sender=Loan)
def handle_loan_approval(sender, instance, created, **kwargs):
    if not created and instance.status == Loan.Status.APPROVED:
        if not LoanInstallment.objects.filter(loan=instance).exists():
            p = Decimal(str(instance.amount))
            r = Decimal(str(instance.interest_rate)) / Decimal('100') / Decimal('12')
            n = int(instance.tenure_months)
            emi = Decimal(str(instance.emi_amount))

            remaining_principal = p
            base_date = instance.date.date() if instance.date else timezone.now().date()

            for i in range(1, n + 1):
                interest_comp = round(remaining_principal * r, 2)
                
                # Adjust final installment to account for floating/decimal rounding
                if i == n:
                    principal_comp = remaining_principal
                    total_amount = principal_comp + interest_comp
                else:
                    principal_comp = emi - interest_comp
                    total_amount = emi

                remaining_principal -= principal_comp
                
                # Note: relativedelta(months=1) from python-dateutil is more accurate for months, 
                # but timedelta(days=30) is an acceptable approximation if dateutil is unavailable.
                due_date = base_date + timedelta(days=30 * i)

                LoanInstallment.objects.create(
                    loan=instance,
                    installment_number=i,
                    due_date=due_date,
                    principal_amount=principal_comp,
                    interest_amount=interest_comp,
                    total_amount=total_amount,
                )

            Notification.objects.create(
                member=instance.member,
                message=f'Your loan request #{instance.id} for ₹{instance.amount} has been APPROVED! Repayment schedule has been generated.',
            )
            
    elif not created and instance.status == Loan.Status.REJECTED:
        Notification.objects.create(
            member=instance.member,
            message=f'Your loan request #{instance.id} for ₹{instance.amount} has been rejected.',
        )


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_member(sender, instance, created, **kwargs):
    if created:
        Member.objects.get_or_create(user=instance)