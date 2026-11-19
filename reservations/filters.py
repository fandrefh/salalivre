"""Filtros da listagem de reservas (usados apenas para admin; ver views)."""

import django_filters

from reservations.models import Reservation


class ReservationFilter(django_filters.FilterSet):
    """`date_from`/`date_to` são inclusivos e comparam a data de `start_at` no fuso de negócio.

    Com USE_TZ, o lookup `__date` converte para o TIME_ZONE (America/Sao_Paulo) antes de
    extrair a data, então uma reserva às 22:00 local não "pula" para o dia seguinte em UTC.
    """

    # Só ISO (YYYY-MM-DD). Sem input_formats, o Django aceitaria também formatos do pt-br
    # (ex.: 10/01/2030), divergindo do endpoint de disponibilidade e da spec.
    date_from = django_filters.DateFilter(
        field_name="start_at", lookup_expr="date__gte", input_formats=["%Y-%m-%d"]
    )
    date_to = django_filters.DateFilter(
        field_name="start_at", lookup_expr="date__lte", input_formats=["%Y-%m-%d"]
    )

    class Meta:
        model = Reservation
        fields = ["room", "user", "date_from", "date_to"]
