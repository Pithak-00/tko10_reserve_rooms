import json
import logging
import calendar as cal_module
from collections import defaultdict

from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.views import View
from django.views.generic import TemplateView, CreateView, ListView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from datetime import date, datetime, timedelta, time as dt_time, timezone as dt_tz
from django.utils import timezone
from django.utils.timezone import localtime
from django.urls import reverse
from django.conf import settings
from django.db import transaction

from .models import Room, Reservation, Facility, Building, RoomFacility, DepartmentRoom, OperationLog
from .forms import ReservationForm
from accounts.models import Department, User, UserGoogleToken
try:
    from .services.google_sync import GoogleSyncService
    GOOGLE_SYNC_AVAILABLE = True
except ImportError:
    GOOGLE_SYNC_AVAILABLE = False
    class GoogleSyncService:
        """google-api-python-client 未インストール時のダミー"""
        def __init__(self, user): pass
        def create_event(self, r): pass
        def update_event(self, r): pass
        def delete_event(self, r): pass

from .services.rakumo_sync import RakumoSyncService

logger = logging.getLogger(__name__)

# google_auth_oauthlib は F-04-R09 Google 同期機能でのみ使用
# pip install google-auth-oauthlib google-api-python-client python-dateutil が必要
try:
    from google_auth_oauthlib.flow import Flow
    GOOGLE_OAUTH_AVAILABLE = True
except ImportError:
    GOOGLE_OAUTH_AVAILABLE = False

try:
    from dateutil.rrule import rrulestr
    DATEUTIL_AVAILABLE = True
except ImportError:
    DATEUTIL_AVAILABLE = False


def home(request):
    return HttpResponse("meeting room reservation system")


def _get_client_ip(request):
    """X-Forwarded-For → REMOTE_ADDR の順で IP を取得"""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _log_operation(request, action, reservation, detail=''):
    """予約操作ログを非同期的に記録する（例外は握り潰してメイン処理に影響させない）"""
    try:
        OperationLog.objects.create(
            user=request.user if request.user.is_authenticated else None,
            action=action,
            reservation=reservation,
            room_name=reservation.room.name if reservation.room_id else '',
            title=reservation.title,
            start_at=reservation.start_at,
            end_at=reservation.end_at,
            detail=detail,
            ip_address=_get_client_ip(request),
        )
    except Exception as e:
        logger.warning(f'OperationLog 書き込み失敗: {e}')


def _conflict_exists(room_id, start_at, end_at, exclude_pk=None, is_all_day=False):
    """
    排他制御付き重複チェック。必ず transaction.atomic() ブロック内で呼ぶこと。
    競合がなければ None、あればエラーメッセージ文字列を返す。
    """
    qs = Reservation.objects.filter(room_id=room_id, is_cancelled=False)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)

    # ① 通常の時間重複
    if qs.filter(start_at__lt=end_at, end_at__gt=start_at).exists():
        return 'その時間帯は既に予約されています'

    # ② 同日の終日予約との重複（終日予約は 00:00〜00:30 で保存されるため別途チェック）
    tz = timezone.get_current_timezone()
    day = localtime(start_at).date()
    day_start = timezone.make_aware(datetime.combine(day, dt_time(0, 0)), tz)
    day_end   = day_start + timedelta(days=1)
    if qs.filter(is_all_day=True, start_at__gte=day_start, start_at__lt=day_end).exists():
        return 'その日は終日予約が入っているため予約できません'

    # ③ 終日予約で同日に通常予約が存在する
    if is_all_day and qs.filter(is_all_day=False, start_at__gte=day_start, start_at__lt=day_end).exists():
        return 'その日は既に予約が入っているため終日予約できません'

    return None


def _generate_recurrence_instances(parent: Reservation, until=None):
    """親予約の recurrence_rule からインスタンス予約を一括生成"""
    if not DATEUTIL_AVAILABLE:
        logger.warning('python-dateutil が未インストールのため繰り返し生成をスキップ')
        return
    duration = parent.end_at - parent.start_at
    rule_str = f'DTSTART:{parent.start_at.strftime("%Y%m%dT%H%M%SZ")}\nRRULE:{parent.recurrence_rule}'
    rule = rrulestr(rule_str)
    instances = []
    for dt in rule:
        if until and dt.date() > until: break
        if dt == parent.start_at: continue  # 親自身をスキップ
        instances.append(Reservation(
            room=parent.room,
            user=parent.user,
            reserved_by=parent.reserved_by,
            title=parent.title,
            start_at=dt,
            end_at=dt + duration,
            parent_reservation=parent,
            recurrence_id=dt,
        ))
    Reservation.objects.bulk_create(instances)


