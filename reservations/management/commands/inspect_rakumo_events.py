"""
Rakumoイベントの内部データを調査するコマンド。
Rakumoで作成したイベントの拡張プロパティ（extendedProperties）を確認するために使用する。

使い方:
    python manage.py inspect_rakumo_events <calendar_id>
"""
import json
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Rakumoイベントの内部データ（extendedProperties等）を表示する'

    def add_arguments(self, parser):
        parser.add_argument('calendar_id', type=str, help='GoogleカレンダーID')
        parser.add_argument('--days', type=int, default=7, help='過去N日分を取得（デフォルト: 7）')

    def handle(self, *args, **options):
        calendar_id = options['calendar_id']
        days = options['days']

        try:
            from reservations.services.rakumo_sync import RakumoSyncService
            svc_wrapper = RakumoSyncService()
            if svc_wrapper.no_op:
                self.stderr.write(f'エラー: {svc_wrapper.error_message}')
                return

            svc = svc_wrapper._get_service()
            if svc is None:
                self.stderr.write('Google Calendar API サービスの初期化に失敗しました。')
                return

            now = timezone.now()
            time_min = (now - timedelta(days=days)).isoformat()
            time_max = now.isoformat()

            self.stdout.write(f'カレンダーID: {calendar_id}')
            self.stdout.write(f'取得期間: 過去{days}日分')
            self.stdout.write('=' * 60)

            events_result = svc.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime',
                maxResults=20,
            ).execute()

            items = events_result.get('items', [])
            if not items:
                self.stdout.write('該当期間にイベントが見つかりませんでした。')
                return

            self.stdout.write(f'{len(items)}件のイベントが見つかりました。\n')

            for i, event in enumerate(items, 1):
                self.stdout.write(f'[{i}] タイトル: {event.get("summary", "（なし）")}')
                self.stdout.write(f'    ID: {event.get("id")}')
                start = event.get('start', {})
                self.stdout.write(f'    開始: {start.get("dateTime") or start.get("date")}')

                ext = event.get('extendedProperties')
                if ext:
                    self.stdout.write('    【extendedProperties】')
                    self.stdout.write(json.dumps(ext, ensure_ascii=False, indent=6))
                else:
                    self.stdout.write('    【extendedProperties】なし')

                # その他のRakumo関連フィールドも確認
                for field in ['colorId', 'transparency', 'visibility', 'source']:
                    val = event.get(field)
                    if val:
                        self.stdout.write(f'    {field}: {val}')

                self.stdout.write('')

        except Exception as e:
            self.stderr.write(f'エラー: {e}')
