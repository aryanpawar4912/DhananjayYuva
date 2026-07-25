from django.db import models
from django.utils import timezone

class Member(models.Model):
    GRADE_CHOICES = [('A', 'Grade A'), ('B', 'Grade B'), ('C', 'Grade C'), ('D', 'Grade D')]
    STATUS_CHOICES = [('Active', 'Active'), ('Warning', 'Warning'), ('Defaulter', 'Defaulter')]

    full_name = models.CharField(max_length=150, default="Admin User")
    join_date = models.DateField(default=timezone.now)
    credit_grade = models.CharField(max_length=1, choices=GRADE_CHOICES, default='B')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')
    
    def __str__(self):
        return self.full_name

class LoanApplication(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'), ('UNDERWRITING', 'Underwriting'),
        ('APPROVED', 'Approved'), ('REJECTED', 'Rejected'),
        ('ACTIVE', 'Active'), ('DEFAULTED', 'Defaulted')
    ]
    PORTFOLIO_CHOICES = [
        ('PERFORMING', 'Performing'), ('SUB_STANDARD', 'Sub-Standard'),
        ('DOUBTFUL', 'Doubtful'), ('LOSS', 'Loss')
    ]

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='loans')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    remaining_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    purpose = models.CharField(max_length=255)
    apply_date = models.DateField(default=timezone.now)
    disbursal_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    portfolio_status = models.CharField(max_length=20, choices=PORTFOLIO_CHOICES, default='PERFORMING')

    def __str__(self):
        return f"Loan #{self.id} - {self.member.full_name} ({self.amount})"

class Transaction(models.Model):
    TYPE_CHOICES = [('CREDIT', 'Credit'), ('RECOVERY', 'Recovery'), ('DEBIT', 'Debit')]
    
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='CREDIT')
    date = models.DateField(default=timezone.now)
    loan = models.ForeignKey(LoanApplication, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')

    def __str__(self):
        return f"{self.transaction_type}: {self.amount} on {self.date}"