# F-04
class CalendarView(LoginRequiredMixin, TemplateView):
    template_name = 'reservations/calendar.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        view  = self.request.GET.get('view', 'week')  # day/week/month
        date_str = self.request.GET.get('date')
        try:
            target = datetime.strptime(date_str, '%Y-%m-%d').date()
        except (TypeError, ValueError):
            target = date.today()

        # 会議室一覧（JSON として埋め込み）
        rooms = Room.objects.filter(is_active=True).order_by('name')
        rooms_json = json.dumps([
            {'id': r.id, 'name': r.name}
            for r in rooms
        ], ensure_ascii=False)

        # フィルター用マスターデータ
        facilities  = Facility.objects.all().order_by('name')
        buildings   = Building.objects.all().order_by('name')
        departments = Department.objects.all().order_by('name')
        users       = User.objects.filter(is_active=True).order_by('name')

        ctx.update({
            'rooms_list':       list(rooms),
            'view':             view,
            'target_date':      target.isoformat(),
            'rooms_json':       rooms_json,
            'facilities_list':  list(facilities),
            'buildings_list':   list(buildings),
            'departments_list': list(departments),
            'users_list':       list(users),
            'fc_initial_view': {
                'day': 'timeGridDay',
                'week': 'timeGridWeek',
                'month': 'dayGridMonth',
            }.get(view, 'timeGridWeek'),
        })
        return ctx


# 一覧（タイムライン）ビュー
class ReservationTimelineView(LoginRequiredMixin, TemplateView):
    template_name = 'reservations/timeline.html'

    HOUR_START = 8
    HOUR_END   = 22   # 8:00〜22:00 を表示（range で 8〜21 列生成、右端が 22:00）
    HOUR_WIDTH = 80   # px/時間

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        date_str = self.request.GET.get('date')
        try:
            target = datetime.strptime(date_str, '%Y-%m-%d').date()
        except (TypeError, ValueError):
            target = date.today()

        tz = timezone.get_current_timezone()
        day_start = timezone.make_aware(datetime.combine(target, dt_time(0, 0)), tz)
        day_end   = day_start + timedelta(days=1)

        rooms = Room.objects.filter(is_active=True).order_by('name')

        # その日の予約を全取得
        reservations = (
            Reservation.objects
            .filter(is_cancelled=False, start_at__lt=day_end, end_at__gt=day_start)
            .select_related('room', 'user')
            .order_by('start_at')
        )

        # 会議室ごとに振り分け
        room_res_map = defaultdict(list)
        for res in reservations:
            room_res_map[res.room_id].append(res)

        hour_start = self.HOUR_START
        hour_end   = self.HOUR_END
        hour_width = self.HOUR_WIDTH
        total_minutes = (hour_end - hour_start) * 60

        room_data = []
        for room in rooms:
            res_list = []
            for res in room_res_map.get(room.pk, []):
                local_start = localtime(res.start_at)
                local_end   = localtime(res.end_at)
                can_edit    = (res.user_id == self.request.user.pk or
                               self.request.user.is_staff)

                # 終日予約は時刻計算をスキップして固定値で登録
                if res.is_all_day:
                    res_list.append({
                        'id':          res.pk,
                        'title':       res.title,
                        'reserved_by': res.reserved_by,
                        'start_min':   0,
                        'dur_min':     total_minutes,
                        'left_px':     0,
                        'width_px':    0,
                        'color':       res.color or '#3182CE',
                        'start_str':   '終日',
                        'end_str':     '',
                        'is_all_day':  True,
                        'can_edit':    can_edit,
                    })
                    continue

                start_min = (local_start.hour - hour_start) * 60 + local_start.minute
                end_min   = (local_end.hour   - hour_start) * 60 + local_end.minute

                # タイムライン範囲にクリップ
                start_min = max(start_min, 0)
                end_min   = min(end_min,   total_minutes)
                if end_min <= start_min:
                    continue

                left_px  = int(start_min * hour_width / 60)
                width_px = max(int((end_min - start_min) * hour_width / 60), 4)

                dur_min  = end_min - start_min
                res_list.append({
                    'id':          res.pk,
                    'title':       res.title,
                    'reserved_by': res.reserved_by,
                    'start_min':   start_min,
                    'dur_min':     dur_min,
                    'left_px':     left_px,
                    'width_px':    width_px,
                    'color':       res.color or '#3182CE',
                    'start_str':   local_start.strftime('%H:%M'),
                    'end_str':     local_end.strftime('%H:%M'),
                    'is_all_day':  False,
                    'can_edit':    can_edit,
                })
            room_data.append({'room': room, 'reservations': res_list})

        # ミニカレンダー用データ
        year  = target.year
        month = target.month
        cal   = cal_module.Calendar(firstweekday=0)  # 月曜始まり
        weeks = cal.monthdatescalendar(year, month)

        # 前月・翌月ナビ
        if month == 1:
            prev_month_date = date(year - 1, 12, 1)
        else:
            prev_month_date = date(year, month - 1, 1)
        if month == 12:
            next_month_date = date(year + 1, 1, 1)
        else:
            next_month_date = date(year, month + 1, 1)

        hours         = list(range(hour_start, hour_end))
        total_minutes = (hour_end - hour_start) * 60
        total_width   = (hour_end - hour_start) * hour_width

        ctx.update({
            'target':          target,
            'prev_date':       target - timedelta(days=1),
            'next_date':       target + timedelta(days=1),
            'today':           date.today(),
            'room_data':       room_data,
            'hours':         hours,
            'total_minutes': total_minutes,
            'hour_width':    hour_width,
            'total_width':   total_width,
            'weeks':           weeks,
            'cal_year':        year,
            'cal_month':       month,
            'prev_month_date': prev_month_date,
            'next_month_date': next_month_date,
            'weekday_names':   ['月', '火', '水', '木', '金', '土', '日'],
        })
        return ctx


