import csv
import io
import logging

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import HttpResponseForbidden
from datetime import datetime, time

from reservations.models import Room, Reservation, Building, Facility, OperationLog
from reservations.forms import ReservationFilterForm
from accounts.models import Department, User
from .forms import RoomForm, UserCreateForm, UserUpdateForm, CSVUploadForm, FacilityForm, BuildingForm, DepartmentForm, UserPasswordResetForm
from collections import Counter

logger = logging.getLogger(__name__)


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """is_staff=True のユーザーのみアクセスを許可する Mixin"""

    def test_func(self):
        return self.request.user.is_staff


def _annotate_rooms(rooms):
    """会議室リストに予約数・設備ID・所属IDを付与する"""
    today = timezone.now().date()
    for room in rooms:
        room.future_reservation_count = Reservation.objects.filter(
            room=room,
            start_at__date__gte=today,
        ).count()
        room.facility_ids = ",".join(
            str(pk) for pk in room.facilities.values_list("id", flat=True)
        )
        room.department_ids = ",".join(
            str(pk) for pk in room.departments.values_list("id", flat=True)
        )


def _list_context():
    """一覧テンプレート用の共通コンテキストを生成するヘルパー（form_invalid 時に使用）"""
    rooms = (
        Room.objects.select_related("building")
        .prefetch_related("facilities", "departments")
        .order_by("name")
    )
    _annotate_rooms(rooms)
    return {
        "rooms": rooms,
        "buildings": Building.objects.all().order_by("name"),
        "facilities": Facility.objects.all().order_by("name"),
        "departments": Department.objects.all().order_by("name"),
    }


# F-18: 会議室一覧
class RoomAdminListView(StaffRequiredMixin, ListView):
    model = Room
    template_name = "admin_panel/room_admin_list.html"
    context_object_name = "rooms"

    def get_queryset(self):
        return (
            Room.objects.select_related("building")
            .prefetch_related("facilities", "departments")
            .order_by("name")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        _annotate_rooms(context["rooms"])
        context.update(
            {
                "form": RoomForm(),
                "buildings": Building.objects.all().order_by("name"),
                "facilities": Facility.objects.all().order_by("name"),
                "departments": Department.objects.all().order_by("name"),
            }
        )
        return context


# F-18: 会議室新規登録
class RoomCreateView(StaffRequiredMixin, CreateView):
    model = Room
    form_class = RoomForm
    template_name = "admin_panel/room_admin_list.html"
    success_url = reverse_lazy("room_admin_list")

    def form_invalid(self, form):
        ctx = _list_context()
        ctx.update(
            {
                "form": form,
                "modal_open": True,
                "modal_mode": "create",
                "form_action_url": reverse("room_create"),
                "selected_facility_ids": [
                    int(x) for x in form.data.getlist("facilities") if x.isdigit()
                ],
                "selected_department_ids": [
                    int(x) for x in form.data.getlist("departments") if x.isdigit()
                ],
            }
        )
        return render(self.request, "admin_panel/room_admin_list.html", ctx)


# F-18: 会議室編集
class RoomUpdateView(StaffRequiredMixin, UpdateView):
    model = Room
    form_class = RoomForm
    template_name = "admin_panel/room_admin_list.html"
    success_url = reverse_lazy("room_admin_list")

    def form_invalid(self, form):
        ctx = _list_context()
        ctx.update(
            {
                "form": form,
                "modal_open": True,
                "modal_mode": "edit",
                "edit_room_id": self.object.pk,
                "form_action_url": reverse("room_edit", kwargs={"pk": self.object.pk}),
                "selected_facility_ids": [
                    int(x) for x in form.data.getlist("facilities") if x.isdigit()
                ],
                "selected_department_ids": [
                    int(x) for x in form.data.getlist("departments") if x.isdigit()
                ],
            }
        )
        return render(self.request, "admin_panel/room_admin_list.html", ctx)


# F-19: 会議室削除（カスケード削除）
class RoomDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        room = get_object_or_404(Room, pk=pk)
        room.delete()
        return redirect("room_admin_list")


# F-20: 利用停止 / 再開（is_active トグル）
class RoomToggleActiveView(StaffRequiredMixin, View):
    def post(self, request, pk):
        room = get_object_or_404(Room, pk=pk)
        room.is_active = not room.is_active
        room.save(update_fields=["is_active"])
        return redirect("room_admin_list")


# ─────────────────────────────────────────────
# ユーザー管理（F-14〜F-17）
# ─────────────────────────────────────────────


def _user_list_context(request, **extra):
    """ユーザー一覧テンプレート用の共通コンテキストを生成するヘルパー"""
    qs = User.objects.select_related("department").order_by("login_id")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(name__icontains=q)
    ctx = {
        "users": qs,
        "q": q,
        "total_count": User.objects.count(),
        "modal_form": UserCreateForm(),
        "modal_open": False,
        "modal_mode": "create",
        "form_action_url": None,
        "edit_user_id": None,
        "edit_user_login_id": "",
        "is_paginated": False,
    }
    ctx.update(extra)
    return ctx


# F-14: ユーザー一覧
class UserListView(StaffRequiredMixin, ListView):
    model = User
    template_name = "admin_panel/user_list.html"
    context_object_name = "users"
    paginate_by = 20

    def get_queryset(self):
        qs = User.objects.select_related("department").order_by("login_id")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)
            logger.info("UserListView: search q=%s matched %s", q, qs.count())
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.request.GET.get("q", "")
        context["total_count"] = User.objects.count()
        context["modal_form"] = UserCreateForm()
        context["modal_open"] = False
        context["modal_mode"] = "create"
        context["form_action_url"] = None
        context["edit_user_id"] = None
        context["edit_user_login_id"] = ""
        return context


