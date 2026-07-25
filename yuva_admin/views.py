from django.shortcuts import render
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta
from django.db.models.functions import TruncMonth

from rest_framework.decorators import APIView, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

from yuva_admin.serializers import MemberSerializer, LoanApplicationSerializer
from yuva.models import Member, Loan, SavingsTransaction, Repayment


# ==========================================
# 1. Template Views
# ==========================================

def admin_dashboard_v2(request):
    return render(request, 'admin/admin_dashboard.html')

def admin_member_list(request):
    return render(request, 'admin/admin_member_list.html')

def admin_loan_list(request):
    return render(request, 'admin/admin_loan.html')


# ==========================================
# 2. Dashboard Metrics API (Class-Based)
# ==========================================

class DashboardMetricsAPI(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        total_capital = SavingsTransaction.objects.filter(
            transaction_type=SavingsTransaction.Type.DEPOSIT
        ).aggregate(total=Sum('amount'))['total'] or 0.00

        active_loans = Loan.objects.filter(status=Loan.Status.APPROVED).count()
        total_members = Member.objects.count()

        total_loans_count = Loan.objects.count()
        rejected_loans_count = Loan.objects.filter(status=Loan.Status.REJECTED).count()
        default_rate = round((rejected_loans_count / total_loans_count * 100), 2) if total_loans_count > 0 else 0.00

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
                "default_rate": {"value": default_rate}
            },
            "charts": {
                "cashflow": cashflow_data,
                "portfolio": portfolio_data,
                "grade_distribution": grade_distribution_data
            }
        }
        return Response(payload)


# ==========================================
# 3. Functional API Endpoints & CRUD Views
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
    
    total_disbursed = loans.aggregate(total=Sum('amount'))['total'] or 0
    active_exposure = loans.filter(status=Loan.Status.APPROVED).aggregate(total=Sum('amount'))['total'] or 0
    defaulted_exposure = loans.filter(status=Loan.Status.REJECTED).aggregate(total=Sum('amount'))['total'] or 0

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
        full_name = data.get('full_name', '')
        if full_name:
            parts = full_name.split(' ', 1)
            data['user'] = {
                'first_name': parts[0],
                'last_name': parts[1] if len(parts) > 1 else '',
                'email': data.get('email', '')
            }
        
        serializer = MemberSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        print("Member Create Errors:", serializer.errors)
        return Response(serializer.errors, status=400)

    def patch(self, request, pk):
        try:
            member = Member.objects.get(pk=pk)
        except Member.DoesNotExist:
            return Response({"error": "Member not found"}, status=404)
        
        data = request.data.copy()
        
        # Clean up non-model fields or normalize choices
        data.pop('phone_number', None)
        data.pop('village', None)
        data.pop('residential_address', None)
        data.pop('full_name', None)

        # Normalize role to lowercase if your model expects lowercase choices
        if 'role' in data and data['role']:
            data['role'] = data['role'].lower()

        if 'email' in data and member.user:
            member.user.email = data.pop('email')
            member.user.save()

        serializer = MemberSerializer(member, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        
        print("Member Update Errors:", serializer.errors)
        return Response(serializer.errors, status=400)

    def delete(self, request, pk):
        try:
            member = Member.objects.get(pk=pk)
        except Member.DoesNotExist:
            return Response({"error": "Member not found"}, status=404)
        
        member.delete()
        return Response({"message": "Member deleted successfully"}, status=204)


# ==========================================
# 4. Loan Detail API (Edit / Delete)
# ==========================================
class LoanDetailAPI(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        try:
            loan = Loan.objects.get(pk=pk)
        except Loan.DoesNotExist:
            return Response({"error": "Loan not found"}, status=404)
        
        data = request.data.copy()
        if 'status' in data and isinstance(data['status'], str):
            data['status'] = data['status'].upper()
            
        serializer = LoanApplicationSerializer(loan, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def delete(self, request, pk):
        try:
            loan = Loan.objects.get(pk=pk)
        except Loan.DoesNotExist:
            return Response({"error": "Loan not found"}, status=404)
        
        loan.delete()
        return Response({"message": "Loan deleted successfully"}, status=204)