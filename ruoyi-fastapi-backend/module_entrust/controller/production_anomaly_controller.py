"""
对账系统 — 生产异常 Controller
=========================================
API 路由：
  POST /entrust/production-anomaly/          — 创建生产异常
  GET  /entrust/production-anomaly/list      — 生产异常列表（分页+筛选）
  GET  /entrust/production-anomaly/{id}      — 生产异常详情
  PUT  /entrust/production-anomaly/{id}/liability    — 判定责任方
  POST /entrust/production-anomaly/{id}/re-shipment  — 创建补发请求
  POST /entrust/production-anomaly/{id}/re-shipment/{re_shipment_id}/confirm-shipment — 确认补发发货
  POST /entrust/production-anomaly/{id}/deduction    — 创建扣款记录
  POST /entrust/production-anomaly/{id}/negotiation  — 记录协商过程

Requirements covered: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 13.1
"""
from typing import Annotated, Optional

from fastapi import Path, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel, ResponseBaseModel
from exceptions.exception import ServiceException
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_entrust.entity.do.reconciliation_do import (
    Deduction,
    NegotiationRecord,
    ProductionAnomaly,
    ReShipment,
)
from module_entrust.entity.vo.reconciliation_vo import (
    DeductionCreateRequest,
    DeductionResponse,
    LiabilitySetRequest,
    NegotiationCreateRequest,
    NegotiationRecordResponse,
    ProductionAnomalyBriefResponse,
    ProductionAnomalyCreateRequest,
    ProductionAnomalyResponse,
    ReShipmentConfirmRequest,
    ReShipmentCreateRequest,
    ReShipmentResponse,
)
from module_entrust.service.production_anomaly_service import (
    ProductionAnomalyService,
)
from utils.response_util import ResponseUtil

production_anomaly_controller = APIRouterPro(
    prefix='/entrust/production-anomaly',
    order_num=25,
    tags=['生产异常管理'],
    dependencies=[PreAuthDependency()],
)


# ── POST / — 创建生产异常 ────────────────────────────────────────────────────

@production_anomaly_controller.post(
    '/',
    summary='创建生产异常',
    response_model=DataResponseModel,
)
async def create_production_anomaly(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data: ProductionAnomalyCreateRequest,
):
    """
    创建生产异常记录。
    记录生产过程中的材料损坏、加工失误或零件不可使用事件。
    """
    try:
        anomaly_id = await ProductionAnomalyService.create_anomaly(
            db=query_db,
            order_id=data.order_id,
            part_id=data.part_id,
            anomaly_type=data.anomaly_type,
            description=data.description,
            occurred_at=data.occurred_at,
            material_cost=data.material_cost,
            rework_cost=data.rework_cost,
            delay_penalty=data.delay_penalty,
            created_by=current_user.user.user_id if current_user.user else 0,
        )
        return ResponseUtil.success(
            data={'anomaly_id': anomaly_id},
            msg='生产异常创建成功',
        )
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))


# ── GET /list — 生产异常列表（分页+筛选） ────────────────────────────────────