# F-06
class MyReservationListView(LoginRequiredMixin, ListView):
    model = Reservation
    template_name = "reservations/my_reservations.html"
    context_object_name = "reservations"

    def get_queryset(self):
        tab = self.request.GET.get("tab", "upcoming")
        now = timezone.now()

        if tab == "past":
            return (
                Reservation.objects.filter(user=self.request.user, start_at__lt=now)
                .select_related("room")
                .order_by("-start_at")
            )
        else:
            return (
                Reservation.objects.filter(
                    user=self.request.user, start_at__gte=now, is_cancelled=False
                )
                .select_related("room")
                .order_by("start_at")
            )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tab = self.request.GET.get("tab", "upcoming")
        context["active_tab"] = tab

        now = timezone.now()
        context["upcoming_count"] = Reservation.objects.filter(
            user=self.request.user, start_at__gte=now, is_cancelled=False
        ).count()
        context["past_count"] = Reservation.objects.filter(
            user=self.request.user, start_at__lt=now
        ).count()

        # Google カレンダー連携状態
        try:
            token = self.request.user.google_token
            context["google_connected"]    = True
            context["google_sync_enabled"] = token.sync_enabled
        except UserGoogleToken.DoesNotExist:
            context["google_connected"]    = False
            context["google_sync_enabled"] = False

        return context


