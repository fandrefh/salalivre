"""Views de autenticação: cadastro, login (JWT) e renovação de token."""

from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from accounts.serializers import RegisterSerializer


@extend_schema(tags=["auth"], summary="Cadastrar usuário (sempre role=user)")
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []


@extend_schema(tags=["auth"], summary="Login: devolve access e refresh (JWT)")
class LoginView(TokenObtainPairView):
    # Rate limit por IP (usuário anônimo), taxa em DEFAULT_THROTTLE_RATES["login"].
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"


@extend_schema(tags=["auth"], summary="Renovar o access token")
class RefreshView(TokenRefreshView):
    pass
