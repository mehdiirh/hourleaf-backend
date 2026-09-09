from datetime import date, timedelta
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.db import transaction
from django.db.models import Sum, Count, Max
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from .models import Entry, WorkType, normalize_type
from .serializers import EntrySerializer

@require_GET
@never_cache
@ensure_csrf_cookie
def csrf(request):
    return JsonResponse({"csrfToken": get_token(request)})

@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"
    def post(self, request):
        username, password = request.data.get("username"), request.data.get("password")
        if not isinstance(username, str) or not isinstance(password, str):
            return Response({"detail": "Enter your username and password."}, status=400)
        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response({"detail": "Incorrect username or password."}, status=400)
        login(request, user)
        return Response({"username": user.username, "first_name": user.first_name, "csrfToken": get_token(request)})

class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response(status=204)

class MeView(APIView):
    def get(self, request):
        return Response({"username": request.user.username, "first_name": request.user.first_name})

def date_range(params):
    try:
        start = date.fromisoformat(params.get("from", date.today().replace(month=1, day=1).isoformat()))
        end = date.fromisoformat(params.get("to", date.today().replace(month=12, day=31).isoformat()))
    except (ValueError, TypeError):
        raise ValidationError("Dates must use YYYY-MM-DD.")
    if end < start or (end - start).days > 365:
        raise ValidationError("Choose a range of at most 366 days, with the end after the start.")
    return start, end

class EntryViewSet(viewsets.ModelViewSet):
    serializer_class = EntrySerializer
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]
    def get_queryset(self):
        qs = Entry.objects.filter(user=self.request.user).select_related("work_type")
        if self.action == "list":
            if "from" in self.request.query_params or "to" in self.request.query_params:
                start, end = date_range(self.request.query_params)
                qs = qs.filter(date__range=(start, end))
            if self.request.query_params.get("work_type"):
                qs = qs.filter(work_type__normalized_name=normalize_type(self.request.query_params["work_type"]))
        return qs
    def _save(self, serializer):
        with transaction.atomic():
            # Serialize writes for each user to enforce the daily limit under concurrency.
            get_user_model().objects.select_for_update().get(pk=self.request.user.pk)
            instance = serializer.instance
            day = serializer.validated_data.get("date", instance.date if instance else None)
            minutes = serializer.validated_data.get("minutes", instance.minutes if instance else 0)
            others = Entry.objects.filter(user=self.request.user, date=day)
            if instance:
                others = others.exclude(pk=instance.pk)
            total = others.aggregate(total=Sum("minutes"))["total"] or 0
            if total + minutes > 1440:
                raise ValidationError("A day cannot contain more than 24 hours of work.")
            start = serializer.validated_data.get("start_time", instance.start_time if instance else None)
            end = serializer.validated_data.get("end_time", instance.end_time if instance else None)
            if start and end and others.filter(start_time__lt=end, end_time__gt=start).exists():
                raise ValidationError("This time range overlaps another entry on this date.")
            name = serializer.validated_data.pop("work_type", None)
            work_type = instance.work_type if instance else None
            if name is not None:
                work_type, _ = WorkType.objects.get_or_create(user=self.request.user, normalized_name=normalize_type(name), defaults={"name": name})
            serializer.save(user=self.request.user, work_type=work_type)
    def perform_create(self, serializer):
        self._save(serializer)
    def perform_update(self, serializer):
        self._save(serializer)

class WorkTypesView(APIView):
    def get(self, request):
        qs = WorkType.objects.filter(user=request.user)
        query = normalize_type(request.query_params.get("q", ""))
        if query:
            qs = qs.filter(normalized_name__icontains=query)
        return Response(list(qs.annotate(uses=Count("entries"), last_used=Max("entries__date")).order_by("-uses", "name").values("id", "name", "uses", "last_used")[:100]))

class AnalyticsView(APIView):
    def get(self, request):
        start, end = date_range(request.query_params)
        qs = Entry.objects.filter(user=request.user, date__range=(start, end))
        if request.query_params.get("work_type"):
            qs = qs.filter(work_type__normalized_name=normalize_type(request.query_params["work_type"]))
        days = list(qs.values("date").annotate(minutes=Sum("minutes")).order_by("date"))
        categories = list(qs.values("work_type__name").annotate(minutes=Sum("minutes"), entries=Count("id")).order_by("-minutes"))
        total = sum(d["minutes"] for d in days)
        best = run = 0
        previous = None
        for day in days:
            run = run + 1 if previous and day["date"] == previous + timedelta(days=1) else 1
            best = max(best, run)
            previous = day["date"]
        return Response({"from": start, "to": end, "total_minutes": total, "active_days": len(days), "average_minutes": round(total / len(days)) if days else 0, "longest_streak": best, "days": days, "categories": [{"name": c["work_type__name"], "minutes": c["minutes"], "entries": c["entries"]} for c in categories]})