# F-09
class ReservationCreateView(CreateView):
    model = Reservation
    form_class = ReservationForm
    template_name = "reservations/create.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        room_id = self.request.GET.get("room")
        selected_room = None
        if room_id:
            try:
                selected_room = Room.objects.get(id=room_id)
            except Room.DoesNotExist:
                selected_room = None
        context["selected_room"] = selected_room
        return context

    def get_initial(self):
        initial = super().get_initial()

        room_id = self.request.GET.get("room")
        if room_id:
            initial["room"] = room_id

        date_str     = self.request.GET.get("date")
        time_str     = self.request.GET.get("time")
        end_time_str = self.request.GET.get("end_time")
        all_day      = self.request.GET.get("all_day")

        if all_day == "1":
            initial["is_all_day"] = True

        # 日付だけ渡された場合（終日予約）でも reserve_date を初期セット
        if date_str:
            try:
                initial["reserve_date"] = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        if date_str and time_str:
            try:
                start_at = datetime.strptime(
                    date_str + " " + time_str, "%Y-%m-%d %H:%M"
                )
                # end_time が渡されていればそれを使う。なければ開始+30分
                if end_time_str:
                    end_at = datetime.strptime(
                        date_str + " " + end_time_str, "%Y-%m-%d %H:%M"
                    )
                    # 日をまたぐ場合（例：23:30〜00:00）は翌日に補正
                    if end_at <= start_at:
                        end_at += timedelta(days=1)
                else:
                    end_at = start_at + timedelta(minutes=30)
                initial["start_at"] = start_at
                initial["end_at"] = end_at
            except ValueError:
                pass

        return initial

    def form_valid(self, form):
        reservation = form.save(commit=False)
        reservation.user = self.request.user
        reservation.reserved_by = self.request.user.name
        recurrence_rule = form.cleaned_data.get('recurrence_rule', '')
        reservation.recurrence_rule = recurrence_rule

        # ── Rakumo事前競合チェック ──────────────────────────────
        if not reservation.is_all_day:
            try:
                rakumo_svc = RakumoSyncService()
                room_obj = Room.objects.get(pk=reservation.room_id)
                if not rakumo_svc.no_op and room_obj.google_calendar_id:
                    conflicts = rakumo_svc.check_conflict_with_rakumo(
                        room_obj.google_calendar_id,
                        reservation.start_at,
                        reservation.end_at,
                    )
                    if conflicts:
                        titles = '、'.join(ev['title'] for ev in conflicts[:3])
                        form.add_error(
                            None,
                            f'Rakumo（本社）に同じ時間帯の予約があります：{titles}。'
                            '時間帯を変更してください。'
                        )
                        return self.form_invalid(form)
            except Exception as e:
                logger.warning(f'Rakumo conflict check on create failed: {e}')

        with transaction.atomic():
            # 会議室行をロックして同時リクエストの割り込みを防ぐ
            Room.objects.select_for_update().get(pk=reservation.room_id)
            error_msg = _conflict_exists(
                reservation.room_id, reservation.start_at, reservation.end_at,
                is_all_day=reservation.is_all_day,
            )
            if error_msg:
                form.add_error(None, error_msg)
                return self.form_invalid(form)
            reservation.save()
            if recurrence_rule:
                _generate_recurrence_instances(reservation)

        self.object = reservation
        color_str = reservation.color or '#3182CE'
        _log_operation(
            self.request,
            OperationLog.ACTION_CREATE,
            reservation,
            detail=(
                f"{reservation.room.name} / "
                f"{reservation.title} / "
                f"{localtime(reservation.start_at).strftime('%Y-%m-%d %H:%M')}"
                f"〜{localtime(reservation.end_at).strftime('%H:%M')} / "
                f"色: {color_str}"
            ),
        )
        GoogleSyncService(self.request.user).create_event(reservation)
        # Rakumo自動連携（このシステム → Rakumo）
        try:
            RakumoSyncService().create_event(reservation)
        except Exception as e:
            logger.warning(f'Rakumo sync on create failed: {e}')
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("reservation_detail", kwargs={"pk": self.object.pk})


# F-10
class ReservationDetailView(LoginRequiredMixin, DetailView):
    model = Reservation
    template_name = "reservations/detail.html"
    context_object_name = "reservation"


