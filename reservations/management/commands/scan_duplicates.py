"""
既存の全予約を対象に重複チェックを実行するコマンド。
初回セットアップ時や手動でスキャンしたいときに使用する。

使い方:
    python manage.py scan_duplicates
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = '既存の全予約を対象に重複チェックを実行し、DuplicateAlert を作成する'

    def handle(self, *args, **options):
        from reservations.models import Reservation, DuplicateAlert
        from reservations.services.duplicate_check import detect_and_save

        # キャンセル済み・終日以外の有効な予約を対象
        reservations = Reservation.objects.filter(
            is_cancelled=False,
            is_all_day=False,
        ).order_by('start_at')

        total = reservations.count()
        self.stdout.write(f'対象予約: {total}件')

        new_alerts = 0
        for r in reservations:
            alerts = detect_and_save(r)
            new_alerts += len(alerts)

        existing = DuplicateAlert.objects.filter(is_resolved=False).count()
        self.stdout.write(
            f'完了 — 新規アラート: {new_alerts}件 / 未解消アラート合計: {existing}件'
        )
