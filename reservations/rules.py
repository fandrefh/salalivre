"""Regras de negócio puras (sem banco, sem relógio).

Tudo que a regra precisa chega por argumento — inclusive `now`.
Assim os testes são unitários, rápidos e determinísticos.

    - R2: não reservar no passado
    - R3: duração entre 30 min e 4 h
    - R4: entre 07:00 e 20:00, mesmo dia (no fuso de negócio)
    - R6: cancelamento com >= 1 h de antecedência

Todas as datas recebidas devem ser timezone-aware.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings

from core.exceptions import BusinessRuleError

# Fuso de negócio: o mesmo em que o Django interpreta datas sem fuso (settings.TIME_ZONE).
# A R4 é avaliada nele, independentemente do fuso da entrada.
BUSINESS_TZ = ZoneInfo(settings.TIME_ZONE)

MIN_DURATION = timedelta(minutes=30)
MAX_DURATION = timedelta(hours=4)
OPENING_TIME = time(7, 0)
CLOSING_TIME = time(20, 0)
MAX_ACTIVE_FUTURE_RESERVATIONS = 3  # R5 (verificada no service, precisa de lock)
MIN_CANCEL_NOTICE = timedelta(hours=1)


def validate_time_window(start_at: datetime, end_at: datetime, now: datetime) -> None:
    """Valida R2, R3 e R4, nessa ordem. Levanta BusinessRuleError na primeira violação."""
    # R2: estritamente no futuro; começar "agora" já é passado no instante do INSERT.
    if start_at <= now:
        raise BusinessRuleError("start_in_past", "Não é possível reservar horário no passado.")

    # R3: limites inclusivos. end_at <= start_at gera duração <= 0 e também cai aqui.
    if not MIN_DURATION <= end_at - start_at <= MAX_DURATION:
        raise BusinessRuleError(
            "invalid_duration", "A reserva deve durar entre 30 minutos e 4 horas."
        )

    # R4: compara no fuso de negócio. Terminar exatamente às 20:00 é permitido.
    local_start = start_at.astimezone(BUSINESS_TZ)
    local_end = end_at.astimezone(BUSINESS_TZ)
    if (
        local_start.date() != local_end.date()
        or local_start.time() < OPENING_TIME
        or local_end.time() > CLOSING_TIME
    ):
        raise BusinessRuleError(
            "outside_business_hours",
            "A reserva deve começar e terminar entre 07:00 e 20:00, no mesmo dia.",
        )


def validate_cancellation(start_at: datetime, now: datetime) -> None:
    """Valida R6: cancelar com pelo menos 1 h de antecedência (exatamente 1 h é permitido)."""
    if start_at - now < MIN_CANCEL_NOTICE:
        raise BusinessRuleError(
            "cancellation_too_late",
            "A reserva só pode ser cancelada com pelo menos 1 hora de antecedência.",
        )
