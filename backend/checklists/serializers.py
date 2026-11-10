from rest_framework import serializers

from .models import SOP, ChecklistRun, ChecklistTemplate, RunAnswer, TemplateTask


def _name(user):
    return user.display_name if user else None


class SOPSerializer(serializers.ModelSerializer):
    steps = serializers.ListField(child=serializers.CharField(), read_only=True)
    updated_by_name = serializers.SerializerMethodField()

    class Meta:
        model = SOP
        fields = ["id", "title", "category", "body", "steps", "is_active", "updated_by_name", "updated_at"]

    def get_updated_by_name(self, sop):
        return _name(sop.updated_by)


class TaskSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    sop_title = serializers.CharField(source="sop.title", read_only=True, default=None)

    class Meta:
        model = TemplateTask
        fields = ["id", "position", "text", "sop", "sop_title", "requires_photo", "value_label", "value_unit",
                  "value_min", "value_max", "is_critical"]
        extra_kwargs = {"position": {"required": False}}

    def validate(self, data):
        lo, hi = data.get("value_min"), data.get("value_max")
        if lo is not None and hi is not None and lo > hi:
            raise serializers.ValidationError("The minimum is above the maximum.")
        if (lo is not None or hi is not None) and not data.get("value_label"):
            raise serializers.ValidationError("Add a reading label (e.g. 'Walk-in temperature') to use limits.")
        return data


class TemplateSerializer(serializers.ModelSerializer):
    tasks = serializers.SerializerMethodField()
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    applies_label = serializers.CharField(source="get_applies_to_display", read_only=True)

    class Meta:
        model = ChecklistTemplate
        fields = ["id", "name", "kind", "kind_label", "applies_to", "applies_label", "due_by", "is_active", "tasks"]

    def get_tasks(self, t):
        return TaskSerializer(t.tasks.filter(is_active=True).select_related("sop"), many=True).data


class TemplateIn(serializers.Serializer):
    name = serializers.CharField(max_length=80)
    kind = serializers.ChoiceField(choices=ChecklistTemplate.Kind.choices)
    applies_to = serializers.ChoiceField(choices=ChecklistTemplate.AppliesTo.choices)
    due_by = serializers.TimeField(required=False, allow_null=True)
    is_active = serializers.BooleanField(default=True)
    tasks = TaskSerializer(many=True)

    def validate_tasks(self, tasks):
        if not tasks:
            raise serializers.ValidationError("A checklist needs at least one task.")
        return tasks


class AnswerSerializer(serializers.ModelSerializer):
    task_id = serializers.IntegerField(source="task.id", read_only=True)
    sop = serializers.SerializerMethodField()
    requires_photo = serializers.BooleanField(source="task.requires_photo", read_only=True)
    value_label = serializers.CharField(source="task.value_label", read_only=True)
    value_unit = serializers.CharField(source="task.value_unit", read_only=True)
    value_min = serializers.DecimalField(source="task.value_min", max_digits=10, decimal_places=2, read_only=True)
    value_max = serializers.DecimalField(source="task.value_max", max_digits=10, decimal_places=2, read_only=True)
    is_critical = serializers.BooleanField(source="task.is_critical", read_only=True)
    photo_url = serializers.SerializerMethodField()
    out_of_range = serializers.BooleanField(read_only=True)
    done_by_name = serializers.SerializerMethodField()

    class Meta:
        model = RunAnswer
        fields = ["id", "task_id", "task_text", "sop", "requires_photo", "value_label", "value_unit", "value_min",
                  "value_max", "is_critical", "done", "value", "note", "photo_url", "out_of_range",
                  "done_by_name", "done_at"]

    def get_sop(self, a):
        sop = a.task.sop
        return {"id": sop.id, "title": sop.title, "steps": sop.steps} if sop else None

    def get_photo_url(self, a):
        # Relative URL: the dev server proxies /media to Django.
        return a.photo.url if a.photo else None

    def get_done_by_name(self, a):
        return _name(a.done_by)


class AnswerIn(serializers.Serializer):
    done = serializers.BooleanField(required=False)
    value = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    note = serializers.CharField(max_length=300, required=False, allow_blank=True)
    photo = serializers.ImageField(required=False)


class RunSerializer(serializers.ModelSerializer):
    number = serializers.CharField(read_only=True)
    template_name = serializers.CharField(source="template.name")
    kind = serializers.CharField(source="template.kind")
    location_name = serializers.CharField(source="location.name")
    status_label = serializers.CharField(source="get_status_display")
    started_by_name = serializers.SerializerMethodField()
    submitted_by_name = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    photos = serializers.SerializerMethodField()
    issue_count = serializers.SerializerMethodField()

    class Meta:
        model = ChecklistRun
        fields = ["id", "number", "template", "template_name", "kind", "location", "location_name", "business_date",
                  "status", "status_label", "started_by_name", "submitted_by_name", "submitted_at",
                  "reviewed_by_name", "reviewed_at", "review_note", "progress", "photos", "issue_count"]

    def _answers(self, run):
        if not hasattr(run, "_answers_cache"):
            run._answers_cache = list(run.answers.select_related("task"))
        return run._answers_cache

    def get_started_by_name(self, r):
        return _name(r.started_by)

    def get_submitted_by_name(self, r):
        return _name(r.submitted_by)

    def get_reviewed_by_name(self, r):
        return _name(r.reviewed_by)

    def get_progress(self, r):
        answers = self._answers(r)
        return {"done": sum(1 for a in answers if a.done), "total": len(answers)}

    def get_photos(self, r):
        return sum(1 for a in self._answers(r) if a.photo)

    def get_issue_count(self, r):
        return sum(1 for a in self._answers(r) if (a.value is not None and a.out_of_range) or a.note)


class RunDetailSerializer(RunSerializer):
    answers = serializers.SerializerMethodField()
    issues = serializers.SerializerMethodField()

    class Meta(RunSerializer.Meta):
        fields = RunSerializer.Meta.fields + ["answers", "issues"]

    def get_answers(self, r):
        return AnswerSerializer(self._answers(r), many=True).data

    def get_issues(self, r):
        from .services import issues

        return issues(r)

