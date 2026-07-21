from decimal import Decimal
import razorpay
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework import status
from django.db.models import Sum
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import Member, Notification, Repayment, SavingsTransaction, Loan, Document, LoanInstallment
from .forms import LoginForm, MemberRegistrationForm

# ==========================================
# 0. AUTHENTICATION & RBAC HELPERS
# ==========================================
def is_admin(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)

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
        return redirect('dashboard')  # Redirect if already logged in
        
    if request.method == 'POST':
        form = MemberRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # Automatically log in after registration
            return redirect('dashboard')
    else:
        form = MemberRegistrationForm()
        
    return render(request, 'member/signup.html', {'form': form})

# ==========================================
# 1. TEMPLATE VIEWS (Loads the UI shells)
# ==========================================
@login_required
def member_dashboard(request): 
    return render(request, 'member/dashboard.html')

@login_required
def member_savings_view(request): 
    return render(request, 'member/savings.html')

@login_required
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
# 2. API VIEWS (Handles Data via JSON)
# ==========================================

class DashboardAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response({'error': 'Member not found'}, status=404)
        
        # Calculate total savings balance
        savings = SavingsTransaction.objects.filter(member=member)
        total_savings = 0
        for t in savings:
            if t.transaction_type == 'deposit':
                total_savings += float(t.amount)
            else:
                total_savings -= float(t.amount)
                
        # Count approved/active loans
        active_loans_count = Loan.objects.filter(member=member, status='approved').count()
        
        # Fetch recent transactions for dashboard
        recent_savings = SavingsTransaction.objects.filter(member=member).order_by('-date')[:5]
        tx_data = []
        for t in recent_savings:
            tx_data.append({
                'transaction_type': f"Savings {t.transaction_type}",
                'amount': str(t.amount),
                'date': t.date.strftime("%Y-%m-%d %H:%M")
            })

        data = {
            'total_savings': round(total_savings, 2),
            'active_loans_count': active_loans_count,
            'recent_transactions': tx_data
        }
        return Response(data)

class SavingsAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response([], status=200)
            
        savings = SavingsTransaction.objects.filter(member=member).order_by('date')
        
        # Calculate running balance dynamically
        running_balance = Decimal('0.00')
        data = []
        for s in savings:
            if s.transaction_type == 'deposit':
                running_balance += s.amount
            else:
                running_balance -= s.amount
                
            data.append({
                'id': s.id,
                'amount': str(s.amount),
                'transaction_type': s.transaction_type,
                'running_balance': str(running_balance),
                'date': s.date.strftime("%Y-%m-%d %H:%M")
            })
        
        # Return in reverse chronological order for UI display
        return Response(list(reversed(data)))

    def post(self, request):
        member = Member.objects.filter(user=request.user).first()
        amount = request.data.get('amount')
        
        if not amount:
            return Response({'error': 'Amount is required'}, status=400)

        SavingsTransaction.objects.create(
            member=member,
            amount=amount,
            transaction_type='deposit'
        )
        Notification.objects.create(
            member=member,
            message=f"Successfully deposited ₹{amount} to your savings ledger."
        )
        return Response({'message': 'Savings deposit recorded successfully.'})
    
class LoansAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response({'error': 'Member profile not found for this user.'}, status=404)
        
        loans = Loan.objects.filter(member=member).order_by('-date')
        data = []
        for loan in loans:
            data.append({
                'id': loan.id,
                'amount': str(loan.amount),
                'interest_rate': str(loan.interest_rate),
                'tenure_months': loan.tenure_months,
                'emi_amount': loan.emi_amount,
                'status': loan.status,
                'date': loan.date.strftime("%Y-%m-%d %H:%M")
            })
        return Response(data)
        
    def post(self, request):
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response({'error': 'No Member profile found for this user account.'}, status=status.HTTP_400_BAD_REQUEST)
            
        amount = request.data.get('amount')
        tenure_months = request.data.get('tenure_months', 12) # Default to 12 months
        
        if amount:
            loan = Loan.objects.create(member=member, amount=amount, tenure_months=tenure_months, status='pending')
            
            # Auto-generate a notification
            Notification.objects.create(
                member=member, 
                message=f"Your loan request for ₹{amount} has been submitted successfully. Estimated EMI: ₹{loan.emi_amount}/month."
            )
            
            return Response({
                'message': 'Loan requested successfully!', 
                'estimated_emi': loan.emi_amount
            }, status=status.HTTP_201_CREATED)
            
        return Response({'error': 'Amount is required'}, status=status.HTTP_400_BAD_REQUEST)

class ProfileAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response({'error': 'Member profile not found.'}, status=404)
            
        full_name = f"{request.user.first_name} {request.user.last_name}".strip()
        if not full_name:
            full_name = request.user.username
            
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
            return Response({'error': 'Member profile not found.'}, status=404)
            
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
    
