from django.db import models
from django.conf import settings
from django.utils import timezone

User = settings.AUTH_USER_MODEL


# ──────────────────────────────────────────────
# T-04 建物マスタ
# ──────────────────────────────────────────────
class Building(models.Model):
    """建物マスタ (T-04)"""

    name = models.CharField(max_length=100, unique=True, verbose_name="建物名称")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="作成日時")

    class Meta:
        db_table = "buildings"
        verbose_name = "建物"
        verbose_name_plural = "建物"

    def __str__(self) -> str:
        return self.name


# ──────────────────────────────────────────────
# T-05 設備マスタ
# ──────────────────────────────────────────────
class Facility(models.Model):
    """設備マスタ (T-05)"""

    name = models.CharField(max_length=100, unique=True, verbose_name="設備名称")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="作成日時")

    class Meta:
        db_table = "facilities"
        verbose_name = "設備"
        verbose_name_plural = "設備"

    def __str__(self) -> str:
        return self.name


# ──────────────────────────────────────────────
# T-06 会議室マスタ
# ──────────────────────────────────────────────
class Room(models.Model):
    """会議室マスタ (T-06)"""

    name = models.CharField(max_length=100, unique=True, verbose_name="室名")
    capacity = models.PositiveIntegerField(verbose_name="収容人数")
    building = models.ForeignKey(
        Building,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="building_id",
        related_name="rooms",
        verbose_name="建物",
    )
    floor = models.IntegerField(null=True, blank=True, verbose_name="階数")
    is_active = models.BooleanField(default=True, verbose_name="利用可能")

    # Rakumo連携: Google Workspace リソースカレンダー ID
    google_calendar_id = models.CharField(
        max_length=255, blank=True, default='',
        verbose_name="Google カレンダーID（Rakumo会議室）",
        help_text="例: xxxxx@resource.calendar.google.com"
    )

    # T-07 room_facilities を経由した設備との M2N
    facilities = models.ManyToManyField(
        Facility,
        through="RoomFacility",
        blank=True,
        verbose_name="設備",
    )

    # T-08 department_rooms を経由した所属との M2N
    departments = models.ManyToManyField(
        "accounts.Department",
        through="DepartmentRoom",
        blank=True,
        verbose_name="所属別表示設定",
    )

    class Meta:
        db_table = "rooms"
        verbose_name = "会議室"
        verbose_name_plural = "会議室"

    def __str__(self) -> str:
        return self.name


# ──────────────────────────────────────────────
# T-07 会議室設備中間テーブル
# ──────────────────────────────────────────────
class RoomFacility(models.Model):
    """会議室と設備の M:N 中間テーブル (T-07)
    room 削除時は CASCADE で連鎖削除される。
    """

    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        db_column="room_id",
        verbose_name="会議室",
    )
    facility = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE,
        db_column="facility_id",
        verbose_name="設備",
    )

    class Meta:
        db_table = "room_facilities"
        unique_together = [("room", "facility")]
        verbose_name = "会議室設備"
        verbose_name_plural = "会議室設備"

    def __str__(self) -> str:
        return f"{self.room} — {self.facility}"


# ──────────────────────────────────────────────
# T-08 所属別会議室テーブル
# ──────────────────────────────────────────────
class DepartmentRoom(models.Model):
    """所属ごとのカレンダー初期表示対象会議室マッピング (T-08)
    room 削除時は CASCADE で連鎖削除される。
    """

    department = models.ForeignKey(
        "accounts.Department",
        on_delete=models.CASCADE,
        db_column="department_id",
        verbose_name="所属",
    )
    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        db_column="room_id",
        verbose_name="会議室",
    )

    class Meta:
        db_table = "department_rooms"
        unique_together = [("department", "room")]
        verbose_name = "所属別会議室"
        verbose_name_plural = "所属別会議室"

    def __str__(self) -> str:
        return f"{self.department} — {self.room}"


# ──────────────────────────────────────────────
# T-09 予約
# ──────────────────────────────────────────────
class Reservation(models.Model):
    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        related_name="reservations",
        verbose_name="会議室",
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    reserved_by = models.CharField(max_length=100)
    purpose = models.CharField(max_length=200, blank=True)

    title = models.CharField(max_length=200)
    participants = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    start_at = models.DateTimeField()
    end_at = models.DateTimeField()

    is_all_day = models.BooleanField(default=False, verbose_name='終日')
    is_cancelled = models.BooleanField(default=False)

    # 予約の表示色（カレンダー上の色）
    color = models.CharField(
        max_length=7, default='#3182CE', blank=True,
        verbose_name='色'
    )

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    # 【追加 F-04-R10】繰り返し予定
    recurrence_rule = models.CharField(
        max_length=255, blank=True, default='',
        verbose_name='繰り返しルール（RRULE）'
    )
    recurrence_id = models.DateTimeField(
        null=True, blank=True, verbose_name='繰り返し識別日時'
    )
    parent_reservation = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='recurrence_instances',
        verbose_name='親予約'
    )
    # Rakumo連携: リソースカレンダーのイベントID
    rakumo_event_id = models.CharField(
        max_length=255, blank=True, default='',
        verbose_name='Rakumo イベントID'
    )

    # Rakumo連携: この予約がRakumo（本社）側で作成された予約かどうか
    is_rakumo_source = models.BooleanField(
        default=False,
        verbose_name='Rakumo発信予約',
        help_text='Rakumo（本社Google Calendar）から同期された予約の場合 True。管理者でもキャンセル不可。',
    )

    class Meta:
        db_table = "reservations"
        verbose_name = "予約"
        verbose_name_plural = "予約"

    def __str__(self):
        return self.title



# ──────────────────────────────────────────────
# T-10 操作ログ
# ──────────────────────────────────────────────
class OperationLog(models.Model):
    """予約操作ログ"""

    ACTION_CREATE = 'create'
    ACTION_UPDATE = 'update'
    ACTION_CANCEL = 'cancel'
    ACTION_MOVE   = 'move'
    ACTION_CHOICES = [
        (ACTION_CREATE, '予約作成'),
        (ACTION_UPDATE, '予約変更'),
        (ACTION_CANCEL, '予約キャンセル'),
        (ACTION_MOVE,   '予約移動'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='operation_logs',
        verbose_name='操作ユーザー',
    )
    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
        verbose_name='操作種別',
    )
    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='logs',
        verbose_name='予約',
    )
    # 操作時点のスナップショット（予約が削除されても残る）
    room_name  = models.CharField(max_length=100, verbose_name='会議室名')
    title      = models.CharField(max_length=200, verbose_name='件名')
    start_at   = models.DateTimeField(verbose_name='開始日時')
    end_at     = models.DateTimeField(verbose_name='終了日時')
    detail     = models.TextField(blank=True, verbose_name='変更内容')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='IPアドレス')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='操作日時')

    class Meta:
        db_table = 'operation_logs'
        ordering = ['-created_at']
        verbose_name = '操作ログ'
        verbose_name_plural = '操作ログ'

    def __str__(self):
        return f"{self.get_action_display()} – {self.title} ({self.created_at:%Y-%m-%d %H:%M})"