# F-15: ユーザー追加
class UserCreateView(StaffRequiredMixin, CreateView):
    model = User
    form_class = UserCreateForm
    success_url = reverse_lazy("user_admin_list")

    def get(self, request, *args, **kwargs):
        return redirect("user_admin_list")

    def form_valid(self, form):
        user = form.save(commit=False)
        user.set_password("Bold1234")
        user.is_active = True
        user.save()
        logger.info(
            "User created: login_id=%s by admin=%s",
            user.login_id,
            self.request.user.login_id,
        )
        messages.success(
            self.request, "ユーザー「{}」を追加しました。".format(user.name)
        )
        return redirect(self.success_url)

    def form_invalid(self, form):
        logger.warning("UserCreateForm invalid: errors=%s", form.errors)
        ctx = _user_list_context(
            self.request,
            modal_form=form,
            modal_open=True,
            modal_mode="create",
            form_action_url=reverse("user_create"),
        )
        return render(self.request, "admin_panel/user_list.html", ctx)


# F-15: ユーザー編集
class UserUpdateView(StaffRequiredMixin, UpdateView):
    model = User
    form_class = UserUpdateForm
    success_url = reverse_lazy("user_admin_list")

    def get_object(self, queryset=None):
        return get_object_or_404(User, pk=self.kwargs["pk"])

    def get(self, request, *args, **kwargs):
        return redirect("user_admin_list")

    def form_valid(self, form):
        user = form.save()
        logger.info(
            "User updated: login_id=%s by admin=%s",
            user.login_id,
            self.request.user.login_id,
        )
        messages.success(
            self.request, "ユーザー「{}」の情報を更新しました。".format(user.name)
        )
        return redirect(self.success_url)

    def form_invalid(self, form):
        logger.warning("UserUpdateForm invalid: errors=%s", form.errors)
        obj = self.get_object()
        ctx = _user_list_context(
            self.request,
            modal_form=form,
            modal_open=True,
            modal_mode="edit",
            edit_user_id=obj.pk,
            edit_user_login_id=obj.login_id,
            form_action_url=reverse("user_edit", kwargs={"pk": obj.pk}),
        )
        return render(self.request, "admin_panel/user_list.html", ctx)


# F-16: ユーザー有効/無効トグル
class UserToggleActiveView(StaffRequiredMixin, View):
    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)

        if request.user.pk == target.pk:
            messages.error(request, "自分自身を無効化することはできません。")
            logger.warning("Self-deactivation attempt: admin=%s", request.user.login_id)
            return redirect("user_admin_list")

        target.is_active = not target.is_active
        target.save(update_fields=["is_active", "updated_at"])

        action = "有効化" if target.is_active else "無効化"
        logger.info(
            "User %s: login_id=%s by admin=%s",
            action,
            target.login_id,
            request.user.login_id,
        )
        messages.success(
            request, "ユーザー「{}」を{}しました。".format(target.name, action)
        )
        return redirect("user_admin_list")


