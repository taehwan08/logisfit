"""
거래처 뷰 모듈

거래처 CRUD, 단가 계약 관리 뷰를 정의합니다.
"""
import json

from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy, reverse
from django.views.generic import (
    ListView, CreateView, UpdateView, DetailView, View, FormView
)
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.utils import timezone

from .models import Client, PriceContract
from .forms import ClientForm, PriceContractForm, PriceContractBulkForm
from apps.accounts.models import User


class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """관리자 권한 필요 믹스인"""

    def test_func(self):
        return self.request.user.is_admin or self.request.user.is_superuser

    def handle_no_permission(self):
        messages.error(self.request, '관리자 권한이 필요합니다.')
        return redirect('dashboard')


# ============================================================================
# 거래처 Views
# ============================================================================

class ClientListView(LoginRequiredMixin, ListView):
    """거래처 목록 뷰"""
    model = Client
    template_name = 'clients/client_list.html'
    context_object_name = 'clients'
    paginate_by = 20

    def get_queryset(self):
        queryset = Client.objects.select_related('created_by')

        if not (self.request.user.is_admin or self.request.user.is_superuser):
            queryset = queryset.filter(is_active=True)

        status = self.request.GET.get('status')
        if status == 'active':
            queryset = queryset.filter(is_active=True)
        elif status == 'inactive':
            queryset = queryset.filter(is_active=False)

        search = self.request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(company_name__icontains=search) |
                Q(business_number__icontains=search) |
                Q(contact_person__icontains=search)
            )

        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('search', '')
        context['current_status'] = self.request.GET.get('status', 'all')
        context['total_count'] = Client.objects.count()
        context['active_count'] = Client.objects.filter(is_active=True).count()
        context['inactive_count'] = Client.objects.filter(is_active=False).count()
        return context


