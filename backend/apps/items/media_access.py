"""Media uses the same live authorization boundary as its owning record."""
import mimetypes
from django.db.models import Q
from django.http import FileResponse, Http404
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from apps.stations.scope import selected_campus
from .models import MediaAsset


class ItemMediaView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, path):
        asset = MediaAsset.objects.select_related('item__location').filter(Q(file=path) | Q(thumbnail=path)).first()
        if not asset or asset.item.location.campus_id != selected_campus(request):
            raise Http404
        item, user = asset.item, request.user
        allowed = asset.is_public and item.review_status == 'APPROVED' and item.business_status == 'OPEN'
        if user.is_authenticated and not allowed:
            allowed = item.owner_id == user.pk or user.role == 'ADMIN'
            if not allowed and user.role == 'STAFF':
                allowed = user.station_memberships.filter(is_active=True, station_id=item.station_id).exists()
            # A claimant retains access to the actual item needed for verification.
            if not allowed:
                allowed = item.claims.filter(claimant=user, claimant_deleted_at__isnull=True).exists()
        if not allowed:
            raise Http404
        field = asset.file if asset.file.name == path else asset.thumbnail
        try:
            response = FileResponse(field.storage.open(field.name, 'rb'), content_type=mimetypes.guess_type(field.name)[0] or 'application/octet-stream')
        except (OSError, ValueError):
            raise Http404 from None
        response['Cache-Control'] = 'private, no-store'
        response['Vary'] = 'Cookie, X-Campus-ID'
        response['X-Content-Type-Options'] = 'nosniff'
        return response
