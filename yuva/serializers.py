from decimal import Decimal
from rest_framework import serializers

# Using relative import to ensure app portability
from .models import (
    AdminNotice,
    AttendanceRecord,
    Bill,
    ChatMessage,
    ChatRoom,
    Document,
    IncomeExpense,
    Loan,
    LoanInstallment,
    Meeting,
    Member,
    Notification,
    Product,
    RentalItem,
    RentalRequest,
    Repayment,
    SavingsTransaction as Savings,
    WeeklyCollection,
)


class MemberSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(source='phone', required=False, allow_blank=True)
    residential_address = serializers.CharField(source='address', required=False, allow_blank=True)
    status = serializers.CharField(default='Active', read_only=True)
    full_name = serializers.CharField(source='user.get_full_name', read_only=True, default='N/A')
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email', required=False, allow_blank=True)
    join_date = serializers.DateTimeField(source='user.date_joined', read_only=True, format='%b %d, %Y')
    user_type = serializers.SerializerMethodField()

    class Meta:
        model = Member
        fields = '__all__'

    def get_user_type(self, obj):
        if obj.user and obj.user.is_superuser:
            return 'Admin'
        elif obj.role:
            return obj.role.capitalize()
        return 'User'


class SavingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Savings
        fields = '__all__'


class RepaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Repayment
        fields = '__all__'


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'


class AdminNoticeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminNotice
        fields = '__all__'


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = '__all__'


class ChatRoomSerializer(serializers.ModelSerializer):
    messages = ChatMessageSerializer(many=True, read_only=True)

    class Meta:
        model = ChatRoom
        fields = '__all__'


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = '__all__'


class WeeklyCollectionSerializer(serializers.ModelSerializer):
    member_name = serializers.CharField(source='member.user.username', read_only=True)

    class Meta:
        model = WeeklyCollection
        fields = '__all__'


class AttendanceRecordSerializer(serializers.ModelSerializer):
    member_name = serializers.CharField(source='member.user.username', read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = '__all__'


class IncomeExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = IncomeExpense
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
        read_only_fields = ('date', 'emi_amount')


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = '__main__'
        fields = '__all__'


class BillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bill
        fields = '__all__'


class MeetingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Meeting
        fields = '__all__'


class RentalItemSerializer(serializers.ModelSerializer):
    price = serializers.DecimalField(
        source='rental_fee', 
        max_digits=10, 
        decimal_places=2, 
        required=False, 
        default=Decimal('0.00')
    )
    rental_fee = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        required=False, 
        default=Decimal('0.00')
    )
    deposit_fee = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        required=False, 
        default=Decimal('0.00')
    )

    class Meta:
        model = RentalItem
        fields = '__all__'


class RentalRequestSerializer(serializers.ModelSerializer):
    member_name = serializers.CharField(source='member.user.username', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)

    class Meta:
        model = RentalRequest
        fields = '__all__'