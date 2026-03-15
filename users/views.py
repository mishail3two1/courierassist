from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render

from orders.models import Order, OrderStatus

from .forms import RegisterForm

User = get_user_model()


def get_linked_telegram_user_from_session(request):
    telegram_debug_user = request.session.get("telegram_debug_user")

    if not telegram_debug_user:
        return None, None

    telegram_id = telegram_debug_user.get("id")
    if not telegram_id:
        return telegram_debug_user, None

    linked_user = User.objects.filter(telegram_user_id=telegram_id).first()
    return telegram_debug_user, linked_user


@login_required
def cabinet(request):
    if request.method == "POST" and request.POST.get("action") == "save_telegram_user_debug":
        telegram_user = {
            "id": request.POST.get("telegram_id", "").strip(),
            "username": request.POST.get("telegram_username", "").strip(),
            "first_name": request.POST.get("telegram_first_name", "").strip(),
            "last_name": request.POST.get("telegram_last_name", "").strip(),
            "language_code": request.POST.get("telegram_language_code", "").strip(),
        }

        request.session["telegram_debug_user"] = telegram_user
        request.session.modified = True

        telegram_id = telegram_user.get("id")
        linked_user_payload = None

        if telegram_id:
            linked_user = User.objects.filter(telegram_user_id=telegram_id).first()
            if linked_user:
                linked_user_payload = {
                    "username": linked_user.username,
                    "role": linked_user.get_role_display(),
                    "telegram_user_id": linked_user.telegram_user_id,
                }

        return JsonResponse(
            {
                "ok": True,
                "telegram_user": telegram_user,
                "linked_user": linked_user_payload,
            }
        )

    if request.method == "POST" and request.POST.get("action") == "link_telegram_account":
        telegram_user = request.session.get("telegram_debug_user")

        if not telegram_user or not telegram_user.get("id"):
            request.session["telegram_link_result"] = {
                "ok": False,
                "text": "Telegram-пользователь ещё не получен на этой странице.",
            }
            return redirect("cabinet")

        existing_user = User.objects.filter(
            telegram_user_id=telegram_user["id"]
        ).exclude(pk=request.user.pk).first()

        if existing_user:
            request.session["telegram_link_result"] = {
                "ok": False,
                "text": "Этот Telegram уже привязан к другому пользователю.",
            }
            return redirect("cabinet")

        request.user.telegram_user_id = int(telegram_user["id"])
        request.user.telegram_username = telegram_user.get("username", "")
        request.user.save(update_fields=["telegram_user_id", "telegram_username"])

        request.session["telegram_link_result"] = {
            "ok": True,
            "text": "Telegram успешно привязан к вашему аккаунту.",
        }
        return redirect("cabinet")

    user = request.user
    all_orders = Order.objects.filter(courier=user)

    total_orders = all_orders.count()
    in_progress_orders = all_orders.filter(status=OrderStatus.IN_PROGRESS).count()
    delivered_orders = all_orders.filter(status=OrderStatus.DELIVERED).count()

    telegram_debug_user, linked_telegram_user = get_linked_telegram_user_from_session(request)
    telegram_link_result = request.session.pop("telegram_link_result", None)

    context = {
        "total_orders": total_orders,
        "in_progress_orders": in_progress_orders,
        "delivered_orders": delivered_orders,
        "telegram_debug_user": telegram_debug_user,
        "linked_telegram_user": linked_telegram_user,
        "telegram_link_result": telegram_link_result,
    }
    return render(request, "users/cabinet.html", context)


def register(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("/accounts/login/?registered=1")
    else:
        form = RegisterForm()

    return render(request, "registration/register.html", {"form": form})
