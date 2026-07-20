from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import User
from .models import Member, Loan

class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Username or Email",
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 outline-none',
            'placeholder': 'Enter username or email'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password'].widget.attrs.update({
            'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 outline-none',
            'placeholder': '••••••••'
        })

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username and password:
            User = get_user_model()
            self.user_cache = None

            # If the user typed an email, safely check all accounts sharing this email to prevent login failures
            if '@' in username:
                matching_users = User.objects.filter(email__iexact=username)
                for user_obj in matching_users:
                    authenticated_user = authenticate(self.request, username=user_obj.username, password=password)
                    if authenticated_user is not None:
                        self.user_cache = authenticated_user
                        break
            else:
                self.user_cache = authenticate(self.request, username=username, password=password)

            if self.user_cache is None:
                raise forms.ValidationError(
                    self.error_messages['invalid_login'],
                    code='invalid_login',
                    params={'username': self.fields['username'].label},
                )
            else:
                self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data

class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = ['phone', 'address'] 
        widgets = {
            'phone': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 outline-none',
                'placeholder': 'Enter phone number'
            }),
            'address': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 outline-none',
                'rows': 3,
                'placeholder': 'Enter your address'
            }),
        }

class LoanRequestForm(forms.ModelForm):
    class Meta:
        model = Loan
        fields = ['amount', 'tenure_months']
        widgets = {
            'amount': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-emerald-500 outline-none',
                'placeholder': 'Enter amount (e.g. 5000)'
            }),
            'tenure_months': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-emerald-500 outline-none',
                'placeholder': 'Enter tenure in months (e.g. 12)'
            }),
        }

class MemberRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'placeholder': 'name@example.com'}))
    
    class Meta:
        model = User
        fields = ['username', 'email']

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email