from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@extend_schema(tags=["health"], responses={200: dict, 503: dict})
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request):
    """Verifica se a aplicação está no ar e se o banco responde."""
    try:
        connection.ensure_connection()
    except Exception:
        return Response({"status": "error", "database": "down"}, status=503)
    return Response({"status": "ok", "database": "up"})
