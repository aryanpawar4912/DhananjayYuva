import os
import json
import datetime
from decimal import Decimal, InvalidOperation
from datetime import timedelta
from dateutil.relativedelta import relativedelta
import razorpay

from django.conf import settings
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth, TruncWeek
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from rest_framework import status, permissions
from rest_framework.views import APIView, View
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser

# Local imports with safe fallbacks
try:
    from .models import (
        Member, Loan, RentalRequest, SavingsTransaction, Repayment, ChatRoom, 
        ChatMessage, AdminNotice, WeeklyCollection, AttendanceRecord, IncomeExpense, 
        Notification, Meeting, RentalItem, Document, LoanInstallment
    )
except ImportError:
    from yuva.models import (
        Member, Loan, RentalRequest, SavingsTransaction, Repayment, ChatRoom, 
        ChatMessage, AdminNotice, WeeklyCollection, AttendanceRecord, IncomeExpense, 
        Notification, Meeting, RentalItem, Document, LoanInstallment
    )

try:
    from .forms import LoginForm, MemberRegistrationForm
except ImportError:
    LoginForm = None
    MemberRegistrationForm = None

try:
    from .serializers import (
        MemberSerializer, LoanApplicationSerializer, WeeklyCollectionSerializer,
        MeetingSerializer, AttendanceRecordSerializer, IncomeExpenseSerializer,
        RentalItemSerializer
    )
except ImportError:
    from yuva_admin.serializers import (
        MemberSerializer, LoanApplicationSerializer, WeeklyCollectionSerializer,
        MeetingSerializer, AttendanceRecordSerializer, IncomeExpenseSerializer,
        RentalItemSerializer
    )

User = get_user_model()


# ==========================================
# HELPER: ROLE-BASED ACCESS CONTROL
# ==========================================
def is_basic_user(member):
    """
    Checks if a member profile is restricted to basic user features.
    Basic users lack full member operations like Savings, Attendance, and Dashboard.
    """
    if not member:
        return True
    role = str(getattr(member, 'role', '')).lower().strip()
    return role in ['user', 'basic', 'pending', '']


