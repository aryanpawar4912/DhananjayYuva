from datetime import date
from rest_framework import serializers
from yuva.models import Member, Loan, SavingsTransaction, Repayment, WeeklyCollection, AttendanceRecord, IncomeExpense, RentalItem, Meeting

class MemberSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='user.get_full_name', read_only=True, default='N/A')
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email', required=False, allow_blank=True)
    join_date = serializers.DateTimeField(source='user.date_joined', read_only=True, format="%b %d, %Y")
    
    # Replace credit_grade or add user_type field
    user_type = serializers.SerializerMethodField()

    class Meta:
        model = Member
        fields = '__all__'
        extra_kwargs = {
            'status': {'required': False},
            'role': {'required': False},
        }

    def get_user_type(self, obj):
        # Checks if user is superuser/staff for Admin, otherwise returns their role or 'User'
        if obj.user and obj.user.is_superuser:
            return 'Admin'
        elif obj.role:
            return obj.role.capitalize() # Capitalizes 'member' to 'Member'
        return 'User'

    def update(self, instance, validated_data):
        user_data = validated_data.pop('user', {})
        user = instance.user
        if user and user_data:
            if 'email' in user_data:
                user.email = user_data['email']
            user.save()
        return super().update(instance, validated_data)


class LoanApplicationSerializer(serializers.ModelSerializer):
    applicant_name = serializers.SerializerMethodField()
    
    # Point source to 'date' because that is the field name defined on your Loan model
    disbursal_date = serializers.DateTimeField(
        source='date', 
        read_only=True, 
        format='%B %d, %Y, %I:%M %p'
    )
    status = serializers.CharField(required=False)

    class Meta:
        model = Loan
        fields = ['id', 'member', 'applicant_name', 'amount', 'status', 'disbursal_date']
        read_only_fields = ['id', 'member', 'amount', 'disbursal_date']

    def get_applicant_name(self, obj):
        if not obj.member:
            return "Unknown Applicant"
        
        if hasattr(obj.member, 'user') and obj.member.user:
            if hasattr(obj.member.user, 'get_full_name'):
                full_name = obj.member.user.get_full_name()
                if full_name and full_name.strip():
                    return full_name
            return obj.member.user.username
            
        return str(obj.member)

    def validate_status(self, value):
        if not value:
            return value
        return str(value).strip().lower()

class SavingsTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavingsTransaction
        fields = '__all__'

class RepaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Repayment
        fields = '__all__'


class WeeklyCollectionSerializer(serializers.ModelSerializer):
    member_name = serializers.CharField(source='member.user.username', read_only=True)

    class Meta:
        model = WeeklyCollection
        fields = '__all__'


class MeetingSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = Meeting
        fields = '__all__'


class AttendanceRecordSerializer(serializers.ModelSerializer):
    member_name = serializers.CharField(source='member.user.username', read_only=True)
    meeting_title = serializers.CharField(source='meeting.title', read_only=True)
    meeting_date = serializers.DateField(source='meeting.date', read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = [
            'id',
            'member',
            'member_name',
            'meeting',
            'meeting_title',
            'meeting_date',
            'date',
            'status',
            'fine_amount',
            'comments',
            'created_at',
        ]
        read_only_fields = ['member_name', 'meeting_title', 'meeting_date']


class IncomeExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = IncomeExpense
        fields = '__all__'


class RentalItemSerializer(serializers.ModelSerializer):
    """Serializer for managing items available for rent."""
    class Meta:
        model = RentalItem
        fields = '__all__'