class ReservationUpdateView(LoginRequiredMixin, UpdateView):
    model = Reservation
    form_class = ReservationForm
    template_name = "reservations/edit.html"
    context_object_name = "reservation"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            # 未ログイン時は LoginRequiredMixin のリダイレクトに委譲
            return super().dispatch(request, *args, **kwargs)
        reservation = self.get_object()
        if reservation.user != request.user and not request.user.is_staff:
            return HttpResponseForbidden("この予約を編集する権限がありません")
        return super().dispatch(request, *args, **kwargs)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["room"].disabled = True
        return form

    def form_valid(self, form):
        reservation = form.save(commit=False)

        # 変更前の値を保存（detail 生成用）
        old = Reservation.objects.get(pk=reservation.pk)

        # ── Rakumo事前競合チェック ──────────────────────────────
        if not reservation.is_all_day:
            try:
                rakumo_svc = RakumoSyncService()
                room_obj = Room.objects.get(pk=reservation.room_id)
                if not rakumo_svc.no_op and room_obj.google_calendar_id:
                    conflicts = rakumo_svc.check_conflict_with_rakumo(
                        room_obj.google_calendar_id,
                        reservation.start_at,
                        reservation.end_at,
                        exclude_rakumo_event_id=reservation.rakumo_event_id or '',
                    )
                    if conflicts:
                        titles = '、'.join(ev['title'] for ev in conflicts[:3])
                        form.add_error(
                            None,
                            f'Rakumo（本社）に同じ時間帯の予約があります：{titles}。'
                            '時間帯を変更してください。'
                        )
                        return self.form_invalid(form)
            except Exception as e:
                logger.warning(f'Rakumo conflict check on update failed: {e}')

        with transaction.atomic():
            Room.objects.select_for_update().get(pk=reservation.room_id)
            error_msg = _conflict_exists(
                reservation.room_id, reservation.start_at, reservation.end_at,
                exclude_pk=reservation.pk,
                is_all_day=reservation.is_all_day,
            )
            if error_msg:
                form.add_error(None, error_msg)
                return self.form_invalid(form)
            reservation.save()
            self.object = reservation

        # 変更内容を差分形式で記録
        diff_parts = []
        if old.title != reservation.title:
            diff_parts.append(f"件名: 「{old.title}」→「{reservation.title}」")
        old_start_local = localtime(old.start_at)
        new_start_local = localtime(reservation.start_at)
        old_end_local   = localtime(old.end_at)
        new_end_local   = localtime(reservation.end_at)
        if old_start_local != new_start_local or old_end_local != new_end_local:
            diff_parts.append(
                f"日時: {old_start_local.strftime('%Y-%m-%d %H:%M')}〜{old_end_local.strftime('%H:%M')}"
                f"→{new_start_local.strftime('%Y-%m-%d %H:%M')}〜{new_end_local.strftime('%H:%M')}"
            )
        if old.participants != reservation.participants:
            diff_parts.append("参加者を変更")
        if old.notes != reservation.notes:
            diff_parts.append("備考を変更")
        old_color = old.color or '#3182CE'
        new_color = reservation.color or '#3182CE'
        if old_color.lower() != new_color.lower():
            diff_parts.append(f"色: 「{old_color}」→「{new_color}」")
        detail = " / ".join(diff_parts) if diff_parts else "変更なし"
        _log_operation(self.request, OperationLog.ACTION_UPDATE, self.object, detail=detail)
        try:
            GoogleSyncService(self.request.user).update_event(self.object)
        except Exception as e:
            logger.warning(f'Google sync on update failed: {e}')
        # Rakumo自動連携（このシステム → Rakumo）
        try:
            RakumoSyncService().update_event(self.object)
        except Exception as e:
            logger.warning(f'Rakumo sync on update failed: {e}')
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("reservation_detail", kwargs={"pk": self.object.pk})


@require_POST
@login_required
def reservation_cancel(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk)

    if reservation.user != request.user and not request.user.is_staff:
        return HttpResponseForbidden("この予約をキャンセルする権限がありません")

    # Rakumo発信予約は管理者でもキャンセル不可
    if reservation.is_rakumo_source:
        return HttpResponseForbidden(
            "この予約はRakumo（本社）で作成された予約のため、このシステムからはキャンセルできません。"
            "Rakumo側でキャンセルしてください。"
        )

    reservation.is_cancelled = True
    reservation.save()

    if request.user == reservation.user:
        cancel_detail = "本人によるキャンセル"
    else:
        cancel_detail = f"管理者（{request.user.name}）による代理キャンセル"
    _log_operation(request, OperationLog.ACTION_CANCEL, reservation, detail=cancel_detail)

    # Google カレンダーのイベントも削除
    try:
        GoogleSyncService(request.user).delete_event(reservation)
    except Exception as e:
        logger.warning(f'Google sync on cancel failed: {e}')
    # Rakumo自動連携（このシステム → Rakumo）
    try:
        RakumoSyncService().delete_event(reservation)
    except Exception as e:
        logger.warning(f'Rakumo sync on cancel failed: {e}')
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or 'calendar'
    return redirect(next_url)


