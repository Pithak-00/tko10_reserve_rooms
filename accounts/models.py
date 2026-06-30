from django.db import models
from django.utils import timezone
from django.contrib.auth.models import (
    AbstractBaseUser,
    PermissionsMixin,
    BaseUserManager,
)

from config import settings


class Department(models.Model):
    id = models.BigAutoField(primary_key=True)

    name = models.CharField(
        max_length=100,
        unique=True,
        db_column="name",
        verbose_name="所属名称",
    )

    created_at = models.DateTimeField(
        default=timezone.now,
        db_column="created_at",
        verbose_name="作成日時",
    )

    class Meta:
        db_table = "departments"
        verbose_name = "所属"
        verbose_name_plural = "所属"

    def __str__(self):
        return self.name


class UserManager(BaseUserManager):
    def create_user(self, login_id, name, password=None, **extra_fields):
        if not login_id:
            raise ValueError("login_id は必須です")
        if not name:
            raise ValueError("name は必須です")

        user = self.model(login_id=login_id, name=name, **extra_fields)

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save(using=self._db)
        return user

    def create_superuser(self, login_id, name, password=None, **extra_fields):
        extra_fields.setdefault("role", "admin")
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_superuser", True)

        user = self.create_user(
            login_id=login_id, name=name, password=password, **extra_fields
        )
        return user


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ("admin", "admin"),
        ("user", "user"),
    ]

    id = models.BigAutoField(primary_key=True)

    login_id = models.CharField(
        max_length=50,
        unique=True,
        db_column="login_id",
        verbose_name="ログインID",
    )

    name = models.CharField(
        max_length=100,
        db_column="name",
        verbose_name="氏名",
    )

    password = models.CharField(
        max_length=255,
        db_column="password_hash",
        verbose_name="パスワードハッシュ",
    )

    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default="user",
        db_column="role",
        verbose_name="権限種別",
    )

    department = models.ForeignKey(
        Department,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="department_id",
        related_name="users",
        verbose_name="所属",
    )

    is_active = models.BooleanField(
        default=True,
        db_column="is_active",
        verbose_name="有効フラグ",
    )

    last_login = models.DateTimeField(
        null=True,
        blank=True,
        db_column="last_login_at",
        verbose_name="最終ログイン日時",
    )

    created_at = models.DateTimeField(
        default=timezone.now,
        db_column="created_at",
        verbose_name="作成日時",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        db_column="updated_at",
        verbose_name="更新日時",
    )

    objects = UserManager()

    USERNAME_FIELD = "login_id"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        db_table = "users"
        verbose_name = "ユーザー"
        verbose_name_plural = "ユーザー"

    def __str__(self):
        return f"{self.login_id} - {self.name}"

    @property
    def is_staff(self):
        return self.role == "admin"
