from django.utils import timezone
from dateutil.relativedelta import relativedelta
from decimal import Decimal
import razorpay
from django.conf import settings
from django.db import transaction
from django.db.models import Sum, Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework import status

from .models import (
    Member, Notification, Repayment, SavingsTransaction, Loan, 
    Document, LoanInstallment, AdminNotice, ChatRoom, ChatMessage, 
    AttendanceRecord, RentalItem, RentalRequest
)
from .forms import LoginForm, MemberRegistrationForm


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
    # Consider roles like 'user', 'basic', 'pending', or empty strings as basic users.
    return role in ['user', 'basic', 'pending', '']


# ==========================================
# 0. AUTHENTICATION VIEWS
# ==========================================
def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST) 
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard')
    else:
        form = LoginForm() 
    return render(request, 'member/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


def signup_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == 'POST':
        form = MemberRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = MemberRegistrationForm()
        
    return render(request, 'member/signup.html', {'form': form})


# ==========================================
# 1. TEMPLATE VIEWS
# ==========================================
@login_required
def member_dashboard(request): 
    member = Member.objects.filter(user=request.user).first()
    # Restricted to Members
    if is_basic_user(member):
        return redirect('member_profile')
    return render(request, 'member/dashboard.html', {'member': member})

@login_required
def member_chat_view(request): 
    return render(request, 'member/chat.html')

@login_required
def member_savings_view(request): 
    member = Member.objects.filter(user=request.user).first()
    # Restricted to Members
    if is_basic_user(member):
        return redirect('member_profile')
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

@login_required(login_url='login')
def member_passbook_view(request):
    return render(request, 'member/passbook.html')

@login_required
def member_attendance_view(request):
    member = Member.objects.filter(user=request.user).first()
    # Restricted to Members
    if is_basic_user(member):
        return redirect('member_profile')
    return render(request, 'member/attendance.html')

@login_required
def member_rentals_view(request):
    return render(request, 'member/rentals.html')


# ==========================================
# 2. API VIEWS
# ==========================================

class DashboardAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member = Member.objects.filter(user=request.user).first()
        # Restricted to Members
        if is_basic_user(member):
            return Response({'error': 'Dashboard access is restricted to full members.'}, status=status.HTTP_403_FORBIDDEN)
            
        if not member:
            return Response({'error': 'Member not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # 1. Core Metrics
        savings = SavingsTransaction.objects.filter(member=member)
        total_savings = sum(float(t.amount) if t.transaction_type.lower() == 'deposit' else -float(t.amount) for t in savings)
                
        active_loans_count = Loan.objects.filter(member=member, status__iexact='approved').count()
        recent_savings = SavingsTransaction.objects.filter(member=member).order_by('-date')[:5]
        
        tx_data = [{
            'transaction_type': f"Savings {t.transaction_type.capitalize()}",
            'amount': str(t.amount),
            'date': t.date.strftime("%Y-%m-%d %H:%M")
        } for t in recent_savings]

        # 2. Dynamic 6-Month Chart Aggregation
        chart_labels = []
        chart_savings = []
        chart_loans = []
        
        current_time = timezone.now().replace(day=1)
        
        for i in range(5, -1, -1):
            month_target = current_time - relativedelta(months=i)
            chart_labels.append(month_target.strftime('%b'))
            
            next_month = month_target + relativedelta(months=1)
            
            past_savings = SavingsTransaction.objects.filter(member=member, date__lt=next_month)
            monthly_savings_sum = sum(
                float(t.amount) if t.transaction_type.lower() == 'deposit' else -float(t.amount) 
                for t in past_savings
            )
            
            monthly_loan_sum = Loan.objects.filter(
                member=member,
                date__lt=next_month,
                status__iexact='approved'
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            chart_savings.append(float(monthly_savings_sum))
            chart_loans.append(float(monthly_loan_sum))

        return Response({
            'total_savings': round(total_savings, 2),
            'share_capital': round(total_savings * 0.1, 2),  
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
        # Restricted to Members
        if is_basic_user(member):
            return Response({'error': 'Savings features are restricted to full members.'}, status=status.HTTP_403_FORBIDDEN)
            
        savings = SavingsTransaction.objects.filter(member=member).order_by('date')
        running_balance = Decimal('0.00')
        data = []
        for s in savings:
            running_balance += s.amount if s.transaction_type == 'deposit' else -s.amount
            data.append({
                'id': s.id,
                'amount': str(s.amount),
                'transaction_type': s.transaction_type,
                'running_balance': str(running_balance),
                'date': s.date.strftime("%Y-%m-%d %H:%M")
            })
        return Response(list(reversed(data)))

    def post(self, request):
        member = Member.objects.filter(user=request.user).first()
        # Restricted to Members
        if is_basic_user(member):
            return Response({'error': 'Savings features are restricted to full members.'}, status=status.HTTP_403_FORBIDDEN)
            
        amount = request.data.get('amount')
        if not amount:
            return Response({'error': 'Amount is required'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            SavingsTransaction.objects.create(member=member, amount=amount, transaction_type='deposit')
            Notification.objects.create(member=member, message=f"Successfully deposited ₹{amount} to your savings ledger.")
            
        return Response({'message': 'Savings deposit recorded successfully.'})


class LoansAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member = Member.objects.filter(user=request.user).first()
        # Available to both Users & Members
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
                'date': loan.date.strftime("%Y-%m-%d %H:%M"),
                'installments': inst_data
            })
            
        return Response(data)
        
    def post(self, request):
        member = Member.objects.filter(user=request.user).first()
        # Available to both Users & Members
        if not member:
            return Response({'error': 'No profile found.'}, status=status.HTTP_400_BAD_REQUEST)
            
        amount = request.data.get('amount')
        tenure_months = request.data.get('tenure_months', 12)
        
        if amount:
            with transaction.atomic():
                loan = Loan.objects.create(member=member, amount=amount, tenure_months=tenure_months, status='pending')
                Notification.objects.create(
                    member=member, 
                    message=f"Your loan request for ₹{amount} has been submitted. Estimated EMI: ₹{loan.emi_amount}/month."
                )
            return Response({'message': 'Loan requested successfully!', 'estimated_emi': loan.emi_amount}, status=status.HTTP_201_CREATED)
            
        return Response({'error': 'Amount is required'}, status=status.HTTP_400_BAD_REQUEST)


class ProfileAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member = Member.objects.filter(user=request.user).first()
        # Available to both Users & Members
        if not member:
            return Response({'error': 'Profile not found.'}, status=status.HTTP_404_NOT_FOUND)
            
        # Calculate profile completion percentage across 6 core fields
        fields = [
            member.name,
            member.gender,
            request.user.email,
            member.phone,
            member.village,
            member.address
        ]
        filled = sum(1 for f in fields if f and str(f).strip())
        profile_completion = int((filled / len(fields)) * 100)
        
        # Format updated_at timestamp for the frontend view
        updated_at_str = None
        if member.updated_at:
            updated_at_str = member.updated_at.strftime("%b %d, %Y, %I:%M %p")

        return Response({
            'username': request.user.username,
            'email': request.user.email,
            'name': member.name or '',
            'gender': member.gender or '',
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
            
        with transaction.atomic():
            # Update Name and Gender directly on the Member model
            if 'name' in request.data:
                member.name = request.data.get('name', '')
                
            if 'gender' in request.data:
                member.gender = request.data.get('gender', '')

            member.phone = request.data.get('phone', member.phone)
            member.village = request.data.get('village', member.village)
            member.address = request.data.get('address', member.address)
            
            # Standard users shouldn't be able to self-assign full member roles to bypass restrictions
            requested_role = request.data.get('role', member.role)
            if not is_basic_user(member) or requested_role == 'user': 
                member.role = requested_role
                
            # Saving member updates the updated_at timestamp via auto_now=True
            member.save() 
            
            email = request.data.get('email')
            if email:
                request.user.email = email
                request.user.save()

        # Recalculate completion percentage after saving updates
        fields = [
            member.name,
            member.gender,
            request.user.email,
            member.phone,
            member.village,
            member.address
        ]
        filled = sum(1 for f in fields if f and str(f).strip())
        profile_completion = int((filled / len(fields)) * 100)

        updated_at_str = member.updated_at.strftime("%b %d, %Y, %I:%M %p") if member.updated_at else "Just now"

        return Response({
            'message': 'Profile updated successfully!',
            'profile_completion': profile_completion,
            'updated_at': updated_at_str
        })


class MemberAttendanceAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member = Member.objects.filter(user=request.user).first()
        # Restricted to Members
        if is_basic_user(member):
            return Response({'error': 'Attendance records are restricted to full members.'}, status=status.HTTP_403_FORBIDDEN)
            
        if not member:
            return Response({'error': 'Profile not found.'}, status=status.HTTP_404_NOT_FOUND)

        records = AttendanceRecord.objects.filter(member=member).order_by('-date')
        response_data = {
            'present_count': records.filter(status=AttendanceRecord.Status.PRESENT).count(),
            'absent_count': records.filter(status=AttendanceRecord.Status.ABSENT).count(),
            'total_fines': float(records.filter(status=AttendanceRecord.Status.ABSENT).aggregate(total=Sum('fine_amount'))['total'] or 0),
            'records': [
                {
                    'date': rec.date.isoformat(),
                    'status': rec.status,
                    'fine_amount': float(rec.fine_amount),
                    'meeting_title': rec.meeting.title if rec.meeting else None
                }
                for rec in records
            ]
        }
        return Response(response_data)


class MemberRentalDirectoryAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Available to both Users & Members
        items = RentalItem.objects.filter(is_active=True)
        items_data = [{
            'id': item.id,
            'name': item.name,
            'description': item.description,
            'rental_fee': str(item.rental_fee),
            'deposit_fee': str(item.deposit_fee),
            'price': str(item.rental_fee), 
            'available_quantity': item.available_quantity,
            'image_url': item.image.url if item.image else None
        } for item in items]
        
        user_requests = RentalRequest.objects.filter(member__user=request.user).order_by('-created_at')
        requests_data = [{
            'id': req.id,
            'item_name': req.item.name,
            'start_date': req.start_date.strftime('%Y-%m-%d'),
            'end_date': req.end_date.strftime('%Y-%m-%d'),
            'status': req.status,
            'created_at': req.created_at.strftime('%Y-%m-%d %H:%M')
        } for req in user_requests]

        return Response({
            'catalog': items_data,
            'my_requests': requests_data
        })


class RepaymentsAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Available to both Users & Members
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)
            
        repayments = Repayment.objects.filter(loan__member=member).order_by('-date').values('loan__id', 'amount_paid', 'date')
        return Response(list(repayments))


class NotificationsAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Available to both Users & Members
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)

        notifications = []
        for note in Notification.objects.filter(member=member).order_by('-created_at'):
            notifications.append({
                'id': note.id,
                'message': note.message,
                'type': 'notification',
                'is_read': note.is_read,
                'created_at': note.created_at.strftime('%Y-%m-%d %H:%M')
            })

        active_notices = AdminNotice.objects.filter(is_active=True).filter(
            Q(target_member=member) | Q(target_member__isnull=True)
        ).order_by('-created_at')

        for notice in active_notices:
            notifications.append({
                'id': notice.id,
                'type': 'admin_notice',
                'title': notice.title,
                'message': notice.message,
                'created_at': notice.created_at.strftime('%Y-%m-%d %H:%M'),
                'expires_at': notice.expires_at.strftime('%Y-%m-%d %H:%M') if notice.expires_at else None
            })

        notifications.sort(key=lambda item: item['created_at'], reverse=True)
        return Response(notifications)


class ChatAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Available to both Users & Members
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)

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
            'room_id': room.id,
            'subject': room.subject,
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
        msg = ChatMessage.objects.create(room=room, sender=ChatMessage.SenderType.MEMBER, content=content)

        return Response({
            'id': msg.id,
            'sender': msg.sender,
            'content': msg.content,
            'created_at': msg.created_at.strftime('%Y-%m-%d %H:%M')
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
        # Available to both Users & Members
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
        # Available to both Users & Members
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response([], status=status.HTTP_200_OK)

        transactions = []
        # Even if users don't have access to Savings API, if they have past transactions, they can view them
        for s in SavingsTransaction.objects.filter(member=member):
            transactions.append({
                'date': s.date,
                'description': f"Savings {s.transaction_type.capitalize()}",
                'type': s.transaction_type,
                'amount': s.amount,
                'category': 'savings'
            })

        for r in Repayment.objects.filter(loan__member=member):
            transactions.append({
                'date': r.date,
                'description': f"Loan EMI Payment (Loan #{r.loan.id})",
                'type': 'withdrawal',
                'amount': r.amount_paid,
                'category': 'repayment'
            })

        transactions.sort(key=lambda x: x['date'])
        data = [{
            'date': t['date'].strftime("%Y-%m-%d %H:%M"),
            'description': t['description'],
            'type': t['type'],
            'amount': str(t['amount']),
            'category': t['category']
        } for t in transactions]

        return Response(list(reversed(data)))


class AdminLoanManagementAPI(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        loans = Loan.objects.all().order_by('-date')
        data = [{
            'id': l.id,
            'member': l.member.user.username,
            'amount': str(l.amount),
            'status': l.status,
            'date': l.date.strftime("%Y-%m-%d")
        } for l in loans]
        return Response(data)

    def patch(self, request, loan_id):
        try:
            loan = Loan.objects.get(id=loan_id)
            new_status = request.data.get('status')
            if new_status in Loan.Status.values:
                loan.status = new_status
                loan.save()
                return Response({'message': f'Loan status updated to {new_status}'})
            return Response({'error': 'Invalid status choice'}, status=status.HTTP_400_BAD_REQUEST)
        except Loan.DoesNotExist:
            return Response({'error': 'Loan not found'}, status=status.HTTP_404_NOT_FOUND)


# ==========================================
# 3. RAZORPAY INTEGRATION VIEWS
# ==========================================
class RazorpayOrderAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        amount = request.data.get('amount')
        if not amount:
            return Response({'error': 'Amount is required'}, status=status.HTTP_400_BAD_REQUEST)

        key_id = getattr(settings, 'RAZORPAY_KEY_ID', '')
        key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', '')

        if not key_id or not key_secret:
            return Response({'error': 'Razorpay API credentials not configured in settings.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        client = razorpay.Client(auth=(key_id, key_secret))
        
        try:
            amount_in_paise = int(Decimal(str(amount)) * 100)
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
        amount = request.data.get('amount')
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
        except razorpay.errors.SignatureVerificationError:
            return Response({'error': 'Payment verification failed. Invalid signature.'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': f'Verification error: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount_decimal = Decimal(str(amount)) if amount else Decimal('0.00')

            with transaction.atomic():
                if payment_type == 'savings':
                    # Explicit role block to prevent basic users from modifying savings through the payment gateway
                    if is_basic_user(member):
                        return Response({'error': 'Savings deposits require full member privileges.'}, status=status.HTTP_403_FORBIDDEN)
                    
                    SavingsTransaction.objects.create(
                        member=member, 
                        amount=amount_decimal, 
                        transaction_type='deposit'
                    )
                    Notification.objects.create(
                        member=member, 
                        message=f"Successfully deposited ₹{amount_decimal} to your savings account."
                    )
                    return Response({'message': 'Savings deposit recorded successfully!'}, status=status.HTTP_200_OK)

                elif payment_type == 'emi' and loan_id:
                    loan = Loan.objects.select_for_update().get(id=loan_id, member=member)
                    Repayment.objects.create(loan=loan, amount_paid=amount_decimal)
                    
                    installment = LoanInstallment.objects.filter(loan=loan, is_paid=False).order_by('id').first()
                    if installment:
                        installment.is_paid = True
                        installment.save()

                    unpaid_count = LoanInstallment.objects.filter(loan=loan, is_paid=False).count()
                    if unpaid_count == 0 and loan.status != 'completed':
                        loan.status = 'completed'
                        loan.save()

                    Notification.objects.create(
                        member=member, 
                        message=f"Successfully paid EMI of ₹{amount_decimal} for Loan #{loan.id}."
                    )
                    return Response({'message': 'EMI payment recorded successfully!'}, status=status.HTTP_200_OK)

                else:
                    return Response({'error': 'Invalid payment type or missing loan ID.'}, status=status.HTTP_400_BAD_REQUEST)

        except Loan.DoesNotExist:
            return Response({'error': 'Associated loan profile not found.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': f'Failed to process transaction: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