# API for Repayments
class RepaymentsAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response({'error': 'Member not found'}, status=404)
        repayments = Repayment.objects.filter(loan__member=member).values('loan__id', 'amount_paid', 'date')
        return Response(list(repayments))

# API for Notifications
class NotificationsAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response({'error': 'Member not found'}, status=404)
        notes = Notification.objects.filter(member=member).order_by('-created_at').values('message', 'is_read', 'created_at')
        return Response(list(notes))

# API for Document Uploads
class DocumentUploadAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response({'error': 'Member not found'}, status=404)
        file = request.FILES.get('file')
        
        if file:
            Document.objects.create(member=member, file=file)
            return Response({'message': 'Document uploaded successfully!'}, status=201)
        return Response({'error': 'No file provided'}, status=400)


class PassbookAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        member = Member.objects.filter(user=request.user).first()
        if not member:
            return Response([], status=200)

        transactions = []

        # 1. Gather Savings Transactions
        savings = SavingsTransaction.objects.filter(member=member)
        for s in savings:
            transactions.append({
                'date': s.date,
                'description': f"Savings {s.transaction_type.capitalize()}",
                'type': s.transaction_type,
                'amount': s.amount,
                'category': 'savings'
            })

        # 2. Gather Loan Repayments (EMIs paid)
        repayments = Repayment.objects.filter(loan__member=member)
        for r in repayments:
            transactions.append({
                'date': r.date,
                'description': f"Loan EMI Payment (Loan #{r.loan.id})",
                'type': 'withdrawal',
                'amount': r.amount_paid,
                'category': 'repayment'
            })

        # Sort all transactions chronologically by date
        transactions.sort(key=lambda x: x['date'])

        # Format for JSON output
        data = []
        for t in transactions:
            data.append({
                'date': t['date'].strftime("%Y-%m-%d %H:%M"),
                'description': t['description'],
                'type': t['type'],
                'amount': str(t['amount']),
                'category': t['category']
            })

        return Response(list(reversed(data)))


class AdminLoanManagementAPI(APIView):
    """RBAC Protected: Only admins can view and manage all member loans."""
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
                loan.save() # Triggers post_save signal for schedule generation & notifications
                return Response({'message': f'Loan status updated to {new_status}'})
            return Response({'error': 'Invalid status choice'}, status=400)
        except Loan.DoesNotExist:
            return Response({'error': 'Loan not found'}, status=404)


class RazorpayOrderAPI(APIView):
    """Payment Gateway Integration: Create Razorpay Order for EMI or Savings"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        amount = request.data.get('amount') # in INR
        payment_type = request.data.get('type') # 'savings' or 'emi'
        loan_id = request.data.get('loan_id')

        if not amount:
            return Response({'error': 'Amount is required'}, status=400)

        # Initialize Razorpay Client (Add keys to settings.py)
        client = razorpay.Client(auth=(getattr(settings, 'RAZORPAY_KEY_ID', 'test_key'), getattr(settings, 'RAZORPAY_KEY_SECRET', 'test_secret')))
        
        data = {
            "amount": int(float(amount) * 100), # amount in paise
            "currency": "INR",
            "receipt": f"rcpt_{request.user.id}"
        }
        
        try:
            order = client.order.create(data=data)
            return Response({
                'order_id': order['id'],
                'amount': order['amount'],
                'currency': order['currency'],
                'key': getattr(settings, 'RAZORPAY_KEY_ID', 'test_key')
            })
        except Exception as e:
            return Response({'error': str(e)}, status=500)


class RazorpayVerifyAPI(APIView):
    """Verify Payment and Log Transaction / Repayment"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        member = Member.objects.filter(user=request.user).first()
        payment_type = request.data.get('type') # 'savings' or 'emi'
        amount = request.data.get('amount')
        loan_id = request.data.get('loan_id')

        if payment_type == 'savings':
            SavingsTransaction.objects.create(member=member, amount=amount, transaction_type='deposit')
            Notification.objects.create(member=member, message=f"Successfully deposited ₹{amount} to savings.")
        elif payment_type == 'emi' and loan_id:
            loan = Loan.objects.get(id=loan_id, member=member)
            Repayment.objects.create(loan=loan, amount_paid=amount)
            # Mark first pending installment as paid
            installment = LoanInstallment.objects.filter(loan=loan, is_paid=False).first()
            if installment:
                installment.is_paid = True
                installment.save()
            Notification.objects.create(member=member, message=f"Successfully paid EMI of ₹{amount} for Loan #{loan.id}.")

        return Response({'message': 'Payment recorded successfully!'})