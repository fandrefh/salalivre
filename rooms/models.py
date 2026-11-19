from django.db import models


class Room(models.Model):
    name = models.CharField(max_length=100, unique=True)
    capacity = models.PositiveIntegerField()
    location = models.CharField("andar/localização", max_length=100)
    # Sala inativa não aceita novas reservas (R7); as existentes continuam válidas.
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(capacity__gt=0), name="room_capacity_positive"
            ),
        ]

    def __str__(self) -> str:
        return self.name
