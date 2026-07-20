# yuva/auth.py
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

class DhananjayYuvaTokenSerializer(TokenObtainPairSerializer):
    """
    Customizes the JWT payload to return user status details directly.
    """
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Inject custom claims into the encrypted payload
        token['username'] = user.username
        token['is_staff'] = user.is_staff  # True for admin, False for members

        # Grab the user's specific member profile ID if it exists
        if hasattr(user, 'member_profile'):
            token['member_id'] = user.member_profile.id
            token['full_name'] = f"{user.member_profile.first_name} {user.member_profile.last_name}"
        else:
            token['member_id'] = None
            token['full_name'] = "Admin User"

        return token

class DhananjayYuvaTokenView(TokenObtainPairView):
    serializer_class = DhananjayYuvaTokenSerializer