@production_anomaly_controller.get(
    '/list',
    summary='生产异常列表',
    response_model=PageResponseModel,
)
async def get_production_anomaly_list(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    order_id: Optional[int] = Query(default=None, description='委外工单ID'),
    anomaly_type: Optional[str] = Query(default=None, description='异常类型: material_damage/process_error/unusable'),
    liability_type: Optional[str] = Query(default=None, description='责任类型: material_supplier_fault/processor_fault'),
    status: Optional[str] = Query(default=None, description='状态: open/liability_confirmed/resolved/closed'),
    page_num: int = Query(default=1, ge=1, description='页码'),
    page_size: int = Query(default=10, ge=1, le=100, description='每页条数'),
):
    """生产异常列表，支持按工单、异常类型、责任类型、状态筛选，分页返回。"""
    stmt = select(ProductionAnomaly)
    count_stmt = select(func.count()).select_from(ProductionAnomaly)

    # 筛选条件
    filters = []
    if order_id is not None:
        filters.append(ProductionAnomaly.order_id == order_id)
    if anomaly_type is not None:
        filters.append(ProductionAnomaly.anomaly_type == anomaly_type)
    if liability_type is not None:
        filters.append(ProductionAnomaly.liability_type == liability_type)
    if status is not None:
        filters.append(ProductionAnomaly.status == status)

    if filters:
        stmt = stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

    # 总数
    total = (await query_db.execute(count_stmt)).scalar() or 0

    # 分页 + 排序
    stmt = stmt.order_by(ProductionAnomaly.created_at.desc())
    stmt = stmt.offset((page_num - 1) * page_size).limit(page_size)

    rows = (await query_db.execute(stmt)).scalars().all()

    # 转换为响应模型
    row_list = [
        ProductionAnomalyBriefResponse.model_validate(r).model_dump()
        for r in rows
    ]

    return ResponseUtil.success(
        rows=row_list,
        dict_content={'total': total, 'page_num': page_num, 'page_size': page_size},
    )


# ── GET /{id} — 生产异常详情 ─────────────────────────────────────────────────

@production_anomaly_controller.get(
    '/{anomaly_id}',
    summary='生产异常详情',
    response_model=DataResponseModel,
)
async def get_production_anomaly_detail(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    anomaly_id: int = Path(..., description='生产异常ID'),
):
    """获取生产异常详情，包含补发记录、扣款记录和协商记录。"""
    anomaly = await query_db.scalar(
        select(ProductionAnomaly).where(ProductionAnomaly.id == anomaly_id)
    )
    if not anomaly:
        return ResponseUtil.failure(msg=f'生产异常不存在: id={anomaly_id}')

    # 查询补发记录
    re_shipments_result = await query_db.execute(
        select(ReShipment)
        .where(ReShipment.production_anomaly_id == anomaly_id)
        .order_by(ReShipment.id.asc())
    )
    re_shipments = re_shipments_result.scalars().all()

    # 查询扣款记录
    deductions_result = await query_db.execute(
        select(Deduction)
        .where(Deduction.production_anomaly_id == anomaly_id)
        .order_by(Deduction.id.asc())
    )
    deductions = deductions_result.scalars().all()

    # 查询协商记录
    negotiations_result = await query_db.execute(
        select(NegotiationRecord)
        .where(NegotiationRecord.production_anomaly_id == anomaly_id)
        .order_by(NegotiationRecord.id.asc())
    )
    negotiations = negotiations_result.scalars().all()

    # 构建响应
    detail = ProductionAnomalyResponse.model_validate(anomaly)
    detail.re_shipments = [
        ReShipmentResponse.model_validate(item)
        for item in re_shipments
    ]
    detail.deductions = [
        DeductionResponse.model_validate(item)
        for item in deductions
    ]
    detail.negotiations = [
        NegotiationRecordResponse.model_validate(item)
        for item in negotiations
    ]

    return ResponseUtil.success(data=detail.model_dump())


# ── PUT /{id}/liability — 判定责任方 ─────────────────────────────────────────

@production_anomaly_controller.put(
    '/{anomaly_id}/liability',
    summary='判定责任方',
    response_model=DataResponseModel,
)
async def set_liability(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data: LiabilitySetRequest,
    anomaly_id: int = Path(..., description='生产异常ID'),
):
    """
    判定生产异常的责任方。
    material_supplier_fault：自动创建材料补发请求。
    processor_fault：由业务人员后续选择补发或扣款。
    """
    try:
        result = await ProductionAnomalyService.set_liability(
            db=query_db,
            anomaly_id=anomaly_id,
            liability_type=data.liability_type,
            operator_id=current_user.user.user_id if current_user.user else 0,
        )
        return ResponseUtil.success(
            data=result,
            msg='责任判定成功',
        )
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))


