def log(user, action, detail="", location=None):
    """Write one audit entry. Call this from views after a change succeeds."""
    from .models import AuditEntry

    return AuditEntry.objects.create(
        user=user if (user is not None and user.is_authenticated) else None,
        action=action[:60],
        detail=detail,
        location=location,
    )
