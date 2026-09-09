import re
from rest_framework import serializers
from .models import Entry, normalize_type


class EntrySerializer(serializers.ModelSerializer):
    work_type = serializers.CharField(max_length=80)
    duration = serializers.CharField(write_only=True, required=False)
    minutes = serializers.IntegerField(read_only=True)
    start_time = serializers.TimeField(
        required=False, allow_null=True, input_formats=["%H:%M"], format="%H:%M"
    )
    end_time = serializers.TimeField(
        required=False, allow_null=True, input_formats=["%H:%M"], format="%H:%M"
    )

    class Meta:
        model = Entry
        fields = [
            "id",
            "date",
            "work_type",
            "duration",
            "minutes",
            "start_time",
            "end_time",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["work_type"] = instance.work_type.name
        return data

    def validate_work_type(self, value):
        name = " ".join(value.split())
        normalized = normalize_type(name)
        if len(normalized) > 160:
            raise serializers.ValidationError(
                "Work type is too long after Unicode normalization."
            )
        if not normalized:
            raise serializers.ValidationError("Enter a work type.")
        return name

    def validate(self, attrs):
        duration = attrs.pop("duration", None)
        start, end = attrs.get("start_time"), attrs.get("end_time")
        has_times = "start_time" in attrs or "end_time" in attrs
        if duration is not None:
            if start is not None or end is not None:
                raise serializers.ValidationError("Use a duration OR a time range.")
            if not re.fullmatch(r"\d{1,2}:[0-5]\d", duration):
                raise serializers.ValidationError(
                    {"duration": "Use HH:MM, for example 07:30."}
                )
            hours, mins = map(int, duration.split(":"))
            attrs.update(minutes=hours * 60 + mins, start_time=None, end_time=None)
        elif has_times:
            if start is None or end is None:
                raise serializers.ValidationError(
                    "Both start and end times are required."
                )
            minutes = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
            if minutes <= 0:
                raise serializers.ValidationError(
                    "End time must be after start time. Split overnight work into two dates."
                )
            attrs["minutes"] = minutes
        elif not self.instance:
            raise serializers.ValidationError("Enter a duration or a time range.")
        if "minutes" in attrs and not 1 <= attrs["minutes"] <= 1440:
            raise serializers.ValidationError(
                {"duration": "Duration must be between 00:01 and 24:00."}
            )
        return attrs
