"""
rakumo_sync.py
==============
Rakumo（Google Workspace リソースカレンダー）と今回の予約システムを
比較・同期するためのサービスクラス。

【認証方式】
  サービスアカウント認証 + ドメイン全体の委任を使用します。

  必要な設定（settings.py または .env）：
    GOOGLE_SERVICE_ACCOUNT_FILE  ... JSONキーのパス（デフォルト: credentials/service_account.json）
    GOOGLE_DELEGATED_ADMIN       ... なりすます管理者メール（例: admin@yourdomain.com）

【Google Workspace側の事前設定】
  admin.google.com → セキュリティ → APIの制御 → ドメイン全体の委任 にて
  クライアントIDとスコープを登録済みであること。
    スコープ: https://www.googleapis.com/auth/calendar
              https://www.googleapis.com/auth/admin.directory.resource.calendar
  GOOGLE_DELEGATED_ADMIN に指定するアカウントは Google Workspace 管理者であること。
"""
import logging
import os
from datetime import datetime, timezone as dt_timezone, timedelta

logger = logging.getLogger(__name__)

# 書き込みも行うため calendar スコープ（フルアクセス）を使用
SCOPES = ['https://www.googleapis.com/auth/calendar']

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False


class RakumoSyncService:
    """
    サービスアカウント認証（ドメイン全体委任）で Google Calendar API にアクセスし、
    Rakumo の会議室予約を取得・比較・書き込みするサービスクラス。
    """

    def __init__(self):
        self.no_op = True
        self.error_message = None

        if not GOOGLE_API_AVAILABLE:
            self.error_message = "google-api-python-client がインストールされていません。"
            return

        from django.conf import settings
        sa_file = getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_FILE', '')
        delegated_admin = getattr(settings, 'GOOGLE_DELEGATED_ADMIN', '')

        if not sa_file or not os.path.exists(sa_file):
            self.error_message = (
                f"サービスアカウントJSONが見つかりません: {sa_file}\n"
                "credentials/service_account.json を配置してください。"
            )
            return

        if not delegated_admin:
            self.error_message = (
                "GOOGLE_DELEGATED_ADMIN が設定されていません。\n"
                "settings.py に管理者メールアドレスを設定してください。"
            )
            return

        self._sa_file = sa_file
        self._delegated_admin = delegated_admin
        self.no_op = False

    def _get_service(self):
        """ドメイン全体委任によるサービスアカウント認証済みの Google Calendar API サービスを返す"""
        try:
            credentials = service_account.Credentials.from_service_account_file(
                self._sa_file,
                scopes=SCOPES,
            ).with_subject(self._delegated_admin)
            return build('calendar', 'v3', credentials=credentials)
        except Exception as e:
            logger.error(f"RakumoSync: サービスアカウント認証失敗: {e}")
            self.error_message = f"サービスアカウント認証に失敗しました: {e}"
            return None

    def _build_event_body(self, reservation) -> dict:
        """予約オブジェクトから Google Calendar イベントの body を生成する"""
        from django.utils.timezone import localtime

        if reservation.is_all_day:
            date_str = localtime(reservation.start_at).strftime('%Y-%m-%d')
            body = {
                'summary':     reservation.title,
                'description': reservation.notes or '',
                'start': {'date': date_str},
                'end':   {'date': date_str},
            }
        else:
            body = {
                'summary':     reservation.title,
                'description': reservation.notes or '',
                'start': {
                    'dateTime': localtime(reservation.start_at).isoformat(),
                    'timeZone': 'Asia/Tokyo',
                },
                'end': {
                    'dateTime': localtime(reservation.end_at).isoformat(),
                    'timeZone': 'Asia/Tokyo',
                },
            }

        if reservation.participants:
            body['description'] += f'\n\n【予約者】{reservation.reserved_by}\n【参加者】\n{reservation.participants}'
        else:
            body['description'] += f'\n\n【予約者】{reservation.reserved_by}'

        # Rakumoカテゴリを「その他」に設定
        body['extendedProperties'] = {
            'shared': {
                'eventType': 'other',
            }
        }

        return body

    # ──────────────────────────────────────────────
    # 書き込み系（片方向自動連携: このシステム → Rakumo）
    # ──────────────────────────────────────────────

    def create_event(self, reservation) -> None:
        """
        予約をRakumo（リソースカレンダー）に新規作成する。
        成功時は reservation.rakumo_event_id に Google イベントIDを保存する。
        """
        if self.no_op:
            return
        calendar_id = reservation.room.google_calendar_id
        if not calendar_id:
            return  # カレンダーIDが未設定の会議室はスキップ

        try:
            svc = self._get_service()
            if svc is None:
                return
            event = svc.events().insert(
                calendarId=calendar_id,
                body=self._build_event_body(reservation),
            ).execute()
            reservation.rakumo_event_id = event.get('id', '')
            reservation.save(update_fields=['rakumo_event_id'])
            logger.info(f"RakumoSync create_event: reservation={reservation.pk} event={reservation.rakumo_event_id}")
        except Exception as e:
            logger.warning(f"RakumoSync create_event failed (reservation={reservation.pk}): {e}")

    def update_event(self, reservation) -> None:
        """
        Rakumo側の予約イベントを更新する。
        rakumo_event_id が未設定の場合は新規作成にフォールバックする。
        """
        if self.no_op:
            return
        calendar_id = reservation.room.google_calendar_id
        if not calendar_id:
            return

        if not reservation.rakumo_event_id:
            return self.create_event(reservation)

        try:
            svc = self._get_service()
            if svc is None:
                return
            svc.events().patch(
                calendarId=calendar_id,
                eventId=reservation.rakumo_event_id,
                body=self._build_event_body(reservation),
            ).execute()
            logger.info(f"RakumoSync update_event: reservation={reservation.pk}")
        except Exception as e:
            logger.warning(f"RakumoSync update_event failed (reservation={reservation.pk}): {e}")

    def delete_event(self, reservation) -> None:
        """
        Rakumo側の予約イベントを削除する。
        """
        if self.no_op or not reservation.rakumo_event_id:
            return
        calendar_id = reservation.room.google_calendar_id
        if not calendar_id:
            return

        try:
            svc = self._get_service()
            if svc is None:
                return
            svc.events().delete(
                calendarId=calendar_id,
                eventId=reservation.rakumo_event_id,
            ).execute()
            reservation.rakumo_event_id = ''
            reservation.save(update_fields=['rakumo_event_id'])
            logger.info(f"RakumoSync delete_event: reservation={reservation.pk}")
        except Exception as e:
            logger.warning(f"RakumoSync delete_event failed (reservation={reservation.pk}): {e}")

    # ──────────────────────────────────────────────
    # 読み取り系（差分確認）
    # ──────────────────────────────────────────────

    def test_connection(self, calendar_id: str) -> dict:
        """
        指定したカレンダーIDへの接続テストを行う。

        Returns:
            {
                'success': bool,
                'calendar_name': str,
                'event_count': int,
                'error': str,
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

            cal = svc.calendars().get(calendarId=calendar_id).execute()
            calendar_name = cal.get('summary', calendar_id)

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
                msg = "アクセス権限がありません。カレンダーの共有設定（「予定の編集」権限）を確認してください。"
            elif '404' in err_str:
                msg = "カレンダーが見つかりません。カレンダーIDまたは共有設定を確認してください。"
            elif '401' in err_str:
                msg = "認証エラーです。サービスアカウントJSONを確認してください。"
            else:
                msg = f"接続エラー: {err_str}"
            logger.warning(f"RakumoSync test_connection failed for {calendar_id}: {e}")
            return {'success': False, 'error': msg}

    def fetch_rakumo_events(self, calendar_id: str, date_from: datetime, date_to: datetime) -> list:
        """
        Rakumo（Google Calendar リソース）から指定期間の予約を取得する。
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
        """
        from reservations.models import Reservation

        if self.no_op:
            return {'error': self.error_message or '設定エラー'}

        if not room.google_calendar_id:
            return {'error': 'この会議室にはGoogle カレンダーIDが設定されていません。'}

        rakumo_events = self.fetch_rakumo_events(room.google_calendar_id, date_from, date_to)

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

    # ──────────────────────────────────────────────
    # Rakumo → このシステム 取り込みバッチ
    # ──────────────────────────────────────────────

    def sync_to_local(self, room, admin_user, days_ahead: int = 30) -> dict:
        """
        Rakumo（Google Calendar）の予約をこのシステムに取り込む。

        処理内容:
          1. rakumo_event_id で紐付く予約がRakumoで変更されていれば更新
          2. rakumo_event_id で紐付く予約がRakumoで削除されていればキャンセル
          3. このシステムに存在しないRakumoイベントを新規予約として作成

        Returns:
            {'created': int, 'updated': int, 'cancelled': int, 'error': str or None}
        """
        from reservations.models import Reservation
        from django.utils import timezone as dj_timezone

        if self.no_op:
            return {'created': 0, 'updated': 0, 'cancelled': 0,
                    'error': self.error_message or '設定エラー'}

        if not room.google_calendar_id:
            return {'created': 0, 'updated': 0, 'cancelled': 0,
                    'error': 'Google カレンダーIDが設定されていません。'}

        now = dj_timezone.now()
        date_from = now - timedelta(hours=1)   # 直前の変更も拾うため1時間前から
        date_to   = now + timedelta(days=days_ahead)

        try:
            rakumo_events = self.fetch_rakumo_events(
                room.google_calendar_id, date_from, date_to
            )
        except Exception as e:
            return {'created': 0, 'updated': 0, 'cancelled': 0, 'error': str(e)}

        rakumo_map = {e['id']: e for e in rakumo_events}

        # rakumo_event_id で紐付いているローカル予約
        local_linked = {
            r.rakumo_event_id: r
            for r in Reservation.objects.filter(
                room=room,
                is_cancelled=False,
                start_at__gte=date_from,
                start_at__lt=date_to,
                rakumo_event_id__gt='',
            )
        }

        created = updated = cancelled = 0

        # ── Case 1: Rakumoで変更・削除された予約の反映 ──
        for rakumo_id, reservation in local_linked.items():
            if rakumo_id not in rakumo_map:
                # Rakumoで削除された → キャンセル
                reservation.is_cancelled = True
                reservation.save(update_fields=['is_cancelled'])
                cancelled += 1
                logger.info(
                    f"RakumoSync←: キャンセル reservation={reservation.pk} "
                    f"(Rakumoから削除)"
                )
            else:
                # Rakumoで変更されたか確認
                event = rakumo_map[rakumo_id]
                fields_changed = []
                if reservation.title != event['title']:
                    reservation.title = event['title']
                    fields_changed.append('title')
                if reservation.start_at != event['start']:
                    reservation.start_at = event['start']
                    fields_changed.append('start_at')
                if reservation.end_at != event['end']:
                    reservation.end_at = event['end']
                    fields_changed.append('end_at')
                if fields_changed:
                    reservation.save(update_fields=fields_changed)
                    updated += 1
                    logger.info(
                        f"RakumoSync←: 更新 reservation={reservation.pk} "
                        f"変更項目={fields_changed}"
                    )

        # ── Case 2: Rakumoにあってローカルにないイベントを新規作成 ──
        for event_id, event in rakumo_map.items():
            if event_id in local_linked:
                continue  # 既に紐付き済みはスキップ

            # タイトル＋開始時刻で照合（このシステムから連携したが未リンクの場合）
            existing = Reservation.objects.filter(
                room=room,
                is_cancelled=False,
                title=event['title'],
                start_at=event['start'],
                rakumo_event_id='',
            ).first()

            if existing:
                # 既存予約にrakumo_event_idを紐付け
                existing.rakumo_event_id = event_id
                existing.save(update_fields=['rakumo_event_id'])
                logger.info(
                    f"RakumoSync←: 紐付け reservation={existing.pk} "
                    f"event={event_id}"
                )
            else:
                # Rakumoで直接作成された予約を新規登録
                Reservation.objects.create(
                    room=room,
                    user=admin_user,
                    reserved_by=event['organizer'] or 'Rakumo経由',
                    title=event['title'],
                    start_at=event['start'],
                    end_at=event['end'],
                    is_all_day=event['is_all_day'],
                    rakumo_event_id=event_id,
                    notes='※ Rakumoから自動同期',
                )
                created += 1
                logger.info(
                    f"RakumoSync←: 新規作成 event={event_id} "
                    f"title={event['title']}"
                )

        return {'created': created, 'updated': updated, 'cancelled': cancelled, 'error': None}
