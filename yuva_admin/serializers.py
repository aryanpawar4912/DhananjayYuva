from rest_framework import serializers
from yuva.models import Member, SavingsTransaction, Loan, Repayment

class MemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = Member
        fields = '__all__'

class SavingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavingsTransaction
        fields = '__all__'

class LoanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Loan
        fields = '__all__'