# ── POST /{id}/re-shipment — 创建补发请求 ────────────────────────────────────

@production_anomaly_controller.post(
    '/{anomaly_id}/re-shipment',
    summary='创建补发请求',
    response_model=DataResponseModel,
)
async def create_re_shipment(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data: ReShipmentCreateRequest,
    anomaly_id: int = Path(..., description='生产异常ID'),
):
    """创建补发请求（材料补发或零件补发）。"""
    try:
        re_shipment_id = await ProductionAnomalyService.create_re_shipment(
            db=query_db,
            anomaly_id=anomaly_id,
            shipment_type=data.shipment_type,
            responsible_party=data.responsible_party,
            description=data.description,
            created_by=current_user.user.user_id if current_user.user else 0,
        )
        return ResponseUtil.success(
            data={'re_shipment_id': re_shipment_id},
            msg='补发请求创建成功',
        )
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))


# ── POST /{id}/deduction — 创建扣款记录 ──────────────────────────────────────

@production_anomaly_controller.post(
    '/{anomaly_id}/re-shipment/{re_shipment_id}/confirm-shipment',
    summary='确认补发发货',
    response_model=DataResponseModel,
)
async def confirm_shipment(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data: ReShipmentConfirmRequest,
    anomaly_id: int = Path(..., description='生产异常ID'),
    re_shipment_id: int = Path(..., description='补发记录ID'),
):
    """
    确认补发已发货。
    将 ReShipment 状态更新为 shipped，并自动创建虚拟入库记录（Requirement 13.1）。
    """
    try:
        result = await ProductionAnomalyService.confirm_shipment(
            db=query_db,
            re_shipment_id=re_shipment_id,
            order_id=data.order_id,
            part_id=data.part_id,
            quantity=data.quantity,
            unit_price=data.unit_price,
            anomaly_reason=data.anomaly_reason,
            operator_id=current_user.user.user_id if current_user.user else 0,
        )
        return ResponseUtil.success(
            data=result,
            msg='补发发货确认成功，已自动创建虚拟入库记录',
        )
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))


# ── POST /{id}/deduction — 创建扣款记录 ──────────────────────────────────────

@production_anomaly_controller.post(
    '/{anomaly_id}/deduction',
    summary='创建扣款记录',
    response_model=DataResponseModel,
)
async def create_deduction(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data: DeductionCreateRequest,
    anomaly_id: int = Path(..., description='生产异常ID'),
):
    """创建扣款记录（通常用于加工方责任场景）。"""
    try:
        deduction_id = await ProductionAnomalyService.create_deduction(
            db=query_db,
            anomaly_id=anomaly_id,
            amount=data.amount,
            reason=data.reason,
            created_by=current_user.user.user_id if current_user.user else 0,
        )
        return ResponseUtil.success(
            data={'deduction_id': deduction_id},
            msg='扣款记录创建成功',
        )
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))


# ── POST /{id}/negotiation — 记录协商过程 ────────────────────────────────────

@production_anomaly_controller.post(
    '/{anomaly_id}/negotiation',
    summary='记录协商过程',
    response_model=DataResponseModel,
)
async def record_negotiation(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data: NegotiationCreateRequest,
    anomaly_id: int = Path(..., description='生产异常ID'),
):
    """记录一次协商过程（时间、参与方、结果）。"""
    try:
        negotiation_id = await ProductionAnomalyService.record_negotiation(
            db=query_db,
            anomaly_id=anomaly_id,
            time=data.negotiation_time,
            participants=data.participants,
            result=data.result,
            created_by=current_user.user.user_id if current_user.user else 0,
        )
        return ResponseUtil.success(
            data={'negotiation_id': negotiation_id},
            msg='协商记录创建成功',
        )
    except ServiceException as e:
        return ResponseUtil.failure(msg=str(e.message) if hasattr(e, 'message') else str(e))
