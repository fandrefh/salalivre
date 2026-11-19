"""Testes dos casos de uso (services): regras aplicadas com banco, locks e concorrência.

Os limites de cada regra pura ficam em test_rules.py; aqui há uma verificação por regra,
checando `error.code` e status HTTP, mais os cenários que só existem com banco (R1, R5, R7,
ordem das validações, cancelamento) e os testes concorrentes.
"""

import threading
from datetime import datetime, timedelta

import pytest
import time_machine
from django.db import connection
from rest_framework.exceptions import NotFound

from core.exceptions import BusinessRuleError
from reservations.models import Reservation, ReservationStatus
from reservations.rules import BUSINESS_TZ
from reservations.services import cancel_reservation, create_reservation

NOW = datetime(2030, 1, 9, 12, 0, tzinfo=BUSINESS_TZ)


def at(hour: int, minute: int = 0, day: int = 10) -> datetime:
    """Data/hora no fuso de negócio, em janeiro de 2030 (por padrão, o dia seguinte a NOW)."""
    return datetime(2030, 1, day, hour, minute, tzinfo=BUSINESS_TZ)


def reserve(user, room, start_at, end_at, now=NOW) -> Reservation:
    return create_reservation(user=user, room=room, start_at=start_at, end_at=end_at, now=now)


def assert_rule_error(exc_info, code: str, status_code: int) -> None:
    assert exc_info.value.error_code == code
    assert exc_info.value.status_code == status_code


@pytest.mark.django_db
class TestCreateReservation:
    def test_creates_active_reservation(self, user, room):
        reservation = reserve(user, room, at(9), at(10))

        assert reservation.pk is not None
        assert reservation.status == ReservationStatus.ACTIVE
        assert reservation.user == user

    def test_r1_overlap_returns_409(self, user, other_user, room):
        reserve(user, room, at(9), at(10))

        with pytest.raises(BusinessRuleError) as exc_info:
            reserve(other_user, room, at(9, 30), at(11))

        assert_rule_error(exc_info, "room_unavailable", 409)
        assert Reservation.objects.count() == 1

    def test_r1_adjacent_reservation_is_allowed(self, user, other_user, room):
        reserve(user, room, at(9), at(10))
        reserve(other_user, room, at(10), at(11))

        assert Reservation.objects.count() == 2

    def test_r1_cancelled_reservation_frees_the_slot(self, user, other_user, room):
        Reservation.objects.create(
            user=user, room=room, start_at=at(9), end_at=at(10), status=ReservationStatus.CANCELLED
        )

        reserve(other_user, room, at(9), at(10))

    def test_r2_past_returns_422(self, user, room):
        with pytest.raises(BusinessRuleError) as exc_info:
            reserve(user, room, at(9, day=8), at(10, day=8))

        assert_rule_error(exc_info, "start_in_past", 422)

    def test_r2_uses_current_time_when_now_is_omitted(self, user, room):
        with time_machine.travel(at(11), tick=False), pytest.raises(BusinessRuleError) as exc_info:
            create_reservation(user=user, room=room, start_at=at(10), end_at=at(11))

        assert_rule_error(exc_info, "start_in_past", 422)

    def test_r3_invalid_duration_returns_422(self, user, room):
        with pytest.raises(BusinessRuleError) as exc_info:
            reserve(user, room, at(9), at(9, 29))

        assert_rule_error(exc_info, "invalid_duration", 422)

    def test_r4_outside_business_hours_returns_422(self, user, room):
        with pytest.raises(BusinessRuleError) as exc_info:
            reserve(user, room, at(19), at(20, 1))

        assert_rule_error(exc_info, "outside_business_hours", 422)

    def test_r5_fourth_active_future_reservation_returns_409(self, user, room):
        for hour in (8, 10, 12):
            reserve(user, room, at(hour), at(hour + 1))

        with pytest.raises(BusinessRuleError) as exc_info:
            reserve(user, room, at(14), at(15))

        assert_rule_error(exc_info, "reservation_limit_reached", 409)

    def test_r5_ignores_cancelled_and_in_progress_reservations(self, user, room):
        # Em andamento: começou antes de NOW, não é "futura".
        Reservation.objects.create(
            user=user,
            room=room,
            start_at=NOW - timedelta(minutes=30),
            end_at=NOW + timedelta(minutes=30),
        )
        Reservation.objects.create(
            user=user, room=room, start_at=at(16), end_at=at(17), status=ReservationStatus.CANCELLED
        )
        for hour in (8, 10):
            reserve(user, room, at(hour), at(hour + 1))

        reserve(user, room, at(12), at(13))  # 3ª futura ativa: permitida

    def test_r5_is_per_user(self, user, other_user, room):
        for hour in (8, 10, 12):
            reserve(user, room, at(hour), at(hour + 1))

        reserve(other_user, room, at(14), at(15))

    def test_r7_inactive_room_returns_422(self, user, room):
        room.is_active = False
        room.save()

        with pytest.raises(BusinessRuleError) as exc_info:
            reserve(user, room, at(9), at(10))

        assert_rule_error(exc_info, "room_inactive", 422)

    def test_r7_reads_current_state_from_database(self, user, room):
        """O objeto em memória diz ativa, mas o banco diz inativa: vale o banco (lido sob lock)."""
        type(room).objects.filter(pk=room.pk).update(is_active=False)

        with pytest.raises(BusinessRuleError) as exc_info:
            reserve(user, room, at(9), at(10))

        assert_rule_error(exc_info, "room_inactive", 422)

    def test_r7_existing_reservations_stay_active_after_deactivation(self, user, room):
        reservation = reserve(user, room, at(9), at(10))
        room.is_active = False
        room.save()

        reservation.refresh_from_db()
        assert reservation.status == ReservationStatus.ACTIVE

    def test_validation_order_r7_before_time_rules(self, user, room):
        """Spec 03: com R7 e R2 violadas, devolve R7."""
        room.is_active = False
        room.save()

        with pytest.raises(BusinessRuleError) as exc_info:
            reserve(user, room, at(9, day=8), at(10, day=8))

        assert exc_info.value.error_code == "room_inactive"


