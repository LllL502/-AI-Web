from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Station, StationAccessApplication
from .serializers import StationSerializer, StationAccessApplicationSerializer
from .scope import selected_campus
from rest_framework.views import APIView
from .models import School, Campus, CampusFeedback
from django.db.models import Q
from django.core.paginator import Paginator
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle
from apps.accounts.permissions import IsAdminRole
from django.db import transaction
from django.utils import timezone
from apps.administration.models import AuditLog


def public_campuses(school):
    """已核实目录具有权威性；地图候选仅在尚无已核实资料时对外可选。"""
    active = [campus for campus in school.campuses.all() if campus.is_active]
    verified = [campus for campus in active if campus.verification_status == 'VERIFIED']
    rows = verified or active
    return [{
        'id': campus.pk,
        'name': campus.name,
        'code': campus.code,
        'verification_status': campus.verification_status,
        'source_url': campus.source_url,
    } for campus in rows]


class CampusDirectoryView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        queryset = School.objects.prefetch_related("campuses").order_by("name_pinyin", "name", "id")
        query = request.query_params.get("q", "").strip()[:100]
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(search_text__icontains=query) | Q(name_pinyin__icontains=query))
        campus_id = request.query_params.get("current_campus")
        if campus_id:
            queryset = queryset.filter(campuses__id=campus_id)
        paginator = Paginator(queryset, 20)
        page = paginator.get_page(request.query_params.get("page", 1))
        return Response({"data": {"schools": [
            {"id": school.pk, "name": school.name, "is_demo": school.is_demo, "province":school.province, "city":school.city,
             "priority":school.priority,
             "campuses": public_campuses(school)}
            for school in page
        ], "total":paginator.count, "page":page.number, "pages":paginator.num_pages}})


class CampusFeedbackSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source='school.name', read_only=True)

    class Meta:
        model = CampusFeedback
        fields = ['id','school','school_name','campus_name','detail','source_url','status','review_note','created_at']
        read_only_fields = ['id','status','review_note','created_at']


class CampusFeedbackView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'campus_feedback'

    def post(self, request):
        serializer = CampusFeedbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        feedback = serializer.save(reporter=request.user)
        return Response({'data':CampusFeedbackSerializer(feedback).data}, status=201)


class CampusFeedbackReviewView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        rows = CampusFeedback.objects.filter(status='PENDING').select_related('school').order_by('created_at')[:100]
        return Response({'data':{'items':CampusFeedbackSerializer(rows, many=True).data}})

    @transaction.atomic
    def post(self, request):
        from rest_framework.exceptions import ValidationError, NotFound
        try:
            feedback = CampusFeedback.objects.select_for_update().get(pk=request.data.get('id'))
        except (CampusFeedback.DoesNotExist, ValueError, TypeError):
            raise NotFound('反馈不存在')
        if feedback.status != 'PENDING':
            raise ValidationError('反馈已处理')
        decision = request.data.get('decision')
        if decision not in ['APPROVE','REJECT']:
            raise ValidationError('无效审核决定')
        if decision == 'APPROVE':
            source = serializers.URLField().run_validation(request.data.get('source_url'))
            name = serializers.CharField(max_length=100).run_validation(request.data.get('campus_name',feedback.campus_name))
            campus = Campus.objects.filter(school=feedback.school, name=name).first()
            if campus is None:
                campus = Campus(school=feedback.school, name=name, code=f'feedback-{feedback.pk}')
            campus.source_url = source
            campus.verification_status = 'VERIFIED'
            campus.verified_at = timezone.localdate()
            campus.save()
        feedback.status = 'APPROVED' if decision == 'APPROVE' else 'REJECTED'
        feedback.reviewed_by = request.user
        feedback.review_note = str(request.data.get('note',''))[:500]
        feedback.save()
        AuditLog.objects.create(actor=request.user,action='campus_feedback.'+decision.lower(),target_type='CampusFeedback',target_id=str(feedback.pk),after={'status':feedback.status},request_id=request.request_id)
        return Response({'data':CampusFeedbackSerializer(feedback).data})


class StationViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = StationSerializer
    queryset = Station.objects.filter(
        is_active=True, approval_status=Station.ApprovalStatus.APPROVED
    ).select_related("location").order_by("name")

    def get_queryset(self):
        return self.queryset.filter(location__campus_id=selected_campus(self.request))

    def retrieve(self, request, *args, **kwargs):
        return Response({"data": self.get_serializer(self.get_object()).data})


class StationAccessApplicationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = StationAccessApplicationSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return StationAccessApplication.objects.filter(applicant=self.request.user).select_related("school", "campus")

    def perform_create(self, serializer):
        serializer.save(applicant=self.request.user)