class ClientCreateView(AdminRequiredMixin, CreateView):
    """거래처 등록 뷰"""
    model = Client
    form_class = ClientForm
    template_name = 'clients/client_form.html'
    success_url = reverse_lazy('clients:client_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, '거래처가 등록되었습니다.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '거래처 등록'
        context['is_create'] = True
        return context


class ClientUpdateView(AdminRequiredMixin, UpdateView):
    """거래처 수정 뷰"""
    model = Client
    form_class = ClientForm
    template_name = 'clients/client_form.html'

    def get_success_url(self):
        return reverse('clients:client_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, '거래처 정보가 수정되었습니다.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '거래처 수정'
        context['is_create'] = False
        return context


class ClientDetailView(LoginRequiredMixin, DetailView):
    """거래처 상세 뷰"""
    model = Client
    template_name = 'clients/client_detail.html'
    context_object_name = 'client'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.object
        today = timezone.now().date()

        # 현재 유효한 단가 계약
        context['current_price_contracts'] = client.price_contracts.filter(
            valid_from__lte=today, valid_to__gte=today
        )
        # 전체 단가 계약 이력
        context['all_price_contracts'] = client.price_contracts.all()

        # 연결된 사용자 (거래처 역할)
        context['linked_users'] = client.users.filter(
            role=User.Role.CLIENT, is_active=True
        ).order_by('name')

        # 연결 가능한 사용자 (거래처 역할이면서 아직 이 거래처에 연결 안 된 사용자)
        context['available_users'] = User.objects.filter(
            role=User.Role.CLIENT, is_active=True
        ).exclude(
            clients=client
        ).order_by('name')

        return context


class ClientDeleteView(AdminRequiredMixin, View):
    """거래처 비활성화 뷰 (소프트 삭제)"""

    def post(self, request, pk):
        client = get_object_or_404(Client, pk=pk)
        client.is_active = False
        client.save()
        messages.success(request, f'{client.company_name} 거래처가 비활성화되었습니다.')
        return redirect('clients:client_list')


# ============================================================================
# 단가 계약 Views
# ============================================================================

class PriceContractCreateView(AdminRequiredMixin, CreateView):
    """단가 계약 개별 등록 뷰"""
    model = PriceContract
    form_class = PriceContractForm
    template_name = 'clients/price_contract_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['client'] = get_object_or_404(Client, pk=self.kwargs['client_id'])
        context['page_title'] = '단가 계약 등록'
        return context

    def form_valid(self, form):
        form.instance.client = get_object_or_404(Client, pk=self.kwargs['client_id'])
        form.instance.created_by = self.request.user
        messages.success(self.request, '단가 계약이 등록되었습니다.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('clients:client_detail', kwargs={'pk': self.kwargs['client_id']})


class PriceContractBulkCreateView(AdminRequiredMixin, FormView):
    """단가 계약 일괄 등록 뷰 - 모든 작업유형을 테이블로 한번에 입력"""
    template_name = 'clients/price_contract_bulk_form.html'
    form_class = PriceContractBulkForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['client'] = get_object_or_404(Client, pk=self.kwargs['client_id'])
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['client'] = get_object_or_404(Client, pk=self.kwargs['client_id'])
        context['work_type_groups_json'] = json.dumps(
            PriceContractBulkForm.get_work_type_groups_data(),
            ensure_ascii=False,
        )
        return context

    def form_valid(self, form):
        contracts = form.save(user=self.request.user)
        if contracts:
            messages.success(self.request, f'{len(contracts)}건의 단가 계약이 등록되었습니다.')
        else:
            messages.warning(self.request, '입력된 단가가 없습니다.')
        return redirect('clients:client_detail', pk=self.kwargs['client_id'])


class PriceContractUpdateView(AdminRequiredMixin, UpdateView):
    """단가 계약 수정 뷰"""
    model = PriceContract
    form_class = PriceContractForm
    template_name = 'clients/price_contract_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['client'] = self.object.client
        context['page_title'] = '단가 계약 수정'
        return context

    def form_valid(self, form):
        messages.success(self.request, '단가 계약이 수정되었습니다.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('clients:client_detail', kwargs={'pk': self.object.client.pk})


class PriceContractDeleteView(AdminRequiredMixin, View):
    """단가 계약 삭제 뷰"""

    def post(self, request, pk):
        contract = get_object_or_404(PriceContract, pk=pk)
        client_pk = contract.client.pk
        contract.delete()
        messages.success(request, '단가 계약이 삭제되었습니다.')
        return redirect('clients:client_detail', pk=client_pk)


# ============================================================================
# 거래처-사용자 매칭 API
# ============================================================================

def _is_admin(user):
    return user.is_authenticated and (user.is_admin or user.is_superuser)


@login_required
@require_http_methods(["POST"])
def add_client_user(request, pk):
    """거래처에 사용자 연결"""
    if not _is_admin(request.user):
        return JsonResponse({'error': '관리자 권한이 필요합니다.'}, status=403)

    client = get_object_or_404(Client, pk=pk)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': '잘못된 요청입니다.'}, status=400)

    user_id = data.get('user_id')
    if not user_id:
        return JsonResponse({'error': '사용자를 선택해주세요.'}, status=400)

    try:
        target_user = User.objects.get(id=user_id, role=User.Role.CLIENT, is_active=True)
    except User.DoesNotExist:
        return JsonResponse({'error': '해당 거래처 사용자를 찾을 수 없습니다.'}, status=404)

    if client in target_user.clients.all():
        return JsonResponse({'error': '이미 연결된 사용자입니다.'}, status=400)

    target_user.clients.add(client)

    return JsonResponse({
        'success': True,
        'message': f'{target_user.name}님이 연결되었습니다.',
        'user': {
            'id': target_user.id,
            'name': target_user.name,
            'email': target_user.email,
            'phone': target_user.phone or '-',
        },
    })


@login_required
@require_http_methods(["POST"])
def remove_client_user(request, pk):
    """거래처에서 사용자 연결 해제"""
    if not _is_admin(request.user):
        return JsonResponse({'error': '관리자 권한이 필요합니다.'}, status=403)

    client = get_object_or_404(Client, pk=pk)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': '잘못된 요청입니다.'}, status=400)

    user_id = data.get('user_id')
    if not user_id:
        return JsonResponse({'error': '사용자를 선택해주세요.'}, status=400)

    try:
        target_user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return JsonResponse({'error': '사용자를 찾을 수 없습니다.'}, status=404)

    target_user.clients.remove(client)

    return JsonResponse({
        'success': True,
        'message': f'{target_user.name}님이 연결 해제되었습니다.',
    })