@pytest.mark.django_db
class TestCancelReservation:
    @pytest.fixture
    def reservation(self, user, room):
        return reserve(user, room, at(9), at(10))

    def test_owner_cancels_keeping_the_record(self, reservation, user):
        cancelled = cancel_reservation(
            reservation=reservation, by_user=user, now=at(9) - timedelta(hours=2)
        )

        assert cancelled.status == ReservationStatus.CANCELLED
        assert cancelled.cancelled_at == at(7)
        assert Reservation.objects.filter(pk=reservation.pk).exists()

    def test_r6_exactly_one_hour_before_is_allowed(self, reservation, user):
        cancel_reservation(reservation=reservation, by_user=user, now=at(8))

    def test_r6_less_than_one_hour_returns_422(self, reservation, user):
        with pytest.raises(BusinessRuleError) as exc_info:
            cancel_reservation(reservation=reservation, by_user=user, now=at(8, 1))

        assert_rule_error(exc_info, "cancellation_too_late", 422)

    def test_r6_also_applies_to_admin(self, reservation, admin_user):
        with pytest.raises(BusinessRuleError) as exc_info:
            cancel_reservation(reservation=reservation, by_user=admin_user, now=at(8, 1))

        assert_rule_error(exc_info, "cancellation_too_late", 422)

    def test_admin_cancels_any_reservation(self, reservation, admin_user):
        cancelled = cancel_reservation(reservation=reservation, by_user=admin_user, now=NOW)

        assert cancelled.status == ReservationStatus.CANCELLED

    def test_user_cannot_cancel_someone_elses_reservation(self, reservation, other_user):
        with pytest.raises(NotFound):
            cancel_reservation(reservation=reservation, by_user=other_user, now=NOW)

        reservation.refresh_from_db()
        assert reservation.status == ReservationStatus.ACTIVE

    def test_already_cancelled_returns_409(self, reservation, user):
        cancel_reservation(reservation=reservation, by_user=user, now=NOW)

        with pytest.raises(BusinessRuleError) as exc_info:
            cancel_reservation(reservation=reservation, by_user=user, now=NOW)

        assert_rule_error(exc_info, "reservation_not_active", 409)

    def test_cancelled_slot_can_be_booked_again(self, reservation, user, other_user, room):
        cancel_reservation(reservation=reservation, by_user=user, now=NOW)

        reserve(other_user, room, at(9), at(10))


def run_concurrently(calls: list[dict]) -> list[str]:
    """Dispara `create_reservation` em threads liberadas ao mesmo tempo por uma Barrier.

    Cada thread usa sua própria conexão com o banco. Devolve, ordenado, "ok" ou o
    `error_code` de cada chamada; qualquer outra exceção (ex.: deadlock) aparece pelo nome
    da classe, para o teste falhar com uma mensagem clara.
    """
    barrier = threading.Barrier(len(calls))
    results: list[str] = []

    def worker(kwargs: dict) -> None:
        try:
            barrier.wait()
            create_reservation(**kwargs)
            results.append("ok")
        except BusinessRuleError as exc:
            results.append(exc.error_code)
        except Exception as exc:  # qualquer falha inesperada (ex.: deadlock) vira resultado
            results.append(type(exc).__name__)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(kwargs,)) for kwargs in calls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return sorted(results)


@pytest.mark.django_db(transaction=True)
class TestConcurrency:
    """transaction=True: cada thread abre conexão própria e só enxerga dados commitados."""

    def test_r1_simultaneous_requests_for_same_slot_create_only_one(self, user, other_user, room):
        calls = [
            {"user": u, "room": room, "start_at": at(9), "end_at": at(10), "now": NOW}
            for u in (user, other_user) * 3
        ]

        results = run_concurrently(calls)

        assert results == ["ok"] + ["room_unavailable"] * 5
        assert Reservation.objects.count() == 1

    def test_r5_simultaneous_requests_from_same_user_respect_the_limit(self, user, room):
        for hour in (8, 10):
            reserve(user, room, at(hour), at(hour + 1))
        calls = [
            {"user": user, "room": room, "start_at": at(h), "end_at": at(h + 1), "now": NOW}
            for h in (12, 14, 16, 18)
        ]

        results = run_concurrently(calls)

        assert results == ["ok"] + ["reservation_limit_reached"] * 3
        assert Reservation.objects.filter(user=user).count() == 3
