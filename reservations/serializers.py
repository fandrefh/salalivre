"""Serializers de reserva: só formato e tipos de entrada/saída.

Nenhuma regra de negócio aqui (R1–R7 ficam em rules.py/services.py).
"""

from rest_framework import serializers

from reservations.models import Reservation
from rooms.models import Room


class ReservationSerializer(serializers.ModelSerializer):
    """Saída de uma reserva. Datas são devolvidas no fuso de negócio (America/Sao_Paulo)."""

    class Meta:
        model = Reservation
        fields = [
            "id",
            "room",
            "user",
            "start_at",
            "end_at",
            "status",
            "cancelled_at",
            "created_at",
        ]
        read_only_fields = fields


class ReservationCreateSerializer(serializers.Serializer):
    """Entrada da criação. `user` não é aceito: a reserva é sempre de quem está autenticado."""

    # Todas as salas, inclusive inativas: sala inativa é R7 (422), não payload inválido (400).
    room = serializers.PrimaryKeyRelatedField(queryset=Room.objects.all())
    start_at = serializers.DateTimeField()
    end_at = serializers.DateTimeField()


class AvailabilityQuerySerializer(serializers.Serializer):
    """Query string do endpoint de disponibilidade."""

    date = serializers.DateField(input_formats=["%Y-%m-%d"])


class IntervalSerializer(serializers.Serializer):
    start_at = serializers.DateTimeField()
    end_at = serializers.DateTimeField()


class AvailabilitySerializer(serializers.Serializer):
    """Saída da disponibilidade: sala, dia e intervalos livres."""

    room = serializers.IntegerField()
    date = serializers.DateField()
    free = IntervalSerializer(many=True)
