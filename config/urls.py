from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from tracker import views
router = DefaultRouter()
router.register("entries", views.EntryViewSet, basename="entry")
urlpatterns = [path("admin/", admin.site.urls), path("api/auth/csrf/", views.csrf), path("api/auth/login/", views.LoginView.as_view()), path("api/auth/logout/", views.LogoutView.as_view()), path("api/auth/me/", views.MeView.as_view()), path("api/work-types/", views.WorkTypesView.as_view()), path("api/analytics/", views.AnalyticsView.as_view()), path("api/", include(router.urls))]