class UserPasswordResetView(StaffRequiredMixin, View):
    """管理者によるユーザーパスワードリセット（F-15 拡張）"""

    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        form = UserPasswordResetForm(request.POST)

        if not form.is_valid():
            # バリデーションエラーはフラッシュメッセージで通知してリダイレクト
            errors = []
            for field_errors in form.errors.values():
                errors.extend(field_errors)
            messages.error(request, '　'.join(errors))
            return redirect("user_admin_list")

        new_password = form.cleaned_data['new_password']
        target.set_password(new_password)
        target.save(update_fields=['password'])

        logger.info(
            "Password reset: target_login_id=%s by admin=%s",
            target.login_id,
            request.user.login_id,
        )
        messages.success(
            request,
            "ユーザー「{}」のパスワードをリセットしました。".format(target.name),
        )
        return redirect("user_admin_list")


# F-17: CSVインポート
SESSION_KEY_CSV_PREVIEW = "csv_preview_data"


class CSVImportView(StaffRequiredMixin, View):
    template_name = "admin_panel/csv_import.html"

    @staticmethod
    def _decode_csv(raw):
        try:
            import chardet

            detected = chardet.detect(raw)
            encoding = detected.get("encoding") or "utf-8"
        except ImportError:
            encoding = "utf-8"
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            return raw.decode("cp932", errors="replace")

    @staticmethod
    def _parse_csv(text):
        reader = csv.reader(io.StringIO(text))
        rows_raw = list(reader)
        if not rows_raw:
            return []

        data_rows = rows_raw[1:]  # skip header

        csv_login_ids = [r[0].strip() for r in data_rows if len(r) > 0 and r[0].strip()]
        existing_ids = set(
            User.objects.filter(login_id__in=csv_login_ids).values_list(
                "login_id", flat=True
            )
        )

        preview_rows = []
        for i, row in enumerate(data_rows, start=2):
            login_id = row[0].strip() if len(row) > 0 else ""
            name = row[1].strip() if len(row) > 1 else ""
            role = row[2].strip() if len(row) > 2 else ""
            dept_name = row[3].strip() if len(row) > 3 else ""

            error_msg = ""
            if not login_id or not name:
                error_msg = "必須項目が不足しています"
            elif role not in ("admin", "user"):
                error_msg = "権限の値が不正です（admin または user）"
            elif login_id in existing_ids:
                error_msg = "このユーザーIDはすでに存在します"

            preview_rows.append(
                {
                    "row_num": i,
                    "login_id": login_id,
                    "name": name,
                    "role": role,
                    "dept_name": dept_name,
                    "is_valid": error_msg == "",
                    "error": error_msg,
                }
            )

        return preview_rows

    def get(self, request, *args, **kwargs):
        request.session.pop(SESSION_KEY_CSV_PREVIEW, None)
        return render(request, self.template_name, {"form": CSVUploadForm()})

    def post(self, request, *args, **kwargs):
        form = CSVUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        csv_file = form.cleaned_data["csv_file"]
        filename = csv_file.name

        try:
            raw = csv_file.read()
            text = self._decode_csv(raw)
            preview_rows = self._parse_csv(text)
        except Exception as exc:
            logger.error(
                "CSV parse error. admin_id=%s filename=%s detail=%s",
                request.user.pk,
                filename,
                exc,
            )
            form.add_error(None, "CSVファイルの読み込みに失敗しました。")
            return render(request, self.template_name, {"form": form})

        request.session[SESSION_KEY_CSV_PREVIEW] = preview_rows

        valid_count = sum(1 for r in preview_rows if r["is_valid"])
        error_count = len(preview_rows) - valid_count

        if error_count > 0:
            logger.warning(
                "CSV import skipped rows=%s admin_id=%s", error_count, request.user.pk
            )

        return render(
            request,
            self.template_name,
            {
                "form": CSVUploadForm(),
                "preview_rows": preview_rows,
                "valid_count": valid_count,
                "error_count": error_count,
                "filename": filename,
            },
        )