class CalendarEventsAPI(LoginRequiredMixin, View):
    def get(self, request):
        start_str = request.GET.get('start')
        end_str   = request.GET.get('end')
        room_ids_str = request.GET.get('room_ids')  # None = パラメータ未送信、'' = 全チェックOFF

        try:
            start = datetime.fromisoformat(start_str)
            end   = datetime.fromisoformat(end_str)
        except (TypeError, ValueError):
            return JsonResponse({'error': 'invalid params'}, status=400)

        qs = Reservation.objects.filter(
            start_at__lt=end, end_at__gt=start,
            is_cancelled=False
        ).select_related('room', 'user')

        # ── room_ids フィルター（既存） ─────────────────────────
        if room_ids_str is not None:
            if room_ids_str == '':
                return JsonResponse([], safe=False)
            ids = [int(x) for x in room_ids_str.split(',') if x.strip().isdigit()]
            qs = qs.filter(room_id__in=ids)

        # ── 汎用フィルター解析ヘルパー ────────────────────────────
        def parse_ids(param_name):
            """
            パラメータ未送信 → None（フィルターなし）
            '' → []（0件表示）
            '1,2,3' → [1, 2, 3]
            """
            val = request.GET.get(param_name)
            if val is None:
                return None
            if val == '':
                return []
            return [int(x) for x in val.split(',') if x.strip().isdigit()]

        # ── 建物フィルター ────────────────────────────────────────
        building_ids = parse_ids('building_ids')
        if building_ids is not None:
            if not building_ids:
                return JsonResponse([], safe=False)
            qs = qs.filter(room__building_id__in=building_ids)

        # ── 設備フィルター（指定設備を持つ会議室の予約のみ） ─────
        facility_ids = parse_ids('facility_ids')
        if facility_ids is not None:
            if not facility_ids:
                return JsonResponse([], safe=False)
            room_ids_with_facility = list(
                RoomFacility.objects.filter(facility_id__in=facility_ids)
                .values_list('room_id', flat=True).distinct()
            )
            qs = qs.filter(room_id__in=room_ids_with_facility)

        # ── 所属フィルター（所属に紐付く会議室の予約のみ） ────────
        department_ids = parse_ids('department_ids')
        if department_ids is not None:
            if not department_ids:
                return JsonResponse([], safe=False)
            room_ids_in_dept = list(
                DepartmentRoom.objects.filter(department_id__in=department_ids)
                .values_list('room_id', flat=True).distinct()
            )
            qs = qs.filter(room_id__in=room_ids_in_dept)

        # ── ユーザーフィルター ────────────────────────────────────
        user_ids = parse_ids('user_ids')
        if user_ids is not None:
            if not user_ids:
                return JsonResponse([], safe=False)
            qs = qs.filter(user_id__in=user_ids)

        events = []
        for res in qs:
            color = res.color or '#3182CE'
            events.append({
                'id': res.id,
                'title': res.title,
                'start': localtime(res.start_at).isoformat(),
                'end':   localtime(res.end_at).isoformat(),
                'room_id': res.room_id,
                'room_name': res.room.name,
                'color': color,
                'reserved_by': res.reserved_by,
                'is_owner': res.user == request.user,
                'can_edit': res.user == request.user or request.user.is_staff,
                'editable': res.user == request.user or request.user.is_staff,
                'allDay': res.is_all_day,
                'is_rakumo': False,
            })

        # ── Rakumoイベントをリアルタイム取得して追加（グレー表示）──
        try:
            rakumo_svc = RakumoSyncService()
            if not rakumo_svc.no_op:
                # フィルター対象の会議室IDセットを特定
                if room_ids_str is not None and room_ids_str != '':
                    filtered_room_ids = set(
                        int(x) for x in room_ids_str.split(',') if x.strip().isdigit()
                    )
                else:
                    filtered_room_ids = None  # フィルターなし = 全室対象

                # google_calendar_id が設定されている会議室からRakumoイベントを取得
                rooms_with_cal = Room.objects.filter(
                    is_active=True, google_calendar_id__gt=''
                )
                if filtered_room_ids is not None:
                    rooms_with_cal = rooms_with_cal.filter(id__in=filtered_room_ids)

                # start/end を aware datetime に変換
                if start.tzinfo is None:
                    start_aware = start.replace(tzinfo=dt_tz.utc)
                else:
                    start_aware = start
                if end.tzinfo is None:
                    end_aware = end.replace(tzinfo=dt_tz.utc)
                else:
                    end_aware = end

                # このシステムで把握済みのRakumoイベントIDセット（グレー二重表示防止）
                # ・is_rakumo_source=True  … Rakumoから取り込んだ予約
                # ・rakumo_event_id__gt='' … このシステムからRakumoへ書き込んだ予約
                # どちらもRakumo上に存在するためグレー表示をスキップする
                existing_rakumo_ids = set(
                    Reservation.objects.filter(
                        is_cancelled=False,
                        rakumo_event_id__gt='',
                        start_at__lt=end_aware,
                        end_at__gt=start_aware,
                    ).values_list('rakumo_event_id', flat=True)
                )

                for room in rooms_with_cal:
                    rakumo_events = rakumo_svc.get_events_for_display(
                        room.google_calendar_id, start_aware, end_aware
                    )
                    for ev in rakumo_events:
                        if ev['id'] in existing_rakumo_ids:
                            continue  # 既にDBに取り込み済みのものはスキップ
                        events.append({
                            'id': f'rakumo_{ev["id"]}',
                            'title': f'[Rakumo] {ev["title"]}',
                            'start': localtime(ev['start']).isoformat(),
                            'end':   localtime(ev['end']).isoformat(),
                            'room_id': room.id,
                            'room_name': room.name,
                            'color': '#718096',        # グレー
                            'textColor': '#FFFFFF',
                            'reserved_by': ev.get('organizer', ''),
                            'is_owner': False,
                            'can_edit': False,
                            'editable': False,
                            'allDay': ev['is_all_day'],
                            'is_rakumo': True,
                        })
        except Exception as e:
            logger.warning(f'CalendarEventsAPI: Rakumoイベント取得失敗: {e}')

        return JsonResponse(events, safe=False)
    

