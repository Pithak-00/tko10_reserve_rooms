"""
rakumo_sync.py
==============
Rakumo（Google Workspace リソースカレンダー）と今回の予約システムを
比較・同期するためのサービスクラス。

【動作の仕組み】
  Rakumoカレンダーは Google Workspace のリソースカレンダーと双方向リアルタイム同期
  しています。そのため Google Calendar API でリソースカレンダーを読み書きすることで
  Rakumo側の予約情報を取得・更新できます。

【認証方式】
  管理者ユーザーの OAuth トークン（既存の google_sync.py と同じ仕組み）を使用します。
  リソースカレンダーへのアクセスには Google Workspace 管理者権限が必要です。

【Step 1 スコープ】
  - Rakumo側の会議室予約を取得して表示
  - 今回のシステムの予約と比較し差分を検出
"""
import logging
from datetime import datetime, timezone as dt_timezone, timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False


class RakumoSyncService:
    """
    Google Calendar API 経由で Rakumo の会議室予約を取得し、
    ローカル予約と比較するサービスクラス。
    """

    def __init__(self, user):
        self.user = user
        self.no_op = True
        self.error_message = None

        if not GOOGLE_API_AVAILABLE:
            self.error_message = "google-api-python-client がインストールされていません。"
            return

        try:
            from accounts.models import UserGoogleToken
            from django.conf import settings
            self.token_obj = user.google_token
            self._settings = settings
            if not self.token_obj.sync_enabled:
                self.error_message = "Google カレンダー連携が有効になっていません。マイページから連携してください。"
                return
            self.no_op = False
        except Exception as e:
            self.error_message = f"Google アカウントが連携されていません: {e}"

    def _refresh_token_if_needed(self):
        """期限切れトークンを更新する"""
        import requests
        now = timezone.now()
        if self.token_obj.token_expiry and self.token_obj.token_expiry <= now:
            try:
                resp = requests.post('https://oauth2.googleapis.com/token', data={
                    'client_id':     self._settings.GOOGLE_CLIENT_ID,
                    'client_secret': self._settings.GOOGLE_CLIENT_SECRET,
                    'refresh_token': self.token_obj.refresh_token,
                    'grant_type':    'refresh_token',
                }, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                self.token_obj.access_token = data['access_token']
                self.token_obj.token_expiry = now + timedelta(seconds=data.get('expires_in', 3600))
                self.token_obj.save(update_fields=['access_token', 'token_expiry'])
            except Exception as e:
                logger.error(f'RakumoSync: Token refresh failed: {e}')
                self.no_op = True
                self.error_message = f"トークンの更新に失敗しました: {e}"

    def _get_service(self):
        """Google Calendar API サービスオブジェクトを返す"""
        self._refresh_token_if_needed()
        if self.no_op:
            return None
        creds = Credentials(
            token=self.token_obj.access_token,
            refresh_token=self.token_obj.refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=self._settings.GOOGLE_CLIENT_ID,
            client_secret=self._settings.GOOGLE_CLIENT_SECRET,
        )
        return build('calendar', 'v3', credentials=creds)

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

            # 直近7日間のイベント数を確認
            now = timezone.now()
            time_min = now.isoformat()
            time_max = (now + timedelta(days=7)).isoformat()
            events_result = svc.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                maxResults=100,
            ).execute()
            events = events_result.get('items', [])

            return {
                'success': True,
                'calendar_name': calendar_name,
                'event_count': len(events),
            }
        except Exception as e:
            err_str = str(e)
            if '403' in err_str:
                msg = "アクセス権限がありません。管理者権限または共有設定を確認してください。"
            elif '404' in err_str:
                msg = "カレンダーが見つかりません。カレンダーIDを確認してください。"
            elif '401' in err_str:
                msg = "認証エラーです。Google アカウントを再連携してください。"
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
                    # タイムゾーンが付いていない場合は UTC とみなす
                    if start_dt.tzinfo is None:
                        start_dt = start_dt.replace(tzinfo=dt_timezone.utc)
                    if end_dt.tzinfo is None:
                        end_dt = end_dt.replace(tzinfo=dt_timezone.utc)

                organizer = item.get('organizer', {}).get('displayName') or \
                            item.get('organizer', {}).get('email', '')

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
                'rakumo_events':   list,   # Rakumo 側の予約一覧
                'local_events':    list,   # ローカル側の予約一覧
                'only_in_rakumo':  list,   # Rakumo にしかない予約
                'only_in_local':   list,   # ローカルにしかない予約
                'matched':         list,   # 両方に存在する予約（タイトル+開始時刻で照合）
                'error':           str,    # エラー時のみ
            }
        """
        from reservations.models import Reservation

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
            'id':        r.id,
            'title':     r.title,
            'start':     r.start_at,
            'end':       r.end_at,
            'organizer': r.reserved_by,
            'is_all_day': r.is_all_day,
        } for r in local_qs]

        # 照合キー：タイトル + 開始時刻（分単位）
        def make_key(title, start_dt):
            import pytz
            jst = pytz.timezone('Asia/Tokyo')
            if hasattr(start_dt, 'astimezone'):
                start_jst = start_dt.astimezone(jst)
            else:
                start_jst = start_dt
            return f"{title.strip().lower()}|{start_jst.strftime('%Y%m%d%H%M')}"

        rakumo_keys = {make_key(e['title'], e['start']): e for e in rakumo_events}
        local_keys  = {make_key(e['title'], e['start']): e for e in local_events}

        only_in_rakumo = [e for k, e in rakumo_keys.items() if k not in local_keys]
        only_in_local  = [e for k, e in local_keys.items()  if k not in rakumo_keys]
        matched        = [e for k, e in rakumo_keys.items() if k in local_keys]

        return {
            'rakumo_events':  rakumo_events,
            'local_events':   local_events,
            'only_in_rakumo': only_in_rakumo,
            'only_in_local':  only_in_local,
            'matched':        matched,
            'error':          None,
        }