class CSVImportExecuteView(StaffRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        preview_rows = request.session.get(SESSION_KEY_CSV_PREVIEW)

        if not preview_rows:
            messages.error(
                request, "セッションが切れました。再度CSVをアップロードしてください。"
            )
            return redirect("csv_import")

        valid_rows = [r for r in preview_rows if r["is_valid"]]
        skip_count = len(preview_rows) - len(valid_rows)
        users_to_create = []

        try:
            with transaction.atomic():
                for row in valid_rows:
                    dept = None
                    if row["dept_name"]:
                        dept, created = Department.objects.get_or_create(
                            name=row["dept_name"]
                        )
                        if created:
                            logger.info(
                                "Department created during CSV import. name=%s admin_id=%s",
                                row["dept_name"],
                                request.user.pk,
                            )
                    u = User(
                        login_id=row["login_id"],
                        name=row["name"],
                        role=row["role"],
                        department=dept,
                        is_active=True,
                    )
                    u.set_password("Bold1234")
                    users_to_create.append(u)

                User.objects.bulk_create(users_to_create)

        except Exception as exc:
            logger.error(
                "CSV import bulk_create failed. admin_id=%s detail=%s",
                request.user.pk,
                exc,
            )
            messages.error(
                request,
                "インポート中にエラーが発生しました。管理者に連絡してください。",
            )
            return redirect("csv_import")

        request.session.pop(SESSION_KEY_CSV_PREVIEW, None)
        logger.info(
            "CSV import success. imported=%s skipped=%s admin_id=%s",
            len(users_to_create),
            skip_count,
            request.user.pk,
        )
        messages.success(
            request, "{}件のユーザーをインポートしました。".format(len(users_to_create))
        )
        return redirect("user_admin_list")


# F-18: CSV一括削除


class CSVDeleteView(StaffRequiredMixin, View):
    template_name = "admin_panel/csv_delete.html"

    @staticmethod
    def _decode_csv(raw):
        try:
            import chardet

            detected = chardet.detect(raw)
            encoding = detected.get("encoding") or "utf-8"
        except ImportError:
            encoding = "utf-8"
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            return raw.decode("cp932", errors="replace")

    @staticmethod
    def _parse_csv(text):
        reader = csv.reader(io.StringIO(text))
        rows_raw = list(reader)
        if not rows_raw:
            return []

        data_rows = rows_raw[1:]  # skip header

        csv_login_ids = [r[0].strip() for r in data_rows if len(r) > 0 and r[0].strip()]

        # CSV内の重複チェック用
        login_id_counts = Counter(csv_login_ids)

        existing_ids = set(
            User.objects.filter(login_id__in=csv_login_ids).values_list(
                "login_id", flat=True
            )
        )

        # DBよりユーザ情報＋所属情報をまとめて取得
        users = User.objects.select_related("department").filter(
            login_id__in=csv_login_ids
        )

        # login_idをキーに検索しやすくする
        user_dict = {
            user.login_id: user
            for user in users
        }

        preview_rows = []
        for i, row in enumerate(data_rows, start=2):
            login_id = row[0].strip() if len(row) > 0 else ""

            error_msg = ""

            # CSV内で重複している場合
            if login_id and login_id_counts[login_id] > 1:
                error_msg = "CSV内のユーザIDが重複しています"

            user = user_dict.get(login_id)

            if not user:
                error_msg = "このユーザーIDは存在しません"

                name = ""
                role = ""
                dept_name = ""
            else:
                name = user.name
                role = user.role

                # Department.nameを取得
                dept_name = (
                    user.department.name
                    if user.department
                    else ""
                )

            preview_rows.append(
                {
                    "row_num": i,
                    "login_id": login_id,
                    "name": name,
                    "role": role,
                    "dept_name": dept_name,
                    "is_valid": error_msg == "",
                    "error": error_msg,
                }
            )

        return preview_rows

    def get(self, request, *args, **kwargs):
        request.session.pop(SESSION_KEY_CSV_PREVIEW, None)
        return render(request, self.template_name, {"form": CSVUploadForm()})

    def post(self, request, *args, **kwargs):
        form = CSVUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        csv_file = form.cleaned_data["csv_file"]
        filename = csv_file.name

        try:
            raw = csv_file.read()
            text = self._decode_csv(raw)
            preview_rows = self._parse_csv(text)
        except Exception as exc:
            logger.error(
                "CSV parse error. admin_id=%s filename=%s detail=%s",
                request.user.pk,
                filename,
                exc,
            )
            form.add_error(None, "CSVファイルの読み込みに失敗しました。")
            return render(request, self.template_name, {"form": form})

        request.session[SESSION_KEY_CSV_PREVIEW] = preview_rows

        valid_count = sum(1 for r in preview_rows if r["is_valid"])
        error_count = len(preview_rows) - valid_count

        if error_count > 0:
            logger.warning(
                "CSV delete skipped rows=%s admin_id=%s", error_count, request.user.pk
            )

        return render(
            request,
            self.template_name,
            {
                "form": CSVUploadForm(),
                "preview_rows": preview_rows,
                "valid_count": valid_count,
                "error_count": error_count,
                "filename": filename,
            },
        )

class CSVDeleteExecuteView(StaffRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        preview_rows = request.session.get(SESSION_KEY_CSV_PREVIEW)

        if not preview_rows:
            messages.error(
                request, "セッションが切れました。再度CSVをアップロードしてください。"
            )
            return redirect("csv_delete")

        valid_rows = [r for r in preview_rows if r["is_valid"]]
        skip_count = len(preview_rows) - len(valid_rows)
        users_to_delete = []

        try:
            with transaction.atomic():
                for row in valid_rows:
                    users_to_delete.append(row["login_id"])
                
                # 削除基準日の取得
                target_date = timezone.make_aware(
                    datetime.combine(
                        timezone.localdate(),
                        time.min,
                    )
                )

                # Userテーブルから対象ユーザーのidを取得
                ids = set(
                    User.objects.filter(login_id__in=users_to_delete).values_list(
                        "id", flat=True
                    )
                )

                # reservationsテーブルの更新
                Reservation.objects.filter(
                    user_id__in=ids,
                    start_at__gte=target_date,
                ).update(
                    is_cancelled=True
                )

                # usersテーブルの更新
                updated_count = User.objects.filter(
                    login_id__in=users_to_delete
                ).update(
                    is_active=False
                )

        except Exception as exc:
            logger.error(
                "CSV delete failed. admin_id=%s detail=%s",
                request.user.pk,
                exc,
            )
            messages.error(
                request,
                "一括削除中にエラーが発生しました。管理者に連絡してください。",
            )
            return redirect("csv_delete")

        request.session.pop(SESSION_KEY_CSV_PREVIEW, None)
        logger.info(
            "CSV delete success. deleted=%s skipped=%s admin_id=%s",
            len(users_to_delete),
            skip_count,
            request.user.pk,
        )
        messages.success(
            request, "{}件のユーザーを一括削除しました。".format(len(users_to_delete))
        )
        return redirect("user_admin_list")


# ─────────────────────────────────────────────
# 全予約管理（F-21）
# ─────────────────────────────────────────────


class AllReservationListView(StaffRequiredMixin, ListView):
    """F-21: 全予約一覧・管理"""

    model = Reservation
    template_name = "admin_panel/admin_reservation_list.html"
    context_object_name = "reservations"

    def get_queryset(self):
        qs = Reservation.objects.select_related("room", "user").order_by("-start_at")

        date_from_str = self.request.GET.get("date_from", "").strip()
        date_to_str = self.request.GET.get("date_to", "").strip()
        room_id_str = self.request.GET.get("room", "").strip()
        user_name = self.request.GET.get("user", "").strip()

        if date_from_str:
            try:
                target = date.fromisoformat(date_from_str)
                qs = qs.filter(start_at__date__gte=target)
            except ValueError:
                pass

        if date_to_str:
            try:
                target = date.fromisoformat(date_to_str)
                qs = qs.filter(start_at__date__lte=target)
            except ValueError:
                pass

        if room_id_str:
            try:
                qs = qs.filter(room_id=int(room_id_str))
            except (ValueError, TypeError):
                pass

        if user_name:
            qs = qs.filter(user__name__icontains=user_name)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        form = ReservationFilterForm(self.request.GET or None)
        rooms = Room.objects.order_by("name")

        date_from_str = self.request.GET.get("date_from", "").strip()
        date_to_str = self.request.GET.get("date_to", "").strip()

        def fmt_date_display(date_str):
            try:
                return date.fromisoformat(date_str).strftime("%Y/%m/%d")
            except (ValueError, AttributeError):
                return ""

        context.update(
            {
                "form": form,
                "rooms": rooms,
                "total_count": context["reservations"].count(),
                "date_from": date_from_str,
                "date_to": date_to_str,
                "date_from_display": fmt_date_display(date_from_str),
                "date_to_display": fmt_date_display(date_to_str),
                "now": timezone.now(),
            }
        )
        return context


# ── ページネーター共通ヘルパー ────────────────────────────────

def _facility_page_obj(request):
    q = request.GET.get('q', '')
    qs = Facility.objects.annotate(room_count=Count('room'))
    if q:
        qs = qs.filter(name__icontains=q)
    qs = qs.order_by('name')
    return Paginator(qs, 20).get_page(request.GET.get('page')), qs.count(), q


def _building_page_obj(request):
    q = request.GET.get('q', '')
    qs = Building.objects.annotate(room_count=Count('rooms'))
    if q:
        qs = qs.filter(name__icontains=q)
    qs = qs.order_by('name')
    return Paginator(qs, 20).get_page(request.GET.get('page')), qs.count(), q


def _department_page_obj(request):
    q = request.GET.get('q', '')
    qs = Department.objects.annotate(
        room_count=Count('room', distinct=True),
        user_count=Count('users', distinct=True),
    )
    if q:
        qs = qs.filter(name__icontains=q)
    qs = qs.order_by('name')
    return Paginator(qs, 20).get_page(request.GET.get('page')), qs.count(), q


# ── F-22 設備管理 ──────────────────────────────────────────
class FacilityListView(StaffRequiredMixin, View):
    template_name = 'admin_panel/facility_list.html'

    def get(self, request):
        page_obj, total, q = _facility_page_obj(request)
        return render(request, self.template_name, {
            'page_obj': page_obj, 'q': q, 'total': total,
            'toast': request.session.pop('toast', None),
        })


class FacilityCreateView(StaffRequiredMixin, View):
    def post(self, request):
        form = FacilityForm(request.POST)
        if form.is_valid():
            form.save()
            request.session['toast'] = '設備を追加しました'
            return redirect('facility_list')
        page_obj, total, _ = _facility_page_obj(request)
        return render(request, 'admin_panel/facility_list.html', {
            'page_obj': page_obj, 'total': total,
            'add_form': form, 'show_add_modal': True,
        })


class FacilityUpdateView(StaffRequiredMixin, View):
    def post(self, request, pk):
        facility = get_object_or_404(Facility, pk=pk)
        form = FacilityForm(request.POST, instance=facility)
        if form.is_valid():
            form.save()
            request.session['toast'] = '設備を更新しました'
            return redirect('facility_list')
        page_obj, total, _ = _facility_page_obj(request)
        return render(request, 'admin_panel/facility_list.html', {
            'page_obj': page_obj, 'total': total,
            'edit_form': form, 'edit_target': facility, 'show_edit_modal': True,
        })


class FacilityDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        facility = get_object_or_404(Facility, pk=pk)
        facility.delete()  # RoomFacility は CASCADE 削除
        request.session['toast'] = '設備を削除しました'
        return redirect('facility_list')


# ── F-23 建物管理 ──────────────────────────────────────────
class BuildingListView(StaffRequiredMixin, View):
    template_name = 'admin_panel/building_list.html'

    def get(self, request):
        page_obj, total, q = _building_page_obj(request)
        return render(request, self.template_name, {
            'page_obj': page_obj, 'q': q, 'total': total,
            'toast': request.session.pop('toast', None),
        })


class BuildingCreateView(StaffRequiredMixin, View):
    def post(self, request):
        form = BuildingForm(request.POST)
        if form.is_valid():
            form.save()
            request.session['toast'] = '建物を追加しました'
            return redirect('building_list')
        page_obj, total, _ = _building_page_obj(request)
        return render(request, 'admin_panel/building_list.html', {
            'page_obj': page_obj, 'total': total,
            'add_form': form, 'show_add_modal': True,
        })


class BuildingUpdateView(StaffRequiredMixin, View):
    def post(self, request, pk):
        building = get_object_or_404(Building, pk=pk)
        form = BuildingForm(request.POST, instance=building)
        if form.is_valid():
            form.save()
            request.session['toast'] = '建物を更新しました'
            return redirect('building_list')
        page_obj, total, _ = _building_page_obj(request)
        return render(request, 'admin_panel/building_list.html', {
            'page_obj': page_obj, 'total': total,
            'edit_form': form, 'edit_target': building, 'show_edit_modal': True,
        })


class BuildingDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        building = get_object_or_404(Building, pk=pk)
        building.delete()
        request.session['toast'] = '建物を削除しました'
        return redirect('building_list')


# ── F-24 所属管理 ──────────────────────────────────────────
class DepartmentListView(StaffRequiredMixin, View):
    template_name = 'admin_panel/department_list.html'

    def get(self, request):
        page_obj, total, q = _department_page_obj(request)
        return render(request, self.template_name, {
            'page_obj': page_obj, 'q': q, 'total': total,
            'toast': request.session.pop('toast', None),
        })


class DepartmentCreateView(StaffRequiredMixin, View):
    def post(self, request):
        form = DepartmentForm(request.POST)
        if form.is_valid():
            form.save()
            request.session['toast'] = '所属を追加しました'
            return redirect('department_list')
        page_obj, total, _ = _department_page_obj(request)
        return render(request, 'admin_panel/department_list.html', {
            'page_obj': page_obj, 'total': total,
            'add_form': form, 'show_add_modal': True,
        })


class DepartmentUpdateView(StaffRequiredMixin, View):
    def post(self, request, pk):
        department = get_object_or_404(Department, pk=pk)
        form = DepartmentForm(request.POST, instance=department)
        if form.is_valid():
            form.save()
            request.session['toast'] = '所属を更新しました'
            return redirect('department_list')
        page_obj, total, _ = _department_page_obj(request)
        return render(request, 'admin_panel/department_list.html', {
            'page_obj': page_obj, 'total': total,
            'edit_form': form, 'edit_target': department, 'show_edit_modal': True,
        })


class DepartmentDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        dept = get_object_or_404(Department, pk=pk)
        dept.delete()  # User.department→SET_NULL / DepartmentRoom→CASCADE
        request.session['toast'] = '所属を削除しました'
        return redirect('department_list')


# ── 操作ログ閲覧 ──────────────────────────────────────────────
class OperationLogView(StaffRequiredMixin, View):
    template_name = 'admin_panel/operation_log.html'
    PER_PAGE = 50

    def get(self, request):
        qs = OperationLog.objects.select_related('user', 'reservation__room').order_by('-created_at')

        # 絞り込み
        action = request.GET.get('action', '').strip()
        date_from_str = request.GET.get('date_from', '').strip()
        date_to_str   = request.GET.get('date_to', '').strip()
        user_q        = request.GET.get('user', '').strip()
        room_q        = request.GET.get('room', '').strip()

        if action:
            qs = qs.filter(action=action)
        if date_from_str:
            try:
                qs = qs.filter(created_at__date__gte=date.fromisoformat(date_from_str))
            except ValueError:
                pass
        if date_to_str:
            try:
                qs = qs.filter(created_at__date__lte=date.fromisoformat(date_to_str))
            except ValueError:
                pass
        if user_q:
            qs = qs.filter(user__name__icontains=user_q)
        if room_q:
            qs = qs.filter(room_name__icontains=room_q)

        total = qs.count()
        page_obj = Paginator(qs, self.PER_PAGE).get_page(request.GET.get('page'))

        return render(request, self.template_name, {
            'page_obj':    page_obj,
            'total':       total,
            'action_choices': OperationLog.ACTION_CHOICES,
            'q_action':    action,
            'q_date_from': date_from_str,
            'q_date_to':   date_to_str,
            'q_user':      user_q,
            'q_room':      room_q,
        })