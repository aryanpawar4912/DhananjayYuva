from django.shortcuts import render
from yuva.models import Member, SavingsTransaction, Loan, Repayment

def admin_dashboard(request):
    # Now looks in: templates/admin/dashboard.html
    context = {
        'member_count': Member.objects.count(),
        'total_loans': Loan.objects.count()
    }
    return render(request, 'admin/dashboard.html', context)

def admin_manage_members(request):
    # Now looks in: templates/admin/members.html
    return render(request, 'admin/members.html', {'members': Member.objects.all()})

def admin_manage_loans(request):
    """List and manage all loans."""
    loans = Loan.objects.all()
    context = {'loans': loans}
    return render(request, 'admin/loans.html', context)

def admin_manage_savings(request):
    """List and manage all savings transactions."""
    savings = SavingsTransaction.objects.all()
    context = {'savings': savings}
    return render(request, 'admin/savings.html', context)