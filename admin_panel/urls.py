from django.urls import path
from .views import (
    RoomAdminListView,
    RoomCreateView,
    RoomUpdateView,
    RoomDeleteView,
    RoomToggleActiveView,
    UserListView,
    UserCreateView,
    UserUpdateView,
    UserToggleActiveView,
    UserPasswordResetView,
    CSVImportView,
    CSVImportExecuteView,
    AllReservationListView,
    FacilityListView,
    FacilityCreateView,
    FacilityUpdateView,
    FacilityDeleteView,
    BuildingListView,
    BuildingCreateView,
    BuildingUpdateView,
    BuildingDeleteView,
    DepartmentListView,
    DepartmentCreateView,
    DepartmentUpdateView,
    DepartmentDeleteView,
    OperationLogView,
    CSVDeleteView,
    CSVDeleteExecuteView,
)

urlpatterns = [
    # F-14: ユーザー一覧
    path("users/", UserListView.as_view(), name="user_admin_list"),
    # F-15: ユーザー追加・編集
    path("users/create/", UserCreateView.as_view(), name="user_create"),
    path("users/<int:pk>/edit/", UserUpdateView.as_view(), name="user_edit"),
    # F-16: 有効/無効トグル
    path(
        "users/<int:pk>/toggle-active/",
        UserToggleActiveView.as_view(),
        name="user_toggle_active",
    ),
    # F-15拡張: パスワードリセット
    path(
        "users/<int:pk>/reset-password/",
        UserPasswordResetView.as_view(),
        name="user_password_reset",
    ),
    # F-17: CSVインポート
    path("users/csv-import/", CSVImportView.as_view(), name="csv_import"),
    path(
        "users/csv-import/execute/",
        CSVImportExecuteView.as_view(),
        name="csv_import_execute",
    ),
    # F-18〜F-20: 会議室マスタ管理
    path("rooms/", RoomAdminListView.as_view(), name="room_admin_list"),
    path("rooms/create/", RoomCreateView.as_view(), name="room_create"),
    path("rooms/<int:pk>/edit/", RoomUpdateView.as_view(), name="room_edit"),
    path("rooms/<int:pk>/delete/", RoomDeleteView.as_view(), name="room_delete"),
    path(
        "rooms/<int:pk>/toggle-active/",
        RoomToggleActiveView.as_view(),
        name="room_toggle_active",
    ),
    # F-21: 全予約一覧・管理
    path(
        "reservations/", AllReservationListView.as_view(), name="all_reservation_list"
    ),
    # F-22 設備管理
    path('facilities/',                    FacilityListView.as_view(),   name='facility_list'),
    path('facilities/create/',             FacilityCreateView.as_view(), name='facility_create'),
    path('facilities/<int:pk>/edit/',      FacilityUpdateView.as_view(), name='facility_edit'),
    path('facilities/<int:pk>/delete/',    FacilityDeleteView.as_view(), name='facility_delete'),
    # F-23 建物管理
    path('buildings/',                     BuildingListView.as_view(),   name='building_list'),
    path('buildings/create/',              BuildingCreateView.as_view(), name='building_create'),
    path('buildings/<int:pk>/edit/',       BuildingUpdateView.as_view(), name='building_edit'),
    path('buildings/<int:pk>/delete/',     BuildingDeleteView.as_view(), name='building_delete'),
    # F-24 所属管理
    path('departments/',                   DepartmentListView.as_view(),   name='department_list'),
    path('departments/create/',            DepartmentCreateView.as_view(), name='department_create'),
    path('departments/<int:pk>/edit/',     DepartmentUpdateView.as_view(), name='department_edit'),
    path('departments/<int:pk>/delete/',   DepartmentDeleteView.as_view(), name='department_delete'),
    # 操作ログ
    path('operation-log/',                 OperationLogView.as_view(),     name='operation_log'),

    # F-25: CSV一括削除
    path("users/csv-delete/", CSVDeleteView.as_view(), name="csv_delete"),
    path(
        "users/csv-delete/execute/",
        CSVDeleteExecuteView.as_view(),
        name="csv_delete_execute",
    ),
]
