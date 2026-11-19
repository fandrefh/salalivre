"""Casos de uso de reserva: orquestram regras puras, transação e locks.

Estratégia (ver CLAUDE.md e docs/specs/03 e 05):
    - R1: garantida pela ExclusionConstraint `reservation_no_overlap`.
      O IntegrityError é traduzido para BusinessRuleError 409 FORA da transação.
      `select_for_update()` na sala complementa: evita deadlock entre inserts
      concorrentes e protege a leitura de `is_active` (R7).
    - R5: `select_for_update()` na linha do usuário dentro da transação,
      para serializar criações simultâneas do mesmo usuário.
    - Ordem dos locks na criação: sala → usuário.
"""

from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from core.exceptions import BusinessRuleError
from reservations import rules
from reservations.availability import Interval, day_window, free_intervals
from reservations.models import Reservation, ReservationStatus
from rooms.models import Room

OVERLAP_CONSTRAINT = "reservation_no_overlap"


def create_reservation(
    *, user, room: Room, start_at: datetime, end_at: datetime, now: datetime | None = None
) -> Reservation:
    """Cria a reserva e traduz violação da R1 em 409.

    A tradução fica fora da transação: quando o INSERT falha, a transação inteira é
    desfeita e só então o erro é convertido. Assim não é preciso savepoint.
    """
    try:
        return _create_reservation_tx(
            user=user, room=room, start_at=start_at, end_at=end_at, now=now
        )
    except IntegrityError as exc:
        if _constraint_name(exc) == OVERLAP_CONSTRAINT:
            raise BusinessRuleError(
                "room_unavailable", "Horário já reservado para esta sala.", status_code=409
            ) from exc
        raise


@transaction.atomic
def _create_reservation_tx(
    *, user, room: Room, start_at: datetime, end_at: datetime, now: datetime | None = None
) -> Reservation:
    """Aplica R7 → R2/R3/R4 → R5 e insere (R1 no banco), numa única transação.

    Ordem dos locks, sempre a mesma para não criar deadlock entre eles: sala → usuário.
    """
    now = now or timezone.now()

    # Trava a sala até o commit. Não é o que garante a R1 (isso é a constraint): serve para
    # (a) enfileirar inserts na mesma sala, evitando o deadlock que duas checagens da
    # ExclusionConstraint em paralelo podem gerar; (b) ler `is_active` sem corrida com um
    # admin desativando a sala ao mesmo tempo (R7).
    room = Room.objects.select_for_update().get(pk=room.pk)

    # R7
    if not room.is_active:
        raise BusinessRuleError("room_inactive", "Esta sala está inativa e não aceita reservas.")

    # R2, R3, R4
    rules.validate_time_window(start_at, end_at, now)

    # R5: trava a linha do usuário até o commit. Uma segunda requisição do mesmo usuário
    # espera aqui e só conta depois que a primeira terminar, vendo a reserva já criada.
    get_user_model().objects.select_for_update().get(pk=user.pk)
    active_future = Reservation.objects.active_future_for(user, now).count()
    if active_future >= rules.MAX_ACTIVE_FUTURE_RESERVATIONS:
        raise BusinessRuleError(
            "reservation_limit_reached",
            f"Limite de {rules.MAX_ACTIVE_FUTURE_RESERVATIONS} reservas ativas futuras atingido.",
            status_code=409,
        )

    # R1: a ExclusionConstraint rejeita sobreposição, inclusive entre inserts simultâneos.
    return Reservation.objects.create(user=user, room=room, start_at=start_at, end_at=end_at)


@transaction.atomic
def cancel_reservation(
    *, reservation: Reservation, by_user, now: datetime | None = None
) -> Reservation:
    """Cancela (status=cancelled, cancelled_at=now) respeitando a R6.

    `user` só cancela as próprias reservas; reserva alheia é tratada como inexistente (404).
    `admin` cancela qualquer uma, mas também está sujeito à R6.
    """
    now = now or timezone.now()

    if not by_user.is_admin_role and reservation.user_id != by_user.pk:
        raise NotFound()

    # Relê com lock: dois cancelamentos simultâneos não podem ambos ver status=active.
    reservation = Reservation.objects.select_for_update().get(pk=reservation.pk)

    if reservation.status != ReservationStatus.ACTIVE:
        raise BusinessRuleError(
            "reservation_not_active", "Esta reserva já está cancelada.", status_code=409
        )

    # R6
    rules.validate_cancellation(reservation.start_at, now)

    reservation.status = ReservationStatus.CANCELLED
    reservation.cancelled_at = now
    reservation.save(update_fields=["status", "cancelled_at"])
    return reservation


def room_availability(*, room: Room, day: date, now: datetime | None = None) -> list[Interval]:
    """Intervalos livres da sala no dia (spec 06), considerando só reservas ativas.

    Sala inativa → 422 (coerente com a R7). Dia passado ou hoje após 20:00 → lista vazia.
    """
    now = now or timezone.now()

    if not room.is_active:
        raise BusinessRuleError("room_inactive", "Esta sala está inativa e não aceita reservas.")

    window = day_window(day, now)
    if window is None:
        return []
    window_start, window_end = window

    # Reservas que intersectam a janela, inclusive a que está em andamento no início dela.
    busy = list(
        Reservation.objects.active()
        .filter(room=room, start_at__lt=window_end, end_at__gt=window_start)
        .values_list("start_at", "end_at")
    )
    return free_intervals(window_start, window_end, busy)


def _constraint_name(exc: IntegrityError) -> str | None:
    """Nome da constraint violada, lido do erro original do psycopg."""
    diag = getattr(exc.__cause__, "diag", None)
    return getattr(diag, "constraint_name", None)
