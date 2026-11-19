from django.urls import path
from rest_framework.routers import SimpleRouter

from reservations.views import ReservationViewSet, RoomAvailabilityView

# Sem barra final, como as demais rotas da API (/api/reservations, /api/health).
router = SimpleRouter(trailing_slash=False)
router.register("reservations", ReservationViewSet, basename="reservation")

urlpatterns = [
    path(
        "rooms/<int:pk>/availability",
        RoomAvailabilityView.as_view(),
        name="room-availability",
    ),
    *router.urls,
]
