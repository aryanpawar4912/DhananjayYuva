from rest_framework import serializers
# Alias SavingsTransaction as Savings to stop the import error
from yuva.models import Member, SavingsTransaction as Savings, Loan, LoanInstallment, Repayment, Notification, Document

class MemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = Member
        fields = '__all__'

class SavingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Savings
        fields = '__all__'

class LoanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Loan
        fields = '__all__'

class RepaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Repayment
        fields = '__all__'

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'

class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = '__all__'

class LoanInstallmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoanInstallment
        fields = '__all__'

class LoanSerializer(serializers.ModelSerializer):
    installments = LoanInstallmentSerializer(many=True, read_only=True)
    
    class Meta:
        model = Loan
        fields = '__all__'