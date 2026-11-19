"""Views de reserva: finas. Validam entrada, chamam o service e serializam a saída."""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from reservations import services
from reservations.filters import ReservationFilter
from reservations.models import Reservation
from reservations.serializers import (
    AvailabilityQuerySerializer,
    AvailabilitySerializer,
    ReservationCreateSerializer,
    ReservationSerializer,
)
from rooms.models import Room


@extend_schema_view(
    list=extend_schema(
        summary="Listar reservas",
        description="user: só as próprias (filtros ignorados). admin: todas, com filtros.",
    ),
    create=extend_schema(
        summary="Criar reserva",
        request=ReservationCreateSerializer,
        responses={201: ReservationSerializer},
    ),
)
@extend_schema(tags=["reservations"])
class ReservationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = ReservationSerializer
    filterset_class = ReservationFilter

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # geração do schema OpenAPI (sem usuário)
            return Reservation.objects.none()
        queryset = Reservation.objects.select_related("room", "user")
        if self.request.user.is_admin_role:
            return queryset
        # Reserva de outro usuário fica fora do escopo: no cancel, get_object() devolve 404.
        return queryset.filter(user=self.request.user)

    def filter_queryset(self, queryset):
        # Filtros (sala, usuário, datas) são recurso de admin; para user, são ignorados.
        if not self.request.user.is_admin_role:
            return queryset
        return super().filter_queryset(queryset)

    def create(self, request):
        serializer = ReservationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reservation = services.create_reservation(user=request.user, **serializer.validated_data)
        return Response(ReservationSerializer(reservation).data, status=status.HTTP_201_CREATED)

    @extend_schema(summary="Cancelar reserva", request=None, responses={200: ReservationSerializer})
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        reservation = services.cancel_reservation(
            reservation=self.get_object(), by_user=request.user
        )
        return Response(ReservationSerializer(reservation).data)


@extend_schema(
    tags=["reservations"],
    summary="Disponibilidade da sala no dia",
    parameters=[OpenApiParameter("date", str, description="Dia no formato YYYY-MM-DD")],
    responses={200: AvailabilitySerializer},
)
class RoomAvailabilityView(APIView):
    def get(self, request, pk: int):
        query = AvailabilityQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        day = query.validated_data["date"]

        room = get_object_or_404(Room, pk=pk)
        free = services.room_availability(room=room, day=day)

        data = {
            "room": room.pk,
            "date": day,
            "free": [{"start_at": start, "end_at": end} for start, end in free],
        }
        return Response(AvailabilitySerializer(data).data)