# ==========================================
# 0. AUTHENTICATION VIEWS
# ==========================================
def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == 'POST':
        if LoginForm:
            form = LoginForm(request, data=request.POST) 
            if form.is_valid():
                user = form.get_user()
                login(request, user)
                return redirect('dashboard')
        else:
            return redirect('login')
    else:
        form = LoginForm() if LoginForm else None
    return render(request, 'member/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


def signup_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == 'POST':
        if MemberRegistrationForm:
            form = MemberRegistrationForm(request.POST)
            if form.is_valid():
                user = form.save()
                login(request, user)
                return redirect('dashboard')
        else:
            return redirect('login')
    else:
        form = MemberRegistrationForm() if MemberRegistrationForm else None
        
    return render(request, 'member/signup.html', {'form': form})


# ==========================================
# 1. MEMBER TEMPLATE VIEWS
# ==========================================
@login_required
def member_dashboard(request): 
    member = Member.objects.filter(user=request.user).first()
    if is_basic_user(member):
        return redirect('profile')
    return render(request, 'member/dashboard.html', {'member': member})

@login_required
def member_chat_view(request): 
    return render(request, 'member/chat.html')

@login_required
def member_savings_view(request): 
    member = Member.objects.filter(user=request.user).first()
    if is_basic_user(member):
        return redirect('profile')
    return render(request, 'member/savings.html')

@login_required
@ensure_csrf_cookie  
def member_loans_view(request): 
    return render(request, 'member/loans.html')

@login_required
def member_profile(request): 
    return render(request, 'member/profile.html')

@login_required
def request_loan(request): 
    return render(request, 'member/request_loan.html')

@login_required
def member_passbook_view(request):
    member = Member.objects.filter(user=request.user).first()
    if not member:
        return render(request, 'member/passbook.html', {'error': 'No associated member profile found.'})

    return render(request, 'member/passbook.html', {'member': member})

@login_required
def member_attendance_view(request):
    member = Member.objects.filter(user=request.user).first()
    if is_basic_user(member):
        return redirect('profile')
    return render(request, 'member/attendance.html')

@login_required
def member_rentals_view(request):
    return render(request, 'member/rentals.html')


# ==========================================
# 2. MEMBER API VIEWS
# ==========================================
class DashboardAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member = Member.objects.filter(user=request.user).first()
        if is_basic_user(member):
            return Response({'error': 'Dashboard access is restricted to full members.'}, status=status.HTTP_403_FORBIDDEN)
            
        if not member:
            return Response({'error': 'Member not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # 1. Core Metrics
        deposits = SavingsTransaction.objects.filter(member=member, transaction_type__iexact='deposit').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        withdrawals = SavingsTransaction.objects.filter(member=member, transaction_type__iexact='withdrawal').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        total_savings = deposits - withdrawals
                
        active_loans_count = Loan.objects.filter(member=member, status__iexact='approved').count()
        recent_savings = SavingsTransaction.objects.filter(member=member).order_by('-date')[:5]
        
        tx_data = [{
            'transaction_type': f"Savings {str(t.transaction_type or 'deposit').capitalize()}",
            'amount': str(t.amount or Decimal('0.00')),
            'date': t.date.strftime("%Y-%m-%d %H:%M") if t.date else "N/A"
        } for t in recent_savings]

        # 2. Dynamic 6-Month Chart Aggregation
        chart_labels = []
        chart_savings = []
        chart_loans = []
        
        # Truncate time to midnight for month boundaries
        current_time = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        for i in range(5, -1, -1):
            month_target = current_time - relativedelta(months=i)
            chart_labels.append(month_target.strftime('%b'))
            
            next_month = month_target + relativedelta(months=1)
            
            past_savings = SavingsTransaction.objects.filter(member=member, date__lt=next_month)
            month_dep = past_savings.filter(transaction_type__iexact='deposit').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            month_wth = past_savings.filter(transaction_type__iexact='withdrawal').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            
            monthly_loan_sum = Loan.objects.filter(
                member=member,
                date__lt=next_month,
                status__iexact='approved'
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            
            chart_savings.append(float(month_dep - month_wth))
            chart_loans.append(float(monthly_loan_sum))

        return Response({
            'total_savings': float(round(total_savings, 2)),
            'share_capital': float(round(total_savings * Decimal('0.1'), 2)),  
            'credit_standing': 'Grade A+',
            'active_loans_count': active_loans_count,
            'recent_transactions': tx_data,
            'chart_labels': chart_labels,
            'chart_savings': chart_savings,
            'chart_loans': chart_loans
        })


class SavingsAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member = Member.objects.filter(user=request.user).first()
        if is_basic_user(member):
            return Response({'error': 'Savings features are restricted to full members.'}, status=status.HTTP_403_FORBIDDEN)
            
        savings = SavingsTransaction.objects.filter(member=member).order_by('date')
        running_balance = Decimal('0.00')
        data = []
        for s in savings:
            amount = s.amount or Decimal('0.00')
            tx_type = str(s.transaction_type or 'deposit').lower()
            running_balance += amount if tx_type == 'deposit' else -amount
            
            data.append({
                'id': s.id,
                'amount': str(amount),
                'transaction_type': tx_type,
                'running_balance': str(running_balance),
                'date': s.date.strftime("%Y-%m-%d %H:%M") if s.date else "N/A"
            })
        return Response(list(reversed(data)))

    def post(self, request):
        member = Member.objects.filter(user=request.user).first()
        if is_basic_user(member):
            return Response({'error': 'Savings features are restricted to full members.'}, status=status.HTTP_403_FORBIDDEN)
            
        try:
            amount = Decimal(str(request.data.get('amount', 0)))
            if amount <= 0:
                raise ValueError
        except (ValueError, InvalidOperation, TypeError):
            return Response({'error': 'A valid positive amount is required'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            SavingsTransaction.objects.create(member=member, amount=amount, transaction_type='deposit')
            Notification.objects.create(member=member, message=f"Successfully deposited ₹{amount} to your savings ledger.")
            
        return Response({'message': 'Savings deposit recorded successfully.'})


class LoansAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response({'error': 'Profile not found.'}, status=status.HTTP_404_NOT_FOUND)
        
        loans = Loan.objects.filter(member=member).order_by('-date')
        data = []
        
        for loan in loans:
            installments = LoanInstallment.objects.filter(loan=loan).order_by('id')
            inst_data = [{
                'installment_number': idx + 1, 
                'due_date': inst.due_date.strftime("%Y-%m-%d") if getattr(inst, 'due_date', None) else "N/A",
                'principal_amount': str(getattr(inst, 'principal_amount', 0)),
                'interest_amount': str(getattr(inst, 'interest_amount', 0)),
                'total_amount': str(getattr(inst, 'total_amount', loan.emi_amount)),
                'is_paid': inst.is_paid
            } for idx, inst in enumerate(installments)]
            
            data.append({
                'id': loan.id,
                'amount': str(loan.amount),
                'interest_rate': str(loan.interest_rate),
                'tenure_months': loan.tenure_months,
                'emi_amount': str(loan.emi_amount),
                'status': loan.status,
                'date': loan.date.strftime("%Y-%m-%d %H:%M") if getattr(loan, 'date', None) else "N/A",
                'installments': inst_data
            })
            
        return Response(data)
        
    def post(self, request):
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response({'error': 'No profile found.'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            amount = Decimal(str(request.data.get('amount', 0)))
            tenure_months = int(request.data.get('tenure_months', 12))
            if amount <= 0 or tenure_months <= 0:
                raise ValueError
        except (ValueError, InvalidOperation, TypeError):
            return Response({'error': 'Valid positive amount and tenure are required'}, status=status.HTTP_400_BAD_REQUEST)
            
        with transaction.atomic():
            loan = Loan.objects.create(member=member, amount=amount, tenure_months=tenure_months, status='pending')
            Notification.objects.create(
                member=member, 
                message=f"Your loan request for ₹{amount} has been submitted. Estimated EMI: ₹{loan.emi_amount}/month."
            )
        return Response({'message': 'Loan requested successfully!', 'estimated_emi': str(loan.emi_amount)}, status=status.HTTP_201_CREATED)


class ProfileAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response({'error': 'Profile not found.'}, status=status.HTTP_404_NOT_FOUND)
            
        fields = [
            member.name,
            getattr(member, 'gender', ''),
            request.user.email,
            member.phone,
            member.village,
            member.address
        ]
        filled = sum(1 for f in fields if f and str(f).strip())
        profile_completion = int((filled / len(fields)) * 100)
        
        updated_at_str = member.updated_at.strftime("%b %d, %Y, %I:%M %p") if getattr(member, 'updated_at', None) else None

        return Response({
            'username': request.user.username,
            'email': request.user.email,
            'name': getattr(member, 'name', '') or '',
            'gender': getattr(member, 'gender', '') or '',
            'phone': member.phone,
            'village': member.village,
            'address': member.address,
            'role': member.role,
            'profile_completion': profile_completion,
            'updated_at': updated_at_str
        })
        
    def post(self, request):
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response({'error': 'Profile not found.'}, status=status.HTTP_404_NOT_FOUND)
            
        email = request.data.get('email')
        if email and email.strip() != request.user.email:
            email_clean = email.strip()
            try:
                validate_email(email_clean)
            except ValidationError:
                return Response({'error': 'Invalid email address format.'}, status=status.HTTP_400_BAD_REQUEST)
                
            if User.objects.filter(email__iexact=email_clean).exclude(pk=request.user.pk).exists():
                return Response({'error': 'An account with this email address already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            if 'name' in request.data and hasattr(member, 'name'):
                member.name = request.data.get('name', '')
            if 'gender' in request.data and hasattr(member, 'gender'):
                member.gender = request.data.get('gender', '')

            member.phone = request.data.get('phone', member.phone)
            member.village = request.data.get('village', member.village)
            member.address = request.data.get('address', member.address)
                
            member.save() 
            
            if email and email.strip() != request.user.email:
                request.user.email = email.strip()
                request.user.save()

        fields = [
            getattr(member, 'name', ''),
            getattr(member, 'gender', ''),
            request.user.email,
            member.phone,
            member.village,
            member.address
        ]
        filled = sum(1 for f in fields if f and str(f).strip())
        profile_completion = int((filled / len(fields)) * 100)

        updated_at_str = member.updated_at.strftime("%b %d, %Y, %I:%M %p") if getattr(member, 'updated_at', None) else "Just now"

        return Response({
            'message': 'Profile updated successfully!',
            'profile_completion': profile_completion,
            'updated_at': updated_at_str
        })


class MemberAttendanceAPI(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # Admin override capability using ?member_id=<id>
        target_member_id = request.query_params.get('member_id')
        
        if (request.user.is_staff or request.user.is_superuser) and target_member_id:
            try:
                member = Member.objects.get(pk=target_member_id)
            except Member.DoesNotExist:
                return Response({'error': 'Target member profile not found.'}, status=status.HTTP_404_NOT_FOUND)
        else:
            member = Member.objects.filter(user=request.user).first()
            if not member:
                return Response({'detail': 'Member profile not found.'}, status=status.HTTP_404_NOT_FOUND)

            if is_basic_user(member) and not (request.user.is_staff or request.user.is_superuser):
                return Response({'error': 'Attendance records are restricted to full members.'}, status=status.HTTP_403_FORBIDDEN)
        
        records = AttendanceRecord.objects.filter(member=member).select_related('meeting').order_by('-date')
        serializer = AttendanceRecordSerializer(records, many=True)
        
        present_val = getattr(getattr(AttendanceRecord, 'Status', None), 'PRESENT', 'present')
        absent_val = getattr(getattr(AttendanceRecord, 'Status', None), 'ABSENT', 'absent')

        present_count = records.filter(status__iexact=str(present_val)).count()
        absent_records = records.filter(status__iexact=str(absent_val))
        absent_count = absent_records.count()
        total_fines = absent_records.aggregate(total=Sum('fine_amount'))['total'] or Decimal('0.00')

        return Response({
            'member_id': member.id,
            'role': getattr(member, 'role', ''),
            'present_count': present_count,
            'absent_count': absent_count,
            'total_fines': float(total_fines),
            'records': serializer.data
        })


class MemberRentalDirectoryAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        items = RentalItem.objects.filter(Q(is_active=True) | Q(is_available=True) if hasattr(RentalItem, 'is_active') else Q(is_available=True))
        items_data = [{
            'id': item.id,
            'name': item.name,
            'description': item.description,
            'rental_fee': str(getattr(item, 'rental_fee', getattr(item, 'rental_price', '0.00'))),
            'deposit_fee': str(getattr(item, 'deposit_fee', '0.00')),
            'available_quantity': getattr(item, 'available_quantity', 1),
            'image_url': item.image.url if getattr(item, 'image', None) else None
        } for item in items]
        
        user_requests = RentalRequest.objects.filter(member__user=request.user).order_by('-created_at')
        requests_data = [{
            'id': req.id,
            'item_name': req.item.name if req.item else 'Unknown',
            'start_date': req.start_date.strftime('%Y-%m-%d') if getattr(req, 'start_date', None) else "N/A",
            'end_date': req.end_date.strftime('%Y-%m-%d') if getattr(req, 'end_date', None) else "N/A",
            'status': req.status,
            'created_at': req.created_at.strftime('%Y-%m-%d %H:%M') if getattr(req, 'created_at', None) else "N/A"
        } for req in user_requests]

        return Response({
            'catalog': items_data,
            'my_requests': requests_data
        })


class RepaymentsAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)
            
        repayments = Repayment.objects.filter(loan__member=member).order_by('-date').values('loan__id', 'amount_paid', 'date')
        return Response(list(repayments))


class NotificationsAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)

        notifications = []
        
        for note in Notification.objects.filter(member=member):
            notifications.append({
                'id': note.id,
                'message': note.message,
                'type': 'notification',
                'is_read': getattr(note, 'is_read', False),
                'raw_created_at': note.created_at
            })

        active_notices = AdminNotice.objects.filter(is_active=True).filter(
            Q(target_member=member) | Q(target_member__isnull=True)
        )

        for notice in active_notices:
            notifications.append({
                'id': notice.id,
                'type': 'admin_notice',
                'title': getattr(notice, 'title', 'Notice'),
                'message': notice.message,
                'raw_created_at': notice.created_at,
                'expires_at': notice.expires_at.strftime('%Y-%m-%d %H:%M') if getattr(notice, 'expires_at', None) else None
            })

        # Sort chronologically by true datetime standard before formatting
        notifications.sort(key=lambda item: item['raw_created_at'] or timezone.now(), reverse=True)

        for item in notifications:
            raw_dt = item.pop('raw_created_at', None)
            item['created_at'] = raw_dt.strftime('%Y-%m-%d %H:%M') if raw_dt else "N/A"

        return Response(notifications)


class ChatAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)

        room, _ = ChatRoom.objects.get_or_create(member=member)
        messages = [
            {
                'id': msg.id,
                'sender': msg.sender,
                'content': msg.content,
                'created_at': msg.created_at.strftime('%Y-%m-%d %H:%M') if getattr(msg, 'created_at', None) else "N/A"
            }
            for msg in room.messages.order_by('created_at')
        ]
        return Response({
            'room_id': room.id,
            'subject': getattr(room, 'subject', 'General Inquiry'),
            'messages': messages
        })

    def post(self, request):
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)

        content = request.data.get('content')
        if not content:
            return Response({'error': 'Message content is required.'}, status=status.HTTP_400_BAD_REQUEST)

        room, _ = ChatRoom.objects.get_or_create(member=member)
        sender_val = getattr(getattr(ChatMessage, 'SenderType', None), 'MEMBER', 'member')
        msg = ChatMessage.objects.create(room=room, sender=sender_val, content=content)

        return Response({
            'id': msg.id,
            'sender': msg.sender,
            'content': msg.content,
            'created_at': msg.created_at.strftime('%Y-%m-%d %H:%M') if getattr(msg, 'created_at', None) else "N/A"
        }, status=status.HTTP_201_CREATED)


@login_required
@require_http_methods(["DELETE"])
def delete_notification(request, notification_id):
    try:
        notification = Notification.objects.get(id=notification_id, member__user=request.user)
        notification.delete()
        return JsonResponse({'status': 'success', 'message': 'Notification deleted permanently'})
    except Notification.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Notification not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


class DocumentUploadAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)
        file = request.FILES.get('file')
        if file:
            Document.objects.create(member=member, file=file)
            return Response({'message': 'Document uploaded successfully!'}, status=status.HTTP_201_CREATED)
        return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)


class PassbookAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response([], status=status.HTTP_200_OK)

        transactions = []

        # 1. Savings Transactions
        for s in SavingsTransaction.objects.filter(member=member):
            if not s.date:
                continue
            
            dt = s.date
            if isinstance(dt, datetime.date) and not isinstance(dt, datetime.datetime):
                dt = datetime.datetime.combine(dt, datetime.time.min)
            if timezone.is_aware(dt):
                dt = timezone.make_naive(dt)

            tx_type = str(s.transaction_type or 'deposit').lower()
            transactions.append({
                'date': dt,
                'description': f"Savings {tx_type.capitalize()}",
                'type': tx_type,
                'amount': s.amount or Decimal('0.00'),
                'category': 'savings'
            })

        # 2. Repayments
        for r in Repayment.objects.filter(loan__member=member).select_related('loan'):
            if not r.date:
                continue

            dt = r.date
            if isinstance(dt, datetime.date) and not isinstance(dt, datetime.datetime):
                dt = datetime.datetime.combine(dt, datetime.time.min)
            if timezone.is_aware(dt):
                dt = timezone.make_naive(dt)

            transactions.append({
                'date': dt,
                'description': f"Loan EMI Payment (Loan #{r.loan.id})",
                'type': 'withdrawal',
                'amount': r.amount_paid or Decimal('0.00'),
                'category': 'repayment'
            })

        # 3. Sort chronologically
        transactions.sort(key=lambda x: x['date'])

        data = [{
            'date': t['date'].strftime("%Y-%m-%d %H:%M"),
            'description': t['description'],
            'type': t['type'],
            'amount': str(t['amount']),
            'category': t['category']
        } for t in transactions]

        return Response(data, status=status.HTTP_200_OK)


# ==========================================
# 3. RAZORPAY INTEGRATION VIEWS
# ==========================================
class RazorpayOrderAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            amount = Decimal(str(request.data.get('amount', 0)))
            if amount <= 0:
                raise ValueError
        except (ValueError, InvalidOperation, TypeError):
            return Response({'error': 'Valid positive amount is required'}, status=status.HTTP_400_BAD_REQUEST)

        key_id = getattr(settings, 'RAZORPAY_KEY_ID', '')
        key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', '')

        if not key_id or not key_secret:
            return Response({'error': 'Razorpay API credentials not configured in settings.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        client = razorpay.Client(auth=(key_id, key_secret))
        
        try:
            amount_in_paise = int(amount * 100)
            data = {
                "amount": amount_in_paise,
                "currency": "INR",
                "receipt": f"rcpt_m_{request.user.id}"
            }
            order = client.order.create(data=data)
            return Response({
                'order_id': order['id'],
                'amount': order['amount'],
                'currency': order['currency'],
                'key': key_id
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RazorpayVerifyAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response({'error': 'Profile not found.'}, status=status.HTTP_404_NOT_FOUND)

        razorpay_order_id = request.data.get('razorpay_order_id')
        razorpay_payment_id = request.data.get('razorpay_payment_id')
        razorpay_signature = request.data.get('razorpay_signature')
        
        payment_type = request.data.get('type') 
        loan_id = request.data.get('loan_id')

        if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
            return Response({'error': 'Missing Razorpay verification parameters.'}, status=status.HTTP_400_BAD_REQUEST)

        key_id = getattr(settings, 'RAZORPAY_KEY_ID', '')
        key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', '')
        client = razorpay.Client(auth=(key_id, key_secret))

        params_dict = {
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature
        }

        try:
            client.utility.verify_payment_signature(params_dict)
            
            payment = client.payment.fetch(razorpay_payment_id)
            if payment['status'] != 'captured':
                return Response({'error': 'Payment not captured.'}, status=status.HTTP_400_BAD_REQUEST)
                
            actual_amount_decimal = Decimal(str(payment['amount'])) / Decimal('100')
            
        except razorpay.errors.SignatureVerificationError:
            return Response({'error': 'Payment verification failed. Invalid signature.'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': f'Verification error: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                if payment_type == 'savings':
                    if is_basic_user(member):
                        return Response({'error': 'Savings deposits require full member privileges.'}, status=status.HTTP_403_FORBIDDEN)
                    
                    SavingsTransaction.objects.create(
                        member=member, 
                        amount=actual_amount_decimal, 
                        transaction_type='deposit'
                    )
                    Notification.objects.create(
                        member=member, 
                        message=f"Successfully deposited ₹{actual_amount_decimal} to your savings account."
                    )
                    return Response({'message': 'Savings deposit recorded successfully!'}, status=status.HTTP_200_OK)

                elif payment_type == 'emi' and loan_id:
                    loan = Loan.objects.select_for_update().get(id=loan_id, member=member)
                    Repayment.objects.create(loan=loan, amount_paid=actual_amount_decimal)
                    
                    # Deduct incoming payment against pending installments
                    unpaid_installments = LoanInstallment.objects.filter(loan=loan, is_paid=False).order_by('id')
                    remaining_payment = actual_amount_decimal

                    for installment in unpaid_installments:
                        inst_total = getattr(installment, 'total_amount', loan.emi_amount) or loan.emi_amount
                        if remaining_payment >= inst_total:
                            installment.is_paid = True
                            installment.save()
                            remaining_payment -= inst_total
                        else:
                            break

                    unpaid_count = LoanInstallment.objects.filter(loan=loan, is_paid=False).count()
                    if unpaid_count == 0 and loan.status != 'completed':
                        loan.status = 'completed'
                        loan.save()

                    Notification.objects.create(
                        member=member, 
                        message=f"Successfully paid EMI of ₹{actual_amount_decimal} for Loan #{loan.id}."
                    )
                    return Response({'message': 'EMI payment recorded successfully!'}, status=status.HTTP_200_OK)

                else:
                    return Response({'error': 'Invalid payment type or missing loan ID.'}, status=status.HTTP_400_BAD_REQUEST)

        except Loan.DoesNotExist:
            return Response({'error': 'Associated loan profile not found.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': f'Failed to process transaction: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==========================================
# 4. ADMIN PANEL TEMPLATE VIEWS
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
# 5. ADMIN DASHBOARD & METRICS API
# ==========================================
class DashboardMetricsAPI(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        dep_type = getattr(getattr(SavingsTransaction, 'Type', None), 'DEPOSIT', 'deposit')
        total_capital = SavingsTransaction.objects.filter(
            Q(transaction_type__iexact='deposit') | Q(transaction_type=dep_type)
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        approved_val = getattr(getattr(Loan, 'Status', None), 'APPROVED', 'approved')
        rejected_val = getattr(getattr(Loan, 'Status', None), 'REJECTED', 'rejected')
        pending_val = getattr(getattr(Loan, 'Status', None), 'PENDING', 'pending')
        completed_val = getattr(getattr(Loan, 'Status', None), 'COMPLETED', 'completed')

        active_loans = Loan.objects.filter(status__iexact=str(approved_val)).count()
        total_members = Member.objects.count()

        total_loans_count = Loan.objects.count()
        rejected_loans_count = Loan.objects.filter(status__iexact=str(rejected_val)).count()
        default_rate = round((rejected_loans_count / total_loans_count * 100), 2) if total_loans_count > 0 else 0.00

        # --- DYNAMIC SESSION STATUS ---
        today = timezone.now().date()
        nearest_meeting = Meeting.objects.filter(date__gte=today).order_by('date').first()
        
        if nearest_meeting:
            if nearest_meeting.date == today:
                session_status = "Active Today"
            else:
                session_status = f"Upcoming: {nearest_meeting.date.strftime('%b %d')}"
        else:
            session_status = "No Upcoming Sessions"

        disbursements_list = []
        recoveries_list = []

        raw_savings = (
            SavingsTransaction.objects.filter(Q(transaction_type__iexact='deposit') | Q(transaction_type=dep_type))
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
                Loan.objects.filter(status__iexact=str(approved_val)).count(),
                Loan.objects.filter(status__iexact=str(pending_val)).count(),
                Loan.objects.filter(status__iexact=str(rejected_val)).count(),
                Loan.objects.filter(status__iexact=str(completed_val)).count(),
            ]
        }

        member_role_val = getattr(getattr(Member, 'Role', None), 'MEMBER', 'member')
        user_role_val = getattr(getattr(Member, 'Role', None), 'USER', 'user')

        grade_distribution_data = {
            "categories": ["Members", "Users"],
            "series": [
                Member.objects.filter(role__iexact=str(member_role_val)).count(),
                Member.objects.filter(role__iexact=str(user_role_val)).count(),
            ]
        }

        payload = {
            "kpis": {
                "total_capital": {"value": float(total_capital)},
                "active_loans": {"value": active_loans},
                "total_members": {"value": total_members},
                "default_rate": {"value": default_rate},
                "latest_session_status": {"value": session_status} 
            },
            "charts": {
                "cashflow": cashflow_data,
                "portfolio": portfolio_data,
                "grade_distribution": grade_distribution_data
            }
        }
        return Response(payload)


# ==========================================
# 6. ADMIN MANAGEMENT & MANAGEMENT APIS
# ==========================================
class AdminLoanManagementAPI(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        loans = Loan.objects.all().order_by('-date')
        data = [{
            'id': l.id,
            'member': l.member.user.username if l.member and l.member.user else 'Unknown',
            'amount': str(l.amount),
            'status': l.status,
            'date': l.date.strftime("%Y-%m-%d") if getattr(l, 'date', None) else "N/A"
        } for l in loans]
        return Response(data)

    def patch(self, request, loan_id):
        try:
            loan = Loan.objects.get(id=loan_id)
            new_status = request.data.get('status')
            
            valid_statuses = []
            if hasattr(Loan, 'Status') and hasattr(Loan.Status, 'values'):
                valid_statuses = list(Loan.Status.values)
            
            if valid_statuses and new_status not in valid_statuses:
                return Response({'error': f'Invalid status choice. Valid choices are: {valid_statuses}'}, status=status.HTTP_400_BAD_REQUEST)

            loan.status = new_status
            loan.save()
            return Response({'message': f'Loan status updated to {new_status}'})
        except Loan.DoesNotExist:
            return Response({'error': 'Loan not found'}, status=status.HTTP_404_NOT_FOUND)


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

class AdminRentalRequestDetailAPI(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        try:
            rental_req = RentalRequest.objects.select_related('member', 'item').get(pk=pk)
        except RentalRequest.DoesNotExist:
            return Response({'error': 'Rental request not found.'}, status=status.HTTP_404_NOT_FOUND)

        new_status = str(request.data.get('status', '')).lower().strip()
        admin_note = request.data.get('admin_note', '').strip()

        valid_statuses = ['pending', 'approved', 'rejected', 'completed', 'cancelled']
        if new_status not in valid_statuses:
            return Response({'error': f'Invalid status. Must be one of {valid_statuses}'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            rental_req.status = new_status
            if hasattr(rental_req, 'admin_note'):
                rental_req.admin_note = admin_note
            rental_req.save()

            # Optional: Send automated notification to member
            if rental_req.member:
                item_name = rental_req.item.name if rental_req.item else 'Item'
                msg = f"Your rental request for '{item_name}' status has been updated to '{new_status.capitalize()}'."
                if admin_note:
                    msg += f" Note: {admin_note}"
                Notification.objects.create(member=rental_req.member, message=msg)

        return Response({
            'status': 'success',
            'message': f'Rental request #{rental_req.id} set to {new_status.capitalize()}.',
            'request_id': rental_req.id,
            'new_status': new_status
        }, status=status.HTTP_200_OK)


class AdminMeetingAPI(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        present_val = getattr(getattr(AttendanceRecord, 'Status', None), 'PRESENT', 'present')
        meetings = Meeting.objects.annotate(
            total_attendance=Count('attendance_records'),
            present_count=Count('attendance_records', filter=Q(attendance_records__status__iexact=str(present_val)))
        ).order_by('-date')
        serializer = MeetingSerializer(meetings, many=True)
        return Response({'meetings': serializer.data})

    def post(self, request):
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
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

        absent_val = getattr(getattr(AttendanceRecord, 'Status', None), 'ABSENT', 'absent')
        absent_total = AttendanceRecord.objects.filter(status__iexact=str(absent_val)).aggregate(total=Sum('fine_amount'))['total'] or Decimal('0.00')
        absent_count = AttendanceRecord.objects.filter(status__iexact=str(absent_val)).count()
        
        status_opts = []
        if hasattr(AttendanceRecord, 'Status'):
            for name in ['PRESENT', 'ABSENT', 'LATE', 'EXCUSED', 'ON_LEAVE']:
                if hasattr(AttendanceRecord.Status, name):
                    val = getattr(AttendanceRecord.Status, name)
                    status_opts.append({'value': val, 'label': name.replace('_', ' ').title()})

        return Response({
            'absent_total_fines': float(absent_total),
            'absent_count': absent_count,
            'records': serializer.data,
            'fined_records': fined_serializer.data,
            'status_options': status_opts
        })

    def post(self, request):
        attendance_rows = request.data.get('attendance', [])
        if not attendance_rows:
            return Response({'error': 'No attendance rows provided.'}, status=status.HTTP_400_BAD_REQUEST)

        saved_records = []
        absent_val = str(getattr(getattr(AttendanceRecord, 'Status', None), 'ABSENT', 'absent')).lower()

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

            try:
                fine_val = Decimal(str(fine_amount)) if fine_amount else Decimal('0.00')
            except (ValueError, TypeError):
                fine_val = Decimal('0.00')

            if str(status_val).lower() == absent_val and fine_val == 0:
                fine_val = Decimal('50.00')  

            record, _ = AttendanceRecord.objects.update_or_create(
                member_id=member_id,
                date=meeting_date,
                defaults={
                    'meeting': meeting,
                    'status': status_val,
                    'fine_amount': fine_val
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
            record.is_paid = not getattr(record, 'is_paid', False)
            record.save()
            return Response({'message': 'Payment status updated successfully', 'is_paid': record.is_paid}, status=status.HTTP_200_OK)
        except AttendanceRecord.DoesNotExist:
            return Response({'error': 'Fine record not found.'}, status=status.HTTP_404_NOT_FOUND)


class AdminFinanceAPI(View):
    def get(self, request):
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
        inc_val = str(getattr(getattr(IncomeExpense, 'EntryType', None), 'INCOME', 'IN')).lower()

        for tx in transactions:
            amt = float(tx.amount or 0)
            entry_type = str(getattr(tx, 'entry_type', '')).lower()
            
            if entry_type in [inc_val, 'in', 'income']:
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
            
            inc_val = getattr(getattr(IncomeExpense, 'EntryType', None), 'INCOME', 'IN')
            exp_val = getattr(getattr(IncomeExpense, 'EntryType', None), 'EXPENSE', 'EX')
            
            entry_type = inc_val if tx_type_input == 'IN' else exp_val

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


class AdminReportAPI(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
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

        inc_val = getattr(getattr(IncomeExpense, 'EntryType', None), 'INCOME', 'IN')
        exp_val = getattr(getattr(IncomeExpense, 'EntryType', None), 'EXPENSE', 'EX')
        absent_val = getattr(getattr(AttendanceRecord, 'Status', None), 'ABSENT', 'absent')

        total_collections = collections_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        total_income = income_expense_qs.filter(entry_type__iexact=str(inc_val)).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        total_expense = income_expense_qs.filter(entry_type__iexact=str(exp_val)).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        absent_count = attendance_qs.filter(status__iexact=str(absent_val)).count()
        fine_total = attendance_qs.filter(status__iexact=str(absent_val)).aggregate(total=Sum('fine_amount'))['total'] or Decimal('0.00')

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
            income_expense_qs.filter(entry_type__iexact=str(exp_val))
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
                'last_at': last_message.created_at.strftime('%Y-%m-%d %H:%M') if last_message and last_message.created_at else ''
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
                'created_at': msg.created_at.strftime('%Y-%m-%d %H:%M') if msg.created_at else ''
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
        admin_sender = getattr(getattr(ChatMessage, 'SenderType', None), 'ADMIN', 'admin')
        msg = ChatMessage.objects.create(room=room, sender=admin_sender, content=content)
        Notification.objects.create(member=member, message=f"Admin sent a new message: {content[:120]}")

        return Response({
            'id': msg.id,
            'sender': msg.sender,
            'content': msg.content,
            'created_at': msg.created_at.strftime('%Y-%m-%d %H:%M') if msg.created_at else ''
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
        admin_sender = getattr(getattr(ChatMessage, 'SenderType', None), 'ADMIN', 'admin')
        msg = ChatMessage.objects.create(room=room, sender=admin_sender, content=content)
        Notification.objects.create(member=member, message=f"Admin sent a new message: {content[:120]}")

        return Response({
            'status': 'success',
            'id': msg.id,
            'sender': msg.sender,
            'content': msg.content,
            'timestamp': msg.created_at.strftime('%Y-%m-%d %H:%M') if msg.created_at else ''
        }, status=status.HTTP_201_CREATED)


# ==========================================
# 7. FUNCTIONAL CRUD & LOAN DETAIL APIS
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
    
    approved_val = getattr(getattr(Loan, 'Status', None), 'APPROVED', 'approved')
    rejected_val = getattr(getattr(Loan, 'Status', None), 'REJECTED', 'rejected')

    active_exposure = loans.filter(status__iexact=str(approved_val)).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    defaulted_exposure = loans.filter(status__iexact=str(rejected_val)).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
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
        data = request.data.copy()
        full_name = data.get('full_name', '').strip()
        email = data.get('email', '').strip()
        
        role_value = data.get('role', 'user').strip().lower()
        
        member_role_val = getattr(getattr(Member, 'Role', None), 'MEMBER', 'member')
        user_role_val = getattr(getattr(Member, 'Role', None), 'USER', 'user')
        member_role = member_role_val if role_value in ['member', 'admin'] else user_role_val

        username_base = email.split('@')[0] if email else (full_name.split(' ')[0].lower() if full_name else 'member')
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
        
        if role_value == 'admin':
            user.is_staff = True
            user.is_superuser = True
        user.save()

        member, _ = Member.objects.get_or_create(user=user)
        member.role = member_role
        member.save()
        
        return Response({
            'status': 'success', 
            'message': 'Member profile created successfully.',
            'username': username, 
            'role': member.role,
            'is_admin': user.is_staff
        }, status=status.HTTP_201_CREATED)

    def patch(self, request, pk=None):
        member_id = pk or request.data.get('id') or request.data.get('member_id')
        if not member_id:
            return Response({'error': 'Member ID is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            member = Member.objects.select_related('user').get(pk=member_id)
        except Member.DoesNotExist:
            return Response({'error': 'Member profile not found.'}, status=status.HTTP_404_NOT_FOUND)

        data = request.data
        user = member.user

        if 'role' in data:
            role_value = str(data['role']).strip().lower()
            member_role_val = getattr(getattr(Member, 'Role', None), 'MEMBER', 'member')
            user_role_val = getattr(getattr(Member, 'Role', None), 'USER', 'user')

            if role_value == 'member':
                member.role = member_role_val
                user.is_staff = False
                user.is_superuser = False
            elif role_value == 'user':
                member.role = user_role_val
                user.is_staff = False
                user.is_superuser = False
            elif role_value == 'admin':
                member.role = member_role_val
                user.is_staff = True
                user.is_superuser = True
            else:
                return Response({'error': f"Invalid role '{role_value}'. Valid choices: 'user', 'member', 'admin'."}, status=status.HTTP_400_BAD_REQUEST)

        if 'full_name' in data:
            full_name = data['full_name'].strip()
            parts = full_name.split(' ', 1)
            user.first_name = parts[0]
            user.last_name = parts[1] if len(parts) > 1 else ''

        if 'email' in data:
            user.email = data['email'].strip()

        if 'is_active' in data:
            user.is_active = bool(data['is_active'])

        user.save()
        member.save()

        serializer = MemberSerializer(member)
        return Response({
            'status': 'success',
            'message': f"Member role updated to '{member.role}' (Admin privileges: {user.is_staff}).",
            'member': serializer.data
        }, status=status.HTTP_200_OK)

    def put(self, request, pk=None):
        return self.patch(request, pk)

    def delete(self, request, pk=None):
        member_id = pk or request.query_params.get('id') or request.data.get('member_id')
        if not member_id:
            return Response({'error': 'Member ID is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            member = Member.objects.get(pk=member_id)
            user = member.user
            member.delete()
            if user:
                user.delete()
            return Response({'status': 'success', 'message': 'Member deleted successfully.'}, status=status.HTTP_200_OK)
        except Member.DoesNotExist:
            return Response({'error': 'Member not found.'}, status=status.HTTP_404_NOT_FOUND)


class LoanDetailAPI(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        try:
            loan = Loan.objects.get(pk=pk)
        except Loan.DoesNotExist:
            return Response({"error": "Loan not found"}, status=status.HTTP_404_NOT_FOUND)
        
        data = request.data.copy()
        
        completed_val = str(getattr(getattr(Loan, 'Status', None), 'COMPLETED', 'completed')).lower()
        rejected_val = str(getattr(getattr(Loan, 'Status', None), 'REJECTED', 'rejected')).lower()
        pending_val = str(getattr(getattr(Loan, 'Status', None), 'PENDING', 'pending')).lower()

        if 'status' in data and isinstance(data['status'], str):
            new_status = data['status'].lower()
            current_status = str(loan.status).lower()
            
            if current_status == completed_val and new_status != completed_val:
                return Response({"error": "Cannot change the status of an already completed loan."}, status=status.HTTP_400_BAD_REQUEST)
            if current_status == rejected_val and new_status == pending_val:
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