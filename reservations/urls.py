from django.urls import path
from .views import (
    ReservationTimelineView,
    ReservationCreateView,
    MyReservationListView,
    ReservationDetailView,
    reservation_cancel,
    ReservationUpdateView,
    CalendarEventsAPI,
    ReservationMoveView,
)

urlpatterns = [
    path("timeline/", ReservationTimelineView.as_view(), name="reservation_timeline"),
    # F-06: my reservations list  (/reservations/my/?tab=upcoming or ?tab=past)
    path("my/", MyReservationListView.as_view(), name="my_reservations"),
    # F-09: reservation create
    path("create/", ReservationCreateView.as_view(), name="reservation_create"),
    # F-10: reservation detail
    path("<int:pk>/", ReservationDetailView.as_view(), name="reservation_detail"),
    # F-11: reservation edit
    path("<int:pk>/edit/", ReservationUpdateView.as_view(), name="reservation_edit"),
    # F-12: reservation cancel
    path("<int:pk>/cancel/", reservation_cancel, name="reservation_cancel"),
    path('events/', CalendarEventsAPI.as_view(), name='calendar_events'),
    path('<int:pk>/move/', ReservationMoveView.as_view(), name='reservation_move'),
]