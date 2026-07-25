from rest_framework import serializers
from yuva.models import Member, Loan, SavingsTransaction, Repayment

class MemberSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='user.get_full_name', read_only=True, default='N/A')
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)
    join_date = serializers.DateTimeField(source='user.date_joined', read_only=True, format="%b %d, %Y")
    credit_grade = serializers.CharField(default='Standard', read_only=True)
    status = serializers.CharField(default='Active', read_only=True)

    class Meta:
        model = Member
        fields = '__all__'

class LoanApplicationSerializer(serializers.ModelSerializer):
    applicant_name = serializers.CharField(source='member.user.get_full_name', read_only=True, default='N/A')
    member_id = serializers.IntegerField(source='member.id', read_only=True)

    class Meta:
        model = Loan
        fields = '__all__'

class SavingsTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavingsTransaction
        fields = '__all__'

class RepaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Repayment
        fields = '__all__'