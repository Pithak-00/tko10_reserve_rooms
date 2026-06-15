"""
Rakumo → このシステムへの定期同期コマンド。

使い方:
    python manage.py sync_from_rakumo
    python manage.py sync_from_rakumo --days 60   # 取り込み日数を変更（デフォルト: 30日）
    python manage.py sync_from_rakumo --room-id 1 # 特定の会議室のみ同期
"""
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Rakumo（Google Calendar）からこのシステムへ予約を同期する'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=30,
            help='何日先まで同期するか（デフォルト: 30日）'
        )
        parser.add_argument(
            '--room-id', type=int, default=None,
            help='特定の会議室IDのみ同期（省略時は全会議室）'
        )

    def handle(self, *args, **options):
        from reservations.models import Room
        from reservations.services.rakumo_sync import RakumoSyncService
        from accounts.models import User

        days = options['days']
        room_id = options.get('room_id')

        # 管理者ユーザーを取得（Rakumo経由の予約はこのユーザーに紐付ける）
        admin_user = (
            User.objects.filter(is_superuser=True).first()
            or User.objects.filter(role='admin').first()
        )
        if not admin_user:
            self.stderr.write('エラー: 管理者ユーザーが見つかりません。')
            return

        # 会議室の取得
        rooms_qs = Room.objects.filter(is_active=True).exclude(google_calendar_id='')
        if room_id:
            rooms_qs = rooms_qs.filter(pk=room_id)

        if not rooms_qs.exists():
            self.stdout.write('Google カレンダーIDが設定された会議室がありません。')
            return

        svc = RakumoSyncService()
        if svc.no_op:
            self.stderr.write(f'エラー: {svc.error_message}')
            return

        total = {'created': 0, 'updated': 0, 'cancelled': 0}
        started_at = timezone.now()

        for room in rooms_qs:
            self.stdout.write(f'同期中: {room.name} ({room.google_calendar_id})')
            result = svc.sync_to_local(room, admin_user, days_ahead=days)

            if result.get('error'):
                self.stderr.write(f'  エラー: {result["error"]}')
                continue

            c, u, ca = result['created'], result['updated'], result['cancelled']
            self.stdout.write(f'  → 新規: {c}件 / 更新: {u}件 / キャンセル: {ca}件')
            total['created']   += c
            total['updated']   += u
            total['cancelled'] += ca

        # 同期後に重複チェックを実行
        from reservations.models import Reservation
        from reservations.services.duplicate_check import detect_and_save, resolve_if_no_longer_overlapping
        active_reservations = Reservation.objects.filter(
            is_cancelled=False,
            is_all_day=False,
            room__in=rooms_qs,
        )
        dup_count = 0
        for r in active_reservations:
            resolve_if_no_longer_overlapping(r)
            dup_count += len(detect_and_save(r))
        if dup_count:
            self.stdout.write(f'⚠ 重複アラート: {dup_count}件検知')

        elapsed = (timezone.now() - started_at).total_seconds()
        self.stdout.write(
            f'\n完了 ({elapsed:.1f}秒) — '
            f'合計: 新規 {total["created"]}件 / 更新 {total["updated"]}件 / キャンセル {total["cancelled"]}件'
        )
