"""Garantias no nível do banco (inserindo direto pelo ORM, sem passar pelo service).

Estes testes provam que a R1 não depende do código da aplicação.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.db import IntegrityError, transaction

from reservations.models import Reservation, ReservationStatus

TZ = ZoneInfo("America/Sao_Paulo")


def dt(hour, minute=0):
    return datetime(2030, 1, 10, hour, minute, tzinfo=TZ)


def make(room, user, start, end, **kwargs):
    return Reservation.objects.create(room=room, user=user, start_at=start, end_at=end, **kwargs)


@pytest.mark.django_db
class TestOverlapConstraint:
    def test_rejects_overlapping_active_reservations_in_same_room(self, room, user, other_user):
        make(room, user, dt(9), dt(10))
        with pytest.raises(IntegrityError, match="reservation_no_overlap"), transaction.atomic():
            make(room, other_user, dt(9, 30), dt(11))

    def test_allows_adjacent_reservations(self, room, user):
        make(room, user, dt(9), dt(10))
        make(room, user, dt(10), dt(11))
        assert Reservation.objects.count() == 2

    def test_cancelled_reservation_does_not_block_slot(self, room, user, other_user):
        make(room, user, dt(9), dt(10), status=ReservationStatus.CANCELLED)
        make(room, other_user, dt(9), dt(10))
        assert Reservation.objects.active().count() == 1

    def test_same_slot_in_different_rooms_is_allowed(self, room, user):
        other_room = type(room).objects.create(name="Sala Verde", capacity=4, location="3º andar")
        make(room, user, dt(9), dt(10))
        make(other_room, user, dt(9), dt(10))
        assert Reservation.objects.count() == 2


@pytest.mark.django_db
def test_rejects_end_before_or_equal_start(room, user):
    with pytest.raises(IntegrityError, match="reservation_end_after_start"), transaction.atomic():
        make(room, user, dt(10), dt(10))