class ReservationMoveView(LoginRequiredMixin, View):
    def patch(self, request, pk):
        reservation = get_object_or_404(Reservation, pk=pk, is_cancelled=False)

        # 権限チェック（自分の予約、または管理者は全予約を移動可）
        if reservation.user != request.user and not request.user.is_staff:
            return JsonResponse({'error': '操作権限がありません'}, status=403)

        # 移動前の値を保存（detail 生成用）
        old_room_name = reservation.room.name
        old_start_at  = reservation.start_at
        old_end_at    = reservation.end_at

        data      = json.loads(request.body)
        room_id   = data.get('room_id', reservation.room_id)
        is_all_day = data.get('is_all_day', False)

        tz = timezone.get_current_timezone()

        if is_all_day:
            # 終日ドロップ：JS から 'YYYY-MM-DD' の date フィールドを受け取る
            date_str   = data.get('date', '')
            local_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            start_at   = timezone.make_aware(
                datetime.combine(local_date, dt_time(0, 0)), tz
            )
            end_at = start_at + timedelta(minutes=30)
        else:
            # JavaScript の toISOString() は '2026-05-26T01:00:00.000Z' 形式を返す。
            # Python 3.10 以前は末尾の 'Z' を fromisoformat() が解釈できないため
            # '+00:00' に置換して確実にパースする（Python 3.7+ 互換）。
            start_at   = datetime.fromisoformat(data['start_at'].replace('Z', '+00:00'))
            end_at_str = data.get('end_at')
            end_at     = (
                datetime.fromisoformat(end_at_str.replace('Z', '+00:00'))
                if end_at_str
                else start_at + timedelta(minutes=30)  # フォールバック：30分後
            )

        with transaction.atomic():
            # 会議室行をロックして同時リクエストの割り込みを防ぐ
            Room.objects.select_for_update().get(pk=room_id)
            error_msg = _conflict_exists(room_id, start_at, end_at, exclude_pk=pk, is_all_day=is_all_day)
            if error_msg:
                return JsonResponse({'error': error_msg}, status=400)

            reservation.start_at   = start_at
            reservation.end_at     = end_at
            reservation.room_id    = room_id
            reservation.is_all_day = is_all_day
            reservation.save(update_fields=['start_at', 'end_at', 'room_id', 'is_all_day', 'updated_at'])

        # 移動内容を差分形式で記録
        move_parts = []
        if old_room_name != reservation.room.name:
            move_parts.append(f"会議室: 「{old_room_name}」→「{reservation.room.name}」")
        old_s = localtime(old_start_at)
        old_e = localtime(old_end_at)
        new_s = localtime(reservation.start_at)
        new_e = localtime(reservation.end_at)
        if old_s != new_s or old_e != new_e:
            if is_all_day:
                move_parts.append(
                    f"日時: {old_s.strftime('%Y-%m-%d %H:%M')}〜{old_e.strftime('%H:%M')}"
                    f"→{new_s.strftime('%Y-%m-%d')}（終日）"
                )
            else:
                move_parts.append(
                    f"日時: {old_s.strftime('%Y-%m-%d %H:%M')}〜{old_e.strftime('%H:%M')}"
                    f"→{new_s.strftime('%Y-%m-%d %H:%M')}〜{new_e.strftime('%H:%M')}"
                )
        move_detail = " / ".join(move_parts) if move_parts else "変更なし"
        _log_operation(request, OperationLog.ACTION_MOVE, reservation, detail=move_detail)

        # Google カレンダー同期
        try:
            GoogleSyncService(request.user).update_event(reservation)
        except Exception as e:
            logger.warning(f'Google sync failed: {e}')
        # Rakumo自動連携（このシステム → Rakumo）
        try:
            RakumoSyncService().update_event(reservation)
        except Exception as e:
            logger.warning(f'Rakumo sync on move failed: {e}')

        color = reservation.color or '#3182CE'
        return JsonResponse({'id': reservation.id, 'color': color}, status=200)
    

