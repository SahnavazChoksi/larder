from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from audit.services import log

from .models import User
from .permissions import IsOwner
from .serializers import MeSerializer, UserSerializer


class LoginView(TokenObtainPairView):
    """Username + password in, access and refresh tokens out. Successful logins are audited."""

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            user = User.objects.filter(username=request.data.get("username")).first()
            if user:
                log(user, "Signed in", "")
        return response


class MeView(APIView):
    def get(self, request):
        return Response(MeSerializer(request.user).data)


class UserViewSet(viewsets.ModelViewSet):
    """Owners manage staff accounts. Users are deactivated, never deleted, so the audit trail stays intact."""

    serializer_class = UserSerializer
    permission_classes = [IsOwner]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return User.objects.prefetch_related("locations").order_by("role", "username")

    def perform_create(self, serializer):
        user = serializer.save()
        log(self.request.user, "Created user", f"{user.username} as {user.get_role_display()}")

    def perform_update(self, serializer):
        changed = sorted(k for k in serializer.validated_data if k != "password")
        if "password" in serializer.validated_data:
            changed.append("password")
        user = serializer.save()
        log(self.request.user, "Updated user", f"{user.username}: changed {', '.join(changed) or 'nothing'}")
