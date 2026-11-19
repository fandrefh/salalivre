"""Cálculo de intervalos livres de uma sala em um dia (funções puras).

Não acessam banco nem relógio: o `now` e as reservas ocupadas chegam por argumento.
"""

from datetime import date, datetime

from reservations.rules import BUSINESS_TZ, CLOSING_TIME, OPENING_TIME

Interval = tuple[datetime, datetime]


def day_window(day: date, now: datetime) -> Interval | None:
    """Janela reservável do dia no fuso de negócio: de max(07:00, now) até 20:00.

    Recorta o que já passou para não oferecer horários que a R2 recusaria.
    Devolve None se não sobrar nada (dia passado ou hoje após 20:00).
    """
    opening = datetime.combine(day, OPENING_TIME, tzinfo=BUSINESS_TZ)
    closing = datetime.combine(day, CLOSING_TIME, tzinfo=BUSINESS_TZ)
    start = max(opening, now)
    if start >= closing:
        return None
    return start, closing


def free_intervals(day_start: datetime, day_end: datetime, busy: list[Interval]) -> list[Interval]:
    """Recebe a janela do dia e os intervalos ocupados (reservas ativas) e devolve os livres.

    Intervalos são [início, fim): reservas adjacentes não deixam lacuna de largura zero.
    Ocupações que extrapolam a janela (ex.: reserva em andamento antes do `now`) são
    recortadas. A entrada não precisa vir ordenada.
    """
    free: list[Interval] = []
    cursor = day_start  # primeiro instante ainda não classificado como livre ou ocupado

    for busy_start, busy_end in sorted(busy):
        if busy_start >= day_end:
            break
        if busy_end <= cursor:
            continue
        if busy_start > cursor:
            free.append((cursor, busy_start))
        cursor = busy_end

    if cursor < day_end:
        free.append((cursor, day_end))
    return free
