"""
rakumo_sync.py
==============
Rakumo（Google Workspace リソースカレンダー）と今回の予約システムを
比較・同期するためのサービスクラス。

【認証方式】
  サービスアカウント認証（credentials/service_account.json）を使用します。
  ユーザーごとのOAuth認証・GOOGLE_DELEGATED_ADMIN 設定は不要です。

  必要な設定（settings.py または .env）：
    GOOGLE_SERVICE_ACCOUNT_FILE  ... JSONキーのパス（デフォルト: credentials/service_account.json）

【Google Workspace側の事前設定】
  各会議室のリソースカレンダーをサービスアカウントのメールアドレスに直接共有する。
    roomreserve@roomreserve-498906.iam.gserviceaccount.com
  ドメイン全体の委任（GOOGLE_DELEGATED_ADMIN）は不要です。
"""
import logging
import os
from datetime import datetime, timezone as dt_timezone, timedelta

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False


class RakumoSyncService:
    """
    サービスアカウント認証で Google Calendar API にアクセスし、
    Rakumo の会議室予約を取得・比較するサービスクラス。
    """

    def __init__(self):
        self.no_op = True
        self.error_message = None

        if not GOOGLE_API_AVAILABLE:
            self.error_message = "google-api-python-client がインストールされていません。"
            return

        from django.conf import settings
        sa_file = getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_FILE', '')

        if not sa_file or not os.path.exists(sa_file):
            self.error_message = (
                f"サービスアカウントJSONが見つかりません: {sa_file}\n"
                "credentials/service_account.json を配置してください。"
            )
            return

        self._sa_file = sa_file
        self.no_op = False

    def _get_service(self):
        """サービスアカウント認証済みの Google Calendar API サービスを返す"""
        try:
            credentials = service_account.Credentials.from_service_account_file(
                self._sa_file,
                scopes=SCOPES,
            )
            return build('calendar', 'v3', credentials=credentials)
        except Exception as e:
            logger.error(f"RakumoSync: サービスアカウント認証失敗: {e}")
            self.error_message = f"サービスアカウント認証に失敗しました: {e}"
            return None

    def test_connection(self, calendar_id: str) -> dict:
        """
        指定したカレンダーIDへの接続テストを行う。

        Returns:
            {
                'success': bool,
                'calendar_name': str,   # カレンダー名（成功時）
                'event_count': int,     # 直近7日間のイベント件数（成功時）
                'error': str,           # エラーメッセージ（失敗時）
            }
        """
        if self.no_op:
            return {'success': False, 'error': self.error_message or '不明なエラー'}
        if not calendar_id:
            return {'success': False, 'error': 'Google カレンダー ID が設定されていません。'}

        try:
            svc = self._get_service()
            if svc is None:
                return {'success': False, 'error': self.error_message or 'API サービスの初期化に失敗しました。'}

            # カレンダー情報を取得
            cal = svc.calendars().get(calendarId=calendar_id).execute()
            calendar_name = cal.get('summary', calendar_id)

            # 直近7日間のイベント件数を確認
            from django.utils import timezone
            now = timezone.now()
            events_result = svc.events().list(
                calendarId=calendar_id,
                timeMin=now.isoformat(),
                timeMax=(now + timedelta(days=7)).isoformat(),
                singleEvents=True,
                maxResults=100,
            ).execute()

            return {
                'success': True,
                'calendar_name': calendar_name,
                'event_count': len(events_result.get('items', [])),
            }

        except Exception as e:
            err_str = str(e)
            if '403' in err_str:
                msg = "アクセス権限がありません。ドメイン全体の委任設定またはカレンダー共有設定を確認してください。"
            elif '404' in err_str:
                msg = "カレンダーが見つかりません。カレンダーIDを確認してください。"
            elif '401' in err_str:
                msg = "認証エラーです。サービスアカウントJSONとGOOGLE_DELEGATED_ADMINを確認してください。"
            else:
                msg = f"接続エラー: {err_str}"
            logger.warning(f"RakumoSync test_connection failed for {calendar_id}: {e}")
            return {'success': False, 'error': msg}

    def fetch_rakumo_events(self, calendar_id: str, date_from: datetime, date_to: datetime) -> list:
        """
        Rakumo（Google Calendar リソース）から指定期間の予約を取得する。

        Returns:
            list of {
                'id': str,
                'title': str,
                'start': datetime,
                'end': datetime,
                'organizer': str,
                'is_all_day': bool,
            }
        """
        if self.no_op or not calendar_id:
            return []

        try:
            svc = self._get_service()
            if svc is None:
                return []

            events_result = svc.events().list(
                calendarId=calendar_id,
                timeMin=date_from.isoformat(),
                timeMax=date_to.isoformat(),
                singleEvents=True,
                orderBy='startTime',
                maxResults=500,
            ).execute()

            results = []
            for item in events_result.get('items', []):
                start_raw = item['start']
                end_raw   = item['end']
                is_all_day = 'date' in start_raw and 'dateTime' not in start_raw

                if is_all_day:
                    start_dt = datetime.fromisoformat(start_raw['date']).replace(tzinfo=dt_timezone.utc)
                    end_dt   = datetime.fromisoformat(end_raw['date']).replace(tzinfo=dt_timezone.utc)
                else:
                    start_dt = datetime.fromisoformat(start_raw['dateTime'])
                    end_dt   = datetime.fromisoformat(end_raw['dateTime'])
                    if start_dt.tzinfo is None:
                        start_dt = start_dt.replace(tzinfo=dt_timezone.utc)
                    if end_dt.tzinfo is None:
                        end_dt = end_dt.replace(tzinfo=dt_timezone.utc)

                organizer = (
                    item.get('organizer', {}).get('displayName') or
                    item.get('organizer', {}).get('email', '')
                )

                results.append({
                    'id':         item.get('id', ''),
                    'title':      item.get('summary', '（タイトルなし）'),
                    'start':      start_dt,
                    'end':        end_dt,
                    'organizer':  organizer,
                    'is_all_day': is_all_day,
                })
            return results

        except Exception as e:
            logger.warning(f"RakumoSync fetch_events failed for {calendar_id}: {e}")
            return []

    def compare_with_local(self, room, date_from: datetime, date_to: datetime) -> dict:
        """
        Rakumo側の予約とローカルDBの予約を比較し差分を返す。

        Returns:
            {
                'rakumo_events':   list,
                'local_events':    list,
                'only_in_rakumo':  list,
                'only_in_local':   list,
                'matched':         list,
                'error':           str or None,
            }
        """
        from reservations.models import Reservation

        if self.no_op:
            return {'error': self.error_message or '設定エラー'}

        if not room.google_calendar_id:
            return {'error': 'この会議室にはGoogle カレンダーIDが設定されていません。'}

        # Rakumo側取得
        rakumo_events = self.fetch_rakumo_events(room.google_calendar_id, date_from, date_to)

        # ローカル側取得
        local_qs = Reservation.objects.filter(
            room=room,
            is_cancelled=False,
            start_at__gte=date_from,
            start_at__lt=date_to,
        ).order_by('start_at')

        local_events = [{
            'id':         r.id,
            'title':      r.title,
            'start':      r.start_at,
            'end':        r.end_at,
            'organizer':  r.reserved_by,
            'is_all_day': r.is_all_day,
        } for r in local_qs]

        # 照合キー：タイトル + 開始時刻（分単位、JST）
        def make_key(title, start_dt):
            from zoneinfo import ZoneInfo
            jst = ZoneInfo('Asia/Tokyo')
            start_jst = start_dt.astimezone(jst) if hasattr(start_dt, 'astimezone') else start_dt
            return f"{title.strip().lower()}|{start_jst.strftime('%Y%m%d%H%M')}"

        rakumo_keys = {make_key(e['title'], e['start']): e for e in rakumo_events}
        local_keys  = {make_key(e['title'], e['start']): e for e in local_events}

        return {
            'rakumo_events':  rakumo_events,
            'local_events':   local_events,
            'only_in_rakumo': [e for k, e in rakumo_keys.items() if k not in local_keys],
            'only_in_local':  [e for k, e in local_keys.items()  if k not in rakumo_keys],
            'matched':        [e for k, e in rakumo_keys.items() if k in local_keys],
            'error':          None,
        }
