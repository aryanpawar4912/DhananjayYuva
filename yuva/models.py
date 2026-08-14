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

    class Gender(models.TextChoices):
        MALE = 'male', 'Male'
        FEMALE = 'female', 'Female'
        OTHER = 'other', 'Other'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name='yuva_member'
    )
    name = models.CharField(max_length=150, blank=True, null=True)
    gender = models.CharField(
        max_length=20, choices=Gender.choices, blank=True, null=True
    )
    phone = models.CharField(max_length=15, blank=True, null=True)
    village = models.CharField(max_length=100, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, default='Active')
    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.USER
    )
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def share_capital(self):
        total_savings = sum(
            tx.amount if tx.transaction_type == SavingsTransaction.Type.DEPOSIT else -tx.amount
            for tx in self.savingstransaction_set.all()
        )
        return (Decimal(total_savings) * Decimal('0.10')).quantize(Decimal('0.01')) if total_savings else Decimal('0.00')

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


class AdminNotice(models.Model):
    title = models.CharField(max_length=150)
    message = models.TextField()
    is_active = models.BooleanField(default=True)
    target_member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='admin_notices',
        help_text='Optional personal notice for a specific member'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        target = self.target_member.user.username if self.target_member and self.target_member.user else 'Global'
        return f'Notice: {self.title} ({target})'

    @property
    def is_current(self):
        return self.is_active and (not self.expires_at or self.expires_at >= timezone.now())


class ChatRoom(models.Model):
    member = models.OneToOneField(Member, on_delete=models.CASCADE, related_name='chat_room')
    subject = models.CharField(max_length=120, default='Member Support')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Chat Room'
        verbose_name_plural = 'Chat Rooms'

    def __str__(self):
        username = self.member.user.username if self.member and self.member.user else 'Unknown'
        return f'Chat room for {username}'


class ChatMessage(models.Model):
    class SenderType(models.TextChoices):
        MEMBER = 'member', 'Member'
        ADMIN = 'admin', 'Admin'

    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
    sender = models.CharField(max_length=10, choices=SenderType.choices, default=SenderType.MEMBER)
    content = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.get_sender_display()} message in {self.room} at {self.created_at.strftime("%Y-%m-%d %H:%M")}'


class Document(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='documents')
    file = models.FileField(upload_to='documents/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        username = self.member.user.username if self.member and self.member.user else 'Unknown'
        return f"Document {self.id} - {username}"


class WeeklyCollection(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='weekly_collections')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField(default=timezone.now)
    remarks = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-payment_date', '-created_at']

    def __str__(self):
        username = self.member.user.username if self.member and self.member.user else 'Unknown'
        return f'Collection ₹{self.amount} by {username} on {self.payment_date}'


class Meeting(models.Model):
    title = models.CharField(max_length=200)
    date = models.DateField(default=timezone.now)
    description = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.title} on {self.date}'


class AttendanceRecord(models.Model):
    class Status(models.TextChoices):
        PRESENT = 'present', 'Present'
        ABSENT = 'absent', 'Absent'
        LATE = 'late', 'Late'
        EXCUSED = 'excused', 'Excused'
        ON_LEAVE = 'on_leave', 'On Leave'

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField(default=timezone.now)
    meeting = models.ForeignKey('Meeting', on_delete=models.SET_NULL, null=True, blank=True, related_name='attendance_records')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PRESENT)
    fine_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    comments = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_paid = models.BooleanField(default=False, help_text="Tracks whether the fine has been settled/paid")

    class Meta:
        ordering = ['-date', '-created_at']
        unique_together = ('member', 'date')

    def __str__(self):
        return f'{self.member} - {self.status.title()} on {self.date}'


class Product(models.Model):
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, null=True)
    daily_price = models.DecimalField(max_digits=10, decimal_places=2)
    is_for_sale = models.BooleanField(default=True)
    is_for_lease = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} - ₹{self.daily_price}/day'


class Bill(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='bills')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='bills')
    quantity = models.PositiveIntegerField(default=1)
    days = models.PositiveIntegerField(default=1)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    bill_date = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-bill_date', '-created_at']

    def __str__(self):
        return f'Bill #{self.id} - {self.member} - ₹{self.total_amount}'


class IncomeExpense(models.Model):
    class EntryType(models.TextChoices):
        INCOME = 'income', 'Income'
        EXPENSE = 'expense', 'Expense'

    category = models.CharField(max_length=120)
    entry_type = models.CharField(max_length=10, choices=EntryType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.now)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.get_entry_type_display()} ₹{self.amount} - {self.category}'


class RentalItem(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    rental_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    deposit_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    available_quantity = models.PositiveIntegerField(default=1)
    image = models.ImageField(upload_to='rentals/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - ₹{self.rental_fee}/day"


class RentalRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        RETURNED = 'returned', 'Returned'

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='rental_requests')
    item = models.ForeignKey(RentalItem, on_delete=models.CASCADE, related_name='requests')
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        username = self.member.user.username if self.member and self.member.user else 'Unknown'
        return f"{username} requested {self.item.name} ({self.get_status_display()})"


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