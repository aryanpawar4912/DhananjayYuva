import json
from decimal import Decimal
from datetime import timedelta, datetime
from django.http import JsonResponse
from django.shortcuts import render
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.db.models.functions import TruncMonth, TruncWeek
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.csrf import ensure_csrf_cookie

from rest_framework.views import APIView, View
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status, permissions
from django.contrib.auth import get_user_model

from yuva_admin.serializers import (
    MemberSerializer,
    LoanApplicationSerializer,
    WeeklyCollectionSerializer,
    MeetingSerializer,
    AttendanceRecordSerializer,
    IncomeExpenseSerializer,
    RentalItemSerializer
)
from yuva.models import (
    Member, Loan, RentalRequest, SavingsTransaction, Repayment, ChatRoom, ChatMessage, 
    AdminNotice, WeeklyCollection, AttendanceRecord, IncomeExpense, 
    Notification, Meeting, RentalItem
)

# ==========================================
# 1. Template Rendering Views (Admin Panel)
# ==========================================

@login_required
@user_passes_test(lambda u: u.is_staff or u.is_superuser)
def admin_dashboard_v2(request):
    return render(request, 'admin/admin_dashboard.html')

@login_required
@user_passes_test(lambda u: u.is_staff or u.is_superuser)
def admin_member_list(request):
    return render(request, 'admin/admin_member_list.html')

@login_required
@user_passes_test(lambda u: u.is_staff or u.is_superuser)
def admin_loan_list(request):
    return render(request, 'admin/admin_loan.html')

@login_required
@user_passes_test(lambda u: u.is_staff or u.is_superuser)
def admin_collections_view(request):
    return render(request, 'admin/admin_collections.html')

@login_required
@user_passes_test(lambda u: u.is_staff or u.is_superuser)
@ensure_csrf_cookie
def admin_attendance_view(request):
    return render(request, 'admin/admin_attendance.html')

@login_required
@user_passes_test(lambda u: u.is_staff or u.is_superuser)
def admin_meetings_view(request):
    return render(request, 'admin/admin_meetings.html')

@login_required
@user_passes_test(lambda u: u.is_staff or u.is_superuser)
def admin_finance_view(request):
    return render(request, 'admin/admin_finance.html')

@login_required
@user_passes_test(lambda u: u.is_staff or u.is_superuser)
def admin_reports_view(request):
    return render(request, 'admin/admin_reports.html')

@login_required
@user_passes_test(lambda u: u.is_staff or u.is_superuser)
def admin_chat_view(request):
    return render(request, 'admin/admin_chat.html')


# ==========================================
# 2. Dashboard Metrics API
# ==========================================

