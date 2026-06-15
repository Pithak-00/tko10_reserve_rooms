"""
duplicate_check.py
==================
予約の重複を検知し、DuplicateAlert に保存するサービス。

検知タイミング:
  - 予約作成・変更時（views.py から呼び出し）
  - Rakumo同期バッチ実行時（sync_from_rakumo コマンドから呼び出し）
"""
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)


def detect_and_save(reservation) -> list:
    """
    指定予約と重複する他の予約を検索し、DuplicateAlert を作成する。

    Args:
        reservation: チェック対象の Reservation インスタンス

    Returns:
        新規作成された DuplicateAlert のリスト
    """
    from reservations.models import Reservation, DuplicateAlert

    if reservation.is_cancelled or reservation.is_all_day:
        return []

    # 同じ会議室・時間帯が重なる他の有効な予約を検索
    overlapping = Reservation.objects.filter(
        room=reservation.room,
        is_cancelled=False,
        is_all_day=False,
        start_at__lt=reservation.end_at,
        end_at__gt=reservation.start_at,
    ).exclude(pk=reservation.pk)

    new_alerts = []
    for other in overlapping:
        # 組み合わせを正規化（IDの小さい方を reservation_a にする）
        a, b = (reservation, other) if reservation.pk < other.pk else (other, reservation)
        alert, created = DuplicateAlert.objects.get_or_create(
            reservation_a=a,
            reservation_b=b,
            defaults={
                'room': reservation.room,
                'is_resolved': False,
            },
        )
        if created:
            new_alerts.append(alert)
            logger.warning(
                f"重複検知: room={reservation.room.name} "
                f"[{a.title} {a.start_at:%H:%M}–{a.end_at:%H:%M}] × "
                f"[{b.title} {b.start_at:%H:%M}–{b.end_at:%H:%M}]"
            )

    return new_alerts


def resolve_if_no_longer_overlapping(reservation) -> int:
    """
    予約が変更・キャンセルされたとき、解消済みになったアラートを更新する。

    Returns:
        解消済みにしたアラート件数
    """
    from reservations.models import DuplicateAlert

    resolved_count = 0
    alerts = DuplicateAlert.objects.filter(
        is_resolved=False,
    ).filter(
        reservation_a=reservation,
    ) | DuplicateAlert.objects.filter(
        is_resolved=False,
    ).filter(
        reservation_b=reservation,
    )

    for alert in alerts:
        a, b = alert.reservation_a, alert.reservation_b
        # どちらかがキャンセル済み、または時間が重ならなくなった場合は解消
        if a.is_cancelled or b.is_cancelled:
            _mark_resolved(alert)
            resolved_count += 1
        elif not (a.start_at < b.end_at and a.end_at > b.start_at):
            _mark_resolved(alert)
            resolved_count += 1

    return resolved_count


def _mark_resolved(alert) -> None:
    alert.is_resolved = True
    alert.resolved_at = timezone.now()
    alert.save(update_fields=['is_resolved', 'resolved_at'])
    logger.info(f"重複解消: DuplicateAlert id={alert.pk}")
