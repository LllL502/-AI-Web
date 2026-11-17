from rest_framework import serializers

from .models import CampusLocation, Station


class CampusLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = CampusLocation
        fields = ["id", "name", "code", "parent_id", "public_precision"]


class StationSerializer(serializers.ModelSerializer):
    location = CampusLocationSerializer(read_only=True)

    class Meta:
        model = Station
        fields = ["id", "name", "code", "location", "address", "opening_hours", "capacity", "status"]
