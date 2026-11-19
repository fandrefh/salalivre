from django.contrib import admin

from .models import Reservation


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("room", "user", "start_at", "end_at", "status")
    list_filter = ("status", "room")
    date_hierarchy = "start_at"
    raw_id_fields = ("user",)
