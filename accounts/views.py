"""Регистрация: открытая, без подтверждения по почте.

Вход и выход - штатные представления Django (`config/urls.py`); здесь только
создание аккаунта: пользователь сразу входит и получает доступ к своим данным.
Данные изолированы по владельцу, поэтому регистрация никому не мешает.
"""
from django.contrib.auth import login
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.forms import UserCreationForm
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render


@login_not_required
def signup(request: HttpRequest) -> HttpResponse:
    """Создаёт пользователя и сразу входит под ним."""
    if request.user.is_authenticated:
        return redirect("home")

    form = UserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("home")
    return render(request, "registration/signup.html", {"form": form})
