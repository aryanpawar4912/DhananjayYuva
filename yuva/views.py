from datetime import datetime
from dateutil.relativedelta import relativedelta
from decimal import Decimal
import razorpay
from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework import status

from .models import Member, Notification, Repayment, SavingsTransaction, Loan, Document, LoanInstallment
from .forms import LoginForm, MemberRegistrationForm


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
    return render(request, 'member/dashboard.html')

@login_required
def member_savings_view(request): 
    return render(request, 'member/savings.html')

@login_required
@ensure_csrf_cookie  # Ensures frontend JS can access CSRF token for payments
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


# ==========================================
# 2. API VIEWS
# ==========================================

class DashboardAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member = Member.objects.filter(user=request.user).first()
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
        
        current_date = datetime.now().replace(day=1)
        
        # Generate past 6 months dynamically (Oldest to Newest)
        for i in range(5, -1, -1):
            month_target = current_date - relativedelta(months=i)
            chart_labels.append(month_target.strftime('%b'))
            
            next_month = month_target + relativedelta(months=1)
            
            # Cumulative savings calculation up to target month
            past_savings = SavingsTransaction.objects.filter(member=member, date__lt=next_month)
            monthly_savings_sum = sum(
                float(t.amount) if t.transaction_type.lower() == 'deposit' else -float(t.amount) 
                for t in past_savings
            )
            
            # Cumulative approved loan principal sum up to target month
            monthly_loan_sum = Loan.objects.filter(
                member=member,
                date__lt=next_month,
                status__iexact='approved'
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            chart_savings.append(float(monthly_savings_sum))
            chart_loans.append(float(monthly_loan_sum))

        return Response({
            'total_savings': round(total_savings, 2),
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
        if not member:
            return Response([], status=status.HTTP_200_OK)
            
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
        if not member:
            return Response({'error': 'Member profile not found.'}, status=status.HTTP_404_NOT_FOUND)
        
        loans = Loan.objects.filter(member=member).order_by('-date')
        data = []
        
        for loan in loans:
            # Fetch and serialize associated installments for frontend schedule table
            installments = LoanInstallment.objects.filter(loan=loan).order_by('id')
            inst_data = [{
                'installment_number': idx + 1,  # Safe fallback index if model field missing
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
        if not member:
            return Response({'error': 'No Member profile found.'}, status=status.HTTP_400_BAD_REQUEST)
            
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
        if not member:
            return Response({'error': 'Member profile not found.'}, status=status.HTTP_404_NOT_FOUND)
            
        full_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username
            
        return Response({
            'name': full_name,
            'phone': member.phone,
            'village': member.village,
            'address': member.address,
            'role': member.role,
            'email': request.user.email,
            'username': request.user.username
        })
        
    def post(self, request):
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response({'error': 'Member profile not found.'}, status=status.HTTP_404_NOT_FOUND)
            
        with transaction.atomic():
            full_name = request.data.get('name', '')
            if full_name:
                name_parts = full_name.split(' ', 1)
                request.user.first_name = name_parts[0]
                request.user.last_name = name_parts[1] if len(name_parts) > 1 else ''
                request.user.save()
                
            member.phone = request.data.get('phone', member.phone)
            member.village = request.data.get('village', member.village)
            member.address = request.data.get('address', member.address)
            member.role = request.data.get('role', member.role)
            member.save()
            
            email = request.data.get('email')
            if email:
                request.user.email = email
                request.user.save()
        
        return Response({'message': 'Profile updated successfully!'})


class RepaymentsAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response({'error': 'Member not found'}, status=status.HTTP_404_NOT_FOUND)
            
        repayments = Repayment.objects.filter(loan__member=member).order_by('-date').values('loan__id', 'amount_paid', 'date')
        return Response(list(repayments))


class NotificationsAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response({'error': 'Member not found'}, status=status.HTTP_404_NOT_FOUND)
        
        notes = Notification.objects.filter(member=member).order_by('-created_at').values('id', 'message', 'is_read', 'created_at')
        return Response(list(notes))


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
            return Response({'error': 'Member not found'}, status=status.HTTP_404_NOT_FOUND)
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
            if new_status in dict(Loan.STATUS_CHOICES):
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
            # Razorpay expects the amount in paise (1 INR = 100 Paise)
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
            return Response({'error': 'Member profile not found.'}, status=status.HTTP_404_NOT_FOUND)

        razorpay_order_id = request.data.get('razorpay_order_id')
        razorpay_payment_id = request.data.get('razorpay_payment_id')
        razorpay_signature = request.data.get('razorpay_signature')
        
        payment_type = request.data.get('type')  # 'savings' or 'emi'
        amount = request.data.get('amount')
        loan_id = request.data.get('loan_id')

        # Check for missing signature fields
        if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
            return Response({'error': 'Missing Razorpay verification parameters.'}, status=status.HTTP_400_BAD_REQUEST)

        key_id = getattr(settings, 'RAZORPAY_KEY_ID', '')
        key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', '')
        client = razorpay.Client(auth=(key_id, key_secret))

        # 1. Verify Payment Signature
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

        # 2. Record Payment on Successful Verification
        try:
            amount_decimal = Decimal(str(amount)) if amount else Decimal('0.00')

            # Ensure all database records update successfully, or rollback entirely
            with transaction.atomic():
                
                if payment_type == 'savings':
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
                    
                    # Mark earliest unpaid installment as paid
                    installment = LoanInstallment.objects.filter(loan=loan, is_paid=False).order_by('id').first()
                    if installment:
                        installment.is_paid = True
                        installment.save()

                    # Check if all installments are paid -> Update Loan status to Completed
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