class DashboardMetricsAPI(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        total_capital = SavingsTransaction.objects.filter(
            transaction_type=SavingsTransaction.Type.DEPOSIT
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        active_loans = Loan.objects.filter(status=Loan.Status.APPROVED).count()
        total_members = Member.objects.count()

        total_loans_count = Loan.objects.count()
        rejected_loans_count = Loan.objects.filter(status=Loan.Status.REJECTED).count()
        default_rate = round((rejected_loans_count / total_loans_count * 100), 2) if total_loans_count > 0 else 0.00

        # --- DYNAMIC SESSION STATUS LOGIC ---
        today = timezone.now().date()
        nearest_meeting = Meeting.objects.filter(date__gte=today).order_by('date').first()
        
        if nearest_meeting:
            if nearest_meeting.date == today:
                session_status = "Active Today"
            else:
                session_status = f"Upcoming: {nearest_meeting.date.strftime('%b %d')}"
        else:
            session_status = "No Upcoming Sessions"
        # ------------------------------------

        disbursements_list = []
        recoveries_list = []

        raw_savings = (
            SavingsTransaction.objects.filter(transaction_type=SavingsTransaction.Type.DEPOSIT)
            .annotate(month=TruncMonth('date'))
            .values('month')
            .annotate(total=Sum('amount'))
            .order_by('month')[:6]
        )

        raw_repayments = (
            Repayment.objects.all()
            .annotate(month=TruncMonth('date'))
            .values('month')
            .annotate(total=Sum('amount_paid'))
            .order_by('month')[:6]
        )

        months_set = sorted(list(set(
            [entry['month'].strftime('%b %Y') for entry in raw_savings if entry['month']] +
            [entry['month'].strftime('%b %Y') for entry in raw_repayments if entry['month']]
        )))

        if not months_set:
            months_set = ["No Data Yet"]
            disbursements_list = [0]
            recoveries_list = [0]
        else:
            savings_dict = {entry['month'].strftime('%b %Y'): float(entry['total']) for entry in raw_savings if entry['month']}
            repay_dict = {entry['month'].strftime('%b %Y'): float(entry['total']) for entry in raw_repayments if entry['month']}
            
            for m in months_set:
                disbursements_list.append(savings_dict.get(m, 0.0))
                recoveries_list.append(repay_dict.get(m, 0.0))

        cashflow_data = {
            "months": months_set,
            "disbursements": disbursements_list,
            "recoveries": recoveries_list
        }

        portfolio_data = {
            "labels": ["Approved", "Pending", "Rejected", "Completed"],
            "series": [
                Loan.objects.filter(status=Loan.Status.APPROVED).count(),
                Loan.objects.filter(status=Loan.Status.PENDING).count(),
                Loan.objects.filter(status=Loan.Status.REJECTED).count(),
                Loan.objects.filter(status=Loan.Status.COMPLETED).count(),
            ]
        }

        grade_distribution_data = {
            "categories": ["Members", "Users"],
            "series": [
                Member.objects.filter(role=Member.Role.MEMBER).count(),
                Member.objects.filter(role=Member.Role.USER).count(),
            ]
        }

        payload = {
            "kpis": {
                "total_capital": {"value": float(total_capital)},
                "active_loans": {"value": active_loans},
                "total_members": {"value": total_members},
                "default_rate": {"value": default_rate},
                "latest_session_status": {"value": session_status} # INJECTED HERE
            },
            "charts": {
                "cashflow": cashflow_data,
                "portfolio": portfolio_data,
                "grade_distribution": grade_distribution_data
            }
        }
        return Response(payload)


# ==========================================
# 3. Collection & Rental API
# ==========================================
class AdminCollectionAPI(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        collections_qs = WeeklyCollection.objects.select_related('member__user').order_by('-payment_date')[:50]
        total = WeeklyCollection.objects.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        collections_list = []
        for col in collections_qs:
            username = getattr(col.member.user, 'username', 'Unknown') if col.member and col.member.user else 'Unknown'
            collections_list.append({
                'id': col.id,
                'member_id': col.member.id if col.member else None,
                'member_username': username,
                'amount': float(col.amount),
                'payment_date': col.payment_date.strftime('%Y-%m-%d %H:%M') if col.payment_date else ''
            })

        member_totals = WeeklyCollection.objects.values('member__id', 'member__user__username').annotate(total=Sum('amount')).order_by('-total')[:20]
        
        return Response({
            'total_collections': float(total),
            'member_totals': [{'member_id': item['member__id'], 'username': item['member__user__username'], 'total': float(item['total'] or 0)} for item in member_totals],
            'collections': collections_list 
        })

    def post(self, request):
        serializer = WeeklyCollectionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminRentalItemAPI(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        items = RentalItem.objects.order_by('-id')
        
        rental_items_data = []
        for item in items:
            fee = getattr(item, 'rental_fee', None) or getattr(item, 'rental_price', Decimal('0.00'))
            deposit = getattr(item, 'deposit_fee', Decimal('0.00'))
            
            is_avail = getattr(item, 'is_available', None)
            if is_avail is None:
                is_avail = getattr(item, 'available', True)

            rental_items_data.append({
                'id': item.id,
                'name': item.name,
                'description': item.description,
                'rental_fee': str(fee),
                'rental_price': str(fee),
                'deposit_fee': str(deposit),
                'is_available': bool(is_avail)
            })

        requests_qs = RentalRequest.objects.select_related('member__user', 'item').order_by('-created_at')
        rental_history = [{
            'id': req.id,
            'member_name': req.member.user.username if req.member and req.member.user else 'Unknown',
            'item_name': req.item.name if req.item else 'Unknown',
            'rental_fee': str(getattr(req.item, 'rental_fee', getattr(req.item, 'rental_price', '0.00'))) if req.item else '0.00',
            'deposit_fee': str(getattr(req.item, 'deposit_fee', '0.00')) if req.item else '0.00',
            'start_date': req.start_date.strftime('%Y-%m-%d') if req.start_date else '',
            'end_date': req.end_date.strftime('%Y-%m-%d') if req.end_date else '',
            'status': req.status,
            'created_at': req.created_at.strftime('%Y-%m-%d %H:%M') if req.created_at else ''
        } for req in requests_qs]

        return Response({
            'count': items.count(),
            'rental_items': rental_items_data,
            'rental_history': rental_history
        }, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data.copy()
        fee = data.get('rental_price') or data.get('rental_fee', '0.00')
        data['rental_fee'] = fee
        
        serializer = RentalItemSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'status': 'success',
                'message': 'Rental item created successfully.',
                'rental_item': serializer.data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminRentalItemDetailAPI(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        try:
            item = RentalItem.objects.get(pk=pk)
        except RentalItem.DoesNotExist:
            return Response({'error': 'Rental item not found.'}, status=status.HTTP_404_NOT_FOUND)
        
        data = request.data.copy()
        if 'rental_price' in data:
            data['rental_fee'] = data['rental_price']

        serializer = RentalItemSerializer(item, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'status': 'success',
                'message': 'Rental item updated successfully.',
                'rental_item': serializer.data
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        try:
            item = RentalItem.objects.get(pk=pk)
        except RentalItem.DoesNotExist:
            return Response({'error': 'Rental item not found.'}, status=status.HTTP_404_NOT_FOUND)
        
        item.delete()
        return Response({
            'status': 'success',
            'message': 'Rental item deleted successfully.'
        }, status=status.HTTP_200_OK)


# ==========================================
# Dedicated Meeting API
# ==========================================
class AdminMeetingAPI(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        meetings = Meeting.objects.annotate(
            total_attendance=Count('attendance_records'),
            present_count=Count('attendance_records', filter=Q(attendance_records__status=AttendanceRecord.Status.PRESENT))
        ).order_by('-date')
        serializer = MeetingSerializer(meetings, many=True)
        return Response({'meetings': serializer.data})

    def post(self, request):
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        
        # Strip time component to fit DateField format (YYYY-MM-DD)
        if 'date' in data and data['date']:
            data['date'] = str(data['date']).split('T')[0]

        serializer = MeetingSerializer(data=data)
        if serializer.is_valid():
            serializer.save(created_by=request.user)
            return Response({
                'success': True,
                'message': 'Meeting created successfully',
                'meeting': serializer.data
            }, status=status.HTTP_201_CREATED)
            
        error_msg = "; ".join([f"{k}: {', '.join(v)}" for k, v in serializer.errors.items()])
        return Response({'error': error_msg, 'details': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request):
        meeting_id = request.query_params.get('id') or request.data.get('id')
        
        if not meeting_id:
            return Response({'error': 'Meeting ID is required for updating.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            meeting = Meeting.objects.get(id=meeting_id)
        except Meeting.DoesNotExist:
            return Response({'error': 'Meeting not found.'}, status=status.HTTP_404_NOT_FOUND)

        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        
        # Strip time component to fit DateField format (YYYY-MM-DD)
        if 'date' in data and data['date']:
            data['date'] = str(data['date']).split('T')[0]

        serializer = MeetingSerializer(meeting, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'message': 'Meeting updated successfully',
                'meeting': serializer.data
            }, status=status.HTTP_200_OK)
            
        error_msg = "; ".join([f"{k}: {', '.join(v)}" for k, v in serializer.errors.items()])
        return Response({'error': error_msg, 'details': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request):
        meeting_id = request.query_params.get('id')
        
        if not meeting_id:
            return Response({'error': 'Meeting ID is required for deletion.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            meeting = Meeting.objects.get(id=meeting_id)
            meeting.delete()
            return Response({'message': 'Meeting deleted successfully'}, status=status.HTTP_200_OK)
        except Meeting.DoesNotExist:
            return Response({'error': 'Meeting not found.'}, status=status.HTTP_404_NOT_FOUND)

# ==========================================
# 5. Dedicated Attendance API
# ==========================================
class AdminAttendanceAPI(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        meeting_id = request.query_params.get('meeting_id')
        attendance = AttendanceRecord.objects.select_related('member__user', 'meeting').order_by('-date')
        
        if meeting_id:
            attendance = attendance.filter(meeting_id=meeting_id)

        attendance = attendance[:50]
        serializer = AttendanceRecordSerializer(attendance, many=True)

        fined_records = AttendanceRecord.objects.filter(fine_amount__gt=0).select_related('member__user', 'meeting').order_by('-date')
        fined_serializer = AttendanceRecordSerializer(fined_records, many=True)

        absent_total = AttendanceRecord.objects.filter(status=AttendanceRecord.Status.ABSENT).aggregate(total=Sum('fine_amount'))['total'] or Decimal('0.00')
        absent_count = AttendanceRecord.objects.filter(status=AttendanceRecord.Status.ABSENT).count()
        
        return Response({
            'absent_total_fines': float(absent_total),
            'absent_count': absent_count,
            'records': serializer.data,
            'fined_records': fined_serializer.data,
            'status_options': [
                {'value': AttendanceRecord.Status.PRESENT, 'label': 'Present'},
                {'value': AttendanceRecord.Status.ABSENT, 'label': 'Absent'},
                {'value': AttendanceRecord.Status.LATE, 'label': 'Late'},
                {'value': AttendanceRecord.Status.EXCUSED, 'label': 'Excused'},
                {'value': AttendanceRecord.Status.ON_LEAVE, 'label': 'On Leave'},
            ]
        })

    def post(self, request):
        attendance_rows = request.data.get('attendance', [])
        
        if not attendance_rows:
            return Response({'error': 'No attendance rows provided.'}, status=status.HTTP_400_BAD_REQUEST)

        saved_records = []
        for row in attendance_rows:
            member_id = row.get('member')
            meeting_id = row.get('meeting')
            status_val = row.get('status')
            fine_amount = row.get('fine_amount', 0)

            if not member_id or not meeting_id:
                continue

            try:
                meeting = Meeting.objects.get(id=meeting_id)
                meeting_date = meeting.date
            except Meeting.DoesNotExist:
                continue

            # AUTOMATED FINE GENERATION
            try:
                fine_val = Decimal(str(fine_amount)) if fine_amount else Decimal('0.00')
            except (ValueError, TypeError):
                fine_val = Decimal('0.00')

            if status_val == AttendanceRecord.Status.ABSENT and fine_val == 0:
                fine_amount = Decimal('50.00')  # Default fine configuration

            record, created = AttendanceRecord.objects.update_or_create(
                member_id=member_id,
                date=meeting_date,
                defaults={
                    'meeting': meeting,
                    'status': status_val,
                    'fine_amount': fine_amount
                }
            )
            saved_records.append(record)

        serializer = AttendanceRecordSerializer(saved_records, many=True)
        return Response({'message': 'Attendance successfully recorded', 'attendance': serializer.data}, status=status.HTTP_201_CREATED)

    def patch(self, request):
        record_id = request.data.get('record_id')
        if not record_id:
            return Response({'error': 'Record ID required.'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            record = AttendanceRecord.objects.get(id=record_id)
            record.is_paid = not record.is_paid
            record.save()
            return Response({'message': 'Payment status updated successfully', 'is_paid': record.is_paid}, status=status.HTTP_200_OK)
        except AttendanceRecord.DoesNotExist:
            return Response({'error': 'Fine record not found.'}, status=status.HTTP_404_NOT_FOUND)


class MemberAttendanceAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            member = Member.objects.get(user=request.user)
        except Member.DoesNotExist:
            return Response({'detail': 'Member profile not found.'}, status=status.HTTP_404_NOT_FOUND)
        
        records = AttendanceRecord.objects.filter(member=member).select_related('meeting').order_by('-date')
        serializer = AttendanceRecordSerializer(records, many=True)
        
        present_count = records.filter(status=AttendanceRecord.Status.PRESENT).count()
        absent_count = records.filter(status=AttendanceRecord.Status.ABSENT).count()
        total_fines = records.filter(status=AttendanceRecord.Status.ABSENT).aggregate(total=Sum('fine_amount'))['total'] or Decimal('0.00')

        return Response({
            'present_count': present_count,
            'absent_count': absent_count,
            'total_fines': float(total_fines),
            'records': serializer.data
        })


# ==========================================
# 6. Admin Finance API
# ==========================================
class AdminFinanceAPI(View):
    def get(self, request):
        # DATE FILTERING
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')

        transactions_qs = IncomeExpense.objects.all()

        if start_date:
            transactions_qs = transactions_qs.filter(date__gte=start_date)
        if end_date:
            transactions_qs = transactions_qs.filter(date__lte=end_date)

        transactions = transactions_qs.order_by('-date', '-id')
        
        tx_list = []
        total_income = 0.0
        total_expense = 0.0

        for tx in transactions:
            amt = float(tx.amount or 0)
            entry_type = getattr(tx, 'entry_type', '')
            
            if entry_type in [IncomeExpense.EntryType.INCOME, 'IN', 'income', 'Income']:
                tx_type = 'IN'
                total_income += amt
            else:
                tx_type = 'EX'
                total_expense += amt

            tx_list.append({
                'id': tx.id,
                'title': getattr(tx, 'description', 'Untitled'),
                'category': getattr(tx, 'category', 'General'),
                'tx_type': tx_type,
                'amount': amt,
                'date': tx.date.strftime('%Y-%m-%d') if tx.date else ''
            })

        net_balance = total_income - total_expense

        return JsonResponse({
            'transactions': tx_list,
            'total_income': total_income,
            'total_expense': total_expense,
            'net_balance': net_balance
        }, safe=False)

    def post(self, request):
        try:
            data = json.loads(request.body)
            tx_type_input = data.get('tx_type')
            
            entry_type = IncomeExpense.EntryType.INCOME if tx_type_input == 'IN' else IncomeExpense.EntryType.EXPENSE

            IncomeExpense.objects.create(
                entry_type=entry_type,
                description=data.get('title') or data.get('description', ''),
                category=data.get('category'),
                amount=data.get('amount'),
                date=data.get('date')
            )
            return JsonResponse({'status': 'success'}, status=201)
        except Exception as e:
            return JsonResponse({'detail': str(e)}, status=400)


# ==========================================
# 7. Admin Report API
# ==========================================
class AdminReportAPI(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        # DATE FILTERING
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        collections_qs = WeeklyCollection.objects.all()
        income_expense_qs = IncomeExpense.objects.all()
        attendance_qs = AttendanceRecord.objects.all()

        if start_date:
            collections_qs = collections_qs.filter(payment_date__gte=start_date)
            income_expense_qs = income_expense_qs.filter(date__gte=start_date)
            attendance_qs = attendance_qs.filter(date__gte=start_date)
        if end_date:
            collections_qs = collections_qs.filter(payment_date__lte=end_date)
            income_expense_qs = income_expense_qs.filter(date__lte=end_date)
            attendance_qs = attendance_qs.filter(date__lte=end_date)

        total_collections = collections_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        total_income = income_expense_qs.filter(entry_type=IncomeExpense.EntryType.INCOME).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        total_expense = income_expense_qs.filter(entry_type=IncomeExpense.EntryType.EXPENSE).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        absent_count = attendance_qs.filter(status=AttendanceRecord.Status.ABSENT).count()
        fine_total = attendance_qs.filter(status=AttendanceRecord.Status.ABSENT).aggregate(total=Sum('fine_amount'))['total'] or Decimal('0.00')

        total_members_count = Member.objects.count()
        members_with_collections = collections_qs.values('member').distinct().count()
        compliance_rate = round((members_with_collections / total_members_count * 100), 1) if total_members_count > 0 else 0.0

        weekly_collections = (
            collections_qs
            .annotate(week=TruncWeek('payment_date'))
            .values('week')
            .annotate(total=Sum('amount'))
            .order_by('week')[:8]
        )
        
        weekly_collection_reports = [
            {
                'week': item['week'].strftime('%V') if item['week'] else '1',
                'total': float(item['total'] or 0)
            }
            for item in weekly_collections
        ]

        expense_categories = (
            income_expense_qs.filter(entry_type=IncomeExpense.EntryType.EXPENSE)
            .values('category')
            .annotate(actual=Sum('amount'))
            .order_by('-actual')
        )
        
        budget_variances = []
        for cat in expense_categories:
            actual_amt = float(cat['actual'] or 0)
            dynamic_budget = round(actual_amt * 1.25, 2)
            budget_variances.append({
                'category': cat['category'] or 'General Expense',
                'actual': actual_amt,
                'budget': dynamic_budget
            })

        top_contributors_qs = (
            collections_qs
            .values('member__user__first_name', 'member__user__last_name', 'member__user__username')
            .annotate(total=Sum('amount'))
            .order_by('-total')[:5]
        )
        
        top_contributors = [
            {
                'name': f"{item['member__user__first_name']} {item['member__user__last_name']}".strip() or item['member__user__username'] or 'Anonymous Member',
                'total': float(item['total'] or 0)
            }
            for item in top_contributors_qs
        ]

        finance_entries = income_expense_qs.order_by('-date', '-created_at')[:10]
        finance_serializer = IncomeExpenseSerializer(finance_entries, many=True)

        return Response({
            'total_collections': float(total_collections),
            'total_income': float(total_income),
            'total_expense': float(total_expense),
            'net_balance': float(total_income - total_expense),
            'absent_count': absent_count,
            'total_fines': float(fine_total),
            'compliance_rate': compliance_rate,
            'weekly_collection_report': weekly_collection_reports,
            'budget_variances': budget_variances,
            'top_contributors': top_contributors,
            'latest_finance_entries': finance_serializer.data
        })


# ==========================================
# 8. Chat APIs
# ==========================================
class AdminChatRoomsAPI(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        members = Member.objects.exclude(user__is_superuser=True).select_related('user').order_by('user__username')
        rooms_payload = []

        for member in members:
            room, _ = ChatRoom.objects.get_or_create(member=member)
            last_message = room.messages.order_by('-created_at').first()
            rooms_payload.append({
                'member_id': member.id,
                'username': member.user.username if member.user else 'Unknown',
                'full_name': member.user.get_full_name() if member.user else 'Unnamed',
                'role': member.role,
                'last_message': last_message.content if last_message else '',
                'last_sender': last_message.sender if last_message else '',
                'last_at': last_message.created_at.strftime('%Y-%m-%d %H:%M') if last_message else ''
            })

        return Response({'chat_rooms': rooms_payload})


class AdminChatRoomAPI(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, member_id):
        try:
            member = Member.objects.get(pk=member_id)
        except Member.DoesNotExist:
            return Response({'error': 'Member not found'}, status=status.HTTP_404_NOT_FOUND)

        room, _ = ChatRoom.objects.get_or_create(member=member)
        messages = [
            {
                'id': msg.id,
                'sender': msg.sender,
                'content': msg.content,
                'created_at': msg.created_at.strftime('%Y-%m-%d %H:%M')
            }
            for msg in room.messages.order_by('created_at')
        ]
        return Response({
            'member_id': member.id,
            'username': member.user.username if member.user else 'Unknown',
            'full_name': member.user.get_full_name() if member.user else 'Unnamed',
            'messages': messages
        })

    def post(self, request, member_id):
        content = request.data.get('content')
        if not content:
            return Response({'error': 'Message content is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            member = Member.objects.get(pk=member_id)
        except Member.DoesNotExist:
            return Response({'error': 'Member not found'}, status=status.HTTP_404_NOT_FOUND)

        room, _ = ChatRoom.objects.get_or_create(member=member)
        msg = ChatMessage.objects.create(room=room, sender=ChatMessage.SenderType.ADMIN, content=content)
        Notification.objects.create(member=member, message=f"Admin sent a new message: {content[:120]}")

        return Response({
            'id': msg.id,
            'sender': msg.sender,
            'content': msg.content,
            'created_at': msg.created_at.strftime('%Y-%m-%d %H:%M')
        }, status=status.HTTP_201_CREATED)


class AdminChatSendAPI(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        member_id = request.data.get('member_id')
        content = request.data.get('message')
        
        if not member_id or not content:
            return Response({'error': 'Member ID and message content are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            member = Member.objects.get(pk=member_id)
        except Member.DoesNotExist:
            return Response({'error': 'Member not found'}, status=status.HTTP_404_NOT_FOUND)

        room, _ = ChatRoom.objects.get_or_create(member=member)
        msg = ChatMessage.objects.create(room=room, sender=ChatMessage.SenderType.ADMIN, content=content)
        Notification.objects.create(member=member, message=f"Admin sent a new message: {content[:120]}")

        return Response({
            'status': 'success',
            'id': msg.id,
            'sender': msg.sender,
            'content': msg.content,
            'timestamp': msg.created_at.strftime('%Y-%m-%d %H:%M')
        }, status=status.HTTP_201_CREATED)


# ==========================================
# 9. Functional API Endpoints & CRUD Views
# ==========================================

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_member_list_api(request):
    members = Member.objects.all().order_by('-id')
    serializer = MemberSerializer(members, many=True)
    return Response({
        "count": members.count(),
        "members": serializer.data
    })

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_loan_list_api(request):
    loans = Loan.objects.all().order_by('-id')
    total_disbursed = loans.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    active_exposure = loans.filter(status=Loan.Status.APPROVED).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    defaulted_exposure = loans.filter(status=Loan.Status.REJECTED).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    serializer = LoanApplicationSerializer(loans, many=True)
    
    return Response({
        "metrics": {
            "total_disbursed": float(total_disbursed),
            "active_exposure": float(active_exposure),
            "defaulted_exposure": float(defaulted_exposure),
            "count": loans.count()
        },
        "loans": serializer.data
    })


class MemberDetailAPI(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        User = get_user_model()
        data = request.data.copy()
        full_name = data.get('full_name', '').strip()
        email = data.get('email', '').strip()
        role_value = data.get('role', 'MEMBER').strip().upper()

        username_base = email.split('@')[0] if email else full_name.split(' ')[0].lower() if full_name else 'member'
        username = username_base or 'member'
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{username_base}{counter}"
            counter += 1

        first_name = ''
        last_name = ''
        if full_name:
            parts = full_name.split(' ', 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ''

        user = User.objects.create(username=username, email=email)
        user.first_name = first_name
        user.last_name = last_name
        user.set_unusable_password()
        
        if role_value == 'ADMIN':
            user.is_staff = True
            user.is_superuser = True
        user.save()
        
        return Response({'status': 'success', 'username': username}, status=status.HTTP_201_CREATED)


# ==========================================
# 10. Loan Detail API
# ==========================================
class LoanDetailAPI(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        try:
            loan = Loan.objects.get(pk=pk)
        except Loan.DoesNotExist:
            return Response({"error": "Loan not found"}, status=status.HTTP_404_NOT_FOUND)
        
        data = request.data.copy()
        
        if 'status' in data and isinstance(data['status'], str):
            new_status = data['status'].lower()
            
            # STRICT STATUS TRANSITION VALIDATION
            if loan.status == Loan.Status.COMPLETED and new_status != Loan.Status.COMPLETED:
                return Response({"error": "Cannot change the status of an already completed loan."}, status=status.HTTP_400_BAD_REQUEST)
            if loan.status == Loan.Status.REJECTED and new_status == Loan.Status.PENDING:
                return Response({"error": "Cannot revert a rejected loan back to pending."}, status=status.HTTP_400_BAD_REQUEST)

            data['status'] = new_status
            
        serializer = LoanApplicationSerializer(loan, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        try:
            loan = Loan.objects.get(pk=pk)
        except Loan.DoesNotExist:
            return Response({"error": "Loan not found"}, status=status.HTTP_404_NOT_FOUND)
        
        loan.delete()
        return Response({"message": "Loan deleted successfully"}, status=status.HTTP_204_NO_CONTENT)