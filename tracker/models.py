import unicodedata
from django.conf import settings
from django.db import models

def normalize_type(value):
    return " ".join(unicodedata.normalize("NFKC", value).replace("ي", "ی").replace("ك", "ک").split()).casefold()

class WorkType(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=80)
    normalized_name = models.CharField(max_length=160)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "normalized_name"], name="unique_user_work_type")]
        ordering = ["name"]
    def __str__(self):
        return self.name

class Entry(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    work_type = models.ForeignKey(WorkType, on_delete=models.PROTECT, related_name="entries")
    date = models.DateField()
    minutes = models.PositiveSmallIntegerField()
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [models.Index(fields=["user", "date"])]
        constraints = [models.CheckConstraint(condition=models.Q(minutes__gte=1, minutes__lte=1440), name="valid_minutes")]
