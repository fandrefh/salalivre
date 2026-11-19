from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeBoundary, RangeOperators
from django.db import models
from django.db.models import F, Func, Q


class TsTzRange(Func):
    """Monta um tstzrange (intervalo de timestamps com fuso) a partir de duas colunas."""

    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


class ReservationStatus(models.TextChoices):
    ACTIVE = "active", "Ativa"
    CANCELLED = "cancelled", "Cancelada"


class ReservationQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=ReservationStatus.ACTIVE)

    def active_future_for(self, user, now):
        """Reservas ativas do usuário que ainda não começaram (base da R5)."""
        return self.active().filter(user=user, start_at__gt=now)


class Reservation(models.Model):
    room = models.ForeignKey("rooms.Room", on_delete=models.PROTECT, related_name="reservations")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reservations"
    )
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    status = models.CharField(
        max_length=10, choices=ReservationStatus.choices, default=ReservationStatus.ACTIVE
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ReservationQuerySet.as_manager()

    class Meta:
        ordering = ["start_at"]
        constraints = [
            # Impede intervalos vazios/invertidos (que escapariam da exclusão abaixo).
            models.CheckConstraint(
                condition=Q(end_at__gt=F("start_at")),
                name="reservation_end_after_start",
            ),
            # R1: duas reservas ATIVAS da mesma sala não podem se sobrepor.
            # '[)' -> início incluso, fim excluso: 09-10 e 10-11 não conflitam.
            ExclusionConstraint(
                name="reservation_no_overlap",
                expressions=[
                    (TsTzRange("start_at", "end_at", RangeBoundary()), RangeOperators.OVERLAPS),
                    ("room", RangeOperators.EQUAL),
                ],
                condition=Q(status=ReservationStatus.ACTIVE),
            ),
        ]
        indexes = [
            models.Index(fields=["user", "status", "start_at"], name="reservation_user_status_idx"),
            models.Index(fields=["room", "start_at"], name="reservation_room_start_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.room} {self.start_at:%d/%m %H:%M}-{self.end_at:%H:%M} ({self.status})"