# ─────────────────────────────────────────────────────────────
# Google OAuth 2.0 ビュー
# ─────────────────────────────────────────────────────────────

@login_required
def google_oauth_start(request):
    """Google OAuth 認証画面へリダイレクト"""
    if not GOOGLE_OAUTH_AVAILABLE:
        return HttpResponse('google-auth-oauthlib が未インストールです。pip install google-auth-oauthlib を実行してください。', status=501)

    import secrets, hashlib, base64
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode('ascii')).digest()
    ).rstrip(b'=').decode('ascii')

    flow = Flow.from_client_config(
        {
            'web': {
                'client_id': settings.GOOGLE_CLIENT_ID,
                'client_secret': settings.GOOGLE_CLIENT_SECRET,
                'redirect_uris': [settings.GOOGLE_REDIRECT_URI],
                'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                'token_uri': 'https://oauth2.googleapis.com/token',
            }
        },
        scopes=settings.GOOGLE_CALENDAR_SCOPES,
    )
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',
        code_challenge=code_challenge,
        code_challenge_method='S256',
    )
    request.session['google_oauth_state'] = state
    request.session['google_code_verifier'] = code_verifier
    return redirect(auth_url)


@login_required
def google_oauth_callback(request):
    """Google からのコールバック：トークンを取得して保存"""
    if not GOOGLE_OAUTH_AVAILABLE:
        return HttpResponse('google-auth-oauthlib が未インストールです。', status=501)
    state = request.GET.get('state')
    if state != request.session.get('google_oauth_state'):
        return HttpResponseBadRequest('Invalid state parameter')

    flow = Flow.from_client_config(
        {
            'web': {
                'client_id': settings.GOOGLE_CLIENT_ID,
                'client_secret': settings.GOOGLE_CLIENT_SECRET,
                'redirect_uris': [settings.GOOGLE_REDIRECT_URI],
                'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                'token_uri': 'https://oauth2.googleapis.com/token',
            }
        },
        scopes=settings.GOOGLE_CALENDAR_SCOPES,
        state=state,
    )
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
    code_verifier = request.session.pop('google_code_verifier', '')
    flow.fetch_token(code=request.GET.get('code'), code_verifier=code_verifier)
    creds = flow.credentials

    # UserGoogleToken に保存（or 更新）
    expiry = None
    if creds.expiry:
        expiry = creds.expiry.replace(tzinfo=dt_tz.utc)
    UserGoogleToken.objects.update_or_create(
        user=request.user,
        defaults={
            'access_token':  creds.token,
            'refresh_token': creds.refresh_token or '',
            'token_expiry':  expiry,
            'sync_enabled':  True,
        }
    )
    request.session['toast'] = 'Google カレンダーと連携しました'
    return redirect('calendar')


class google_oauth_disconnect(LoginRequiredMixin, View):
    def post(self, request):
        """連携解除：トークンを revoke して削除"""
        import requests as req_lib
        try:
            token_obj = request.user.google_token
            req_lib.post('https://oauth2.googleapis.com/revoke',
                params={'token': token_obj.access_token}, timeout=5)
            token_obj.delete()
        except UserGoogleToken.DoesNotExist:
            pass
        return JsonResponse({'status': 'ok'})


class google_sync_toggle(LoginRequiredMixin, View):
    def patch(self, request):
        """同期 ON/OFF 切り替え"""
        try:
            token_obj = request.user.google_token
            token_obj.sync_enabled = not token_obj.sync_enabled
            token_obj.save(update_fields=['sync_enabled'])
            return JsonResponse({'sync_enabled': token_obj.sync_enabled})
        except UserGoogleToken.DoesNotExist:
            return JsonResponse({'error': 'Not connected'}, status=404)