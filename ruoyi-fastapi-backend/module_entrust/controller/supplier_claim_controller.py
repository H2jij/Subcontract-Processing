"""
对账系统 — 供应商对账 Controller
=====================================

供应商视角的对账操作接口：
- 查看对账单列表（按当前用户关联的 supplier_id 过滤）
- 查看对账单明细
- 确认对账单
- 提出争议
- 提交供应商账单

Requirements: 2.2, 2.3, 2.4, 3.1
"""
from typing import Annotated

from fastapi import Path, Query
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel, ResponseBaseModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_entrust.entity.do.entrust_do import EntrustSupplier
from module_entrust.entity.do.reconciliation_do import (
    ReconciliationLineItem,
    ReconciliationStatement,
    SupplierClaim,
)
from module_entrust.entity.vo.reconciliation_vo import (
    ConfirmationHistoryResponse,
    LineItemResponse,
    StatementBriefResponse,
    StatementDetailResponse,
    SupplierClaimResponse,
    SupplierClaimSubmitRequest,
    SupplierDisputeRequest,
)
from module_entrust.service.anomaly_service import AnomalyService
from module_entrust.service.supplier_claim_service import SupplierClaimService
from utils.response_util import ResponseUtil

supplier_claim_controller = APIRouterPro(
    prefix='/entrust/supplier-claim',
    order_num=12,
    tags=['供应商对账'],
    dependencies=[PreAuthDependency()],
)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

async def _get_supplier_id_for_user(
    db: AsyncSession, user_id: int
) -> int | None:
    """根据当前登录用户的 user_id 查询关联的供应商 ID"""
    stmt = select(EntrustSupplier.id).where(EntrustSupplier.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# 供应商查看对账单列表
# ---------------------------------------------------------------------------

@supplier_claim_controller.get(
    '/statements',
    summary='供应商查看对账单列表',
    response_model=PageResponseModel,
)
async def get_supplier_statements(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    status: str = Query(default=None, description='状态: pending/confirmed/disputed/timeout/paid'),
    confirmation_status: str = Query(default=None, description='确认状态: pending/confirmed/disputed'),
    page_num: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
):
    """供应商查看自己的对账单列表，按当前用户关联的 supplier_id 过滤"""
    user_id = current_user.user.user_id if current_user.user else 0
    supplier_id = await _get_supplier_id_for_user(query_db, user_id)
    if not supplier_id:
        return ResponseUtil.failure(msg='当前用户未关联供应商')

    # 构建查询
    query = select(ReconciliationStatement).where(
        ReconciliationStatement.supplier_id == supplier_id
    )
    if status:
        query = query.where(ReconciliationStatement.status == status)
    if confirmation_status:
        query = query.where(ReconciliationStatement.confirmation_status == confirmation_status)

    # 计算总数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await query_db.execute(count_query)).scalar() or 0

    # 分页
    query = query.order_by(ReconciliationStatement.created_at.desc())
    query = query.offset((page_num - 1) * page_size).limit(page_size)
    rows = (await query_db.execute(query)).scalars().all()

    # 转换为响应模型
    result_rows = []
    for row in rows:
        result_rows.append(StatementBriefResponse.model_validate(row).model_dump())

    return ResponseUtil.success(
        rows=result_rows,
        dict_content={'total': total, 'page_num': page_num, 'page_size': page_size},
    )


# ---------------------------------------------------------------------------
# 供应商查看对账单明细
# ---------------------------------------------------------------------------

@supplier_claim_controller.get(
    '/statements/{statement_id}',
    summary='供应商查看对账单明细',
    response_model=DataResponseModel,
)
async def get_supplier_statement_detail(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    statement_id: int = Path(..., description='对账单ID'),
):
    """供应商查看对账单明细，包含所有行项及汇总金额"""
    user_id = current_user.user.user_id if current_user.user else 0
    supplier_id = await _get_supplier_id_for_user(query_db, user_id)
    if not supplier_id:
        return ResponseUtil.failure(msg='当前用户未关联供应商')

    # 查询对账单
    stmt = await query_db.scalar(
        select(ReconciliationStatement).where(
            ReconciliationStatement.id == statement_id,
            ReconciliationStatement.supplier_id == supplier_id,
        )
    )
    if not stmt:
        return ResponseUtil.failure(msg='对账单不存在或无权访问')

    # 查询行项
    line_items_query = (
        select(ReconciliationLineItem)
        .where(ReconciliationLineItem.statement_id == statement_id)
        .order_by(ReconciliationLineItem.id.asc())
    )
    line_items = (await query_db.execute(line_items_query)).scalars().all()

    # 构建响应
    detail = StatementDetailResponse.model_validate(stmt)
    detail.line_items = [LineItemResponse.model_validate(item) for item in line_items]

    return ResponseUtil.success(data=detail.model_dump())


# ---------------------------------------------------------------------------
# 供应商确认对账单
# ---------------------------------------------------------------------------

@supplier_claim_controller.post(
    '/statements/{statement_id}/confirm',
    summary='供应商确认对账单',
    response_model=DataResponseModel,
)
async def confirm_statement(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    statement_id: int = Path(..., description='对账单ID'),
):
    """
    供应商主动确认对账单。
    确认操作必须由供应商主动点击触发，禁止自动确认。
    """
    user_id = current_user.user.user_id if current_user.user else 0
    supplier_id = await _get_supplier_id_for_user(query_db, user_id)
    if not supplier_id:
        return ResponseUtil.failure(msg='当前用户未关联供应商')

    # 验证对账单归属
    stmt = await query_db.scalar(
        select(ReconciliationStatement).where(
            ReconciliationStatement.id == statement_id,
            ReconciliationStatement.supplier_id == supplier_id,
        )
    )
    if not stmt:
        return ResponseUtil.failure(msg='对账单不存在或无权操作')

    try:
        result = await SupplierClaimService.confirm_statement(
            db=query_db,
            statement_id=statement_id,
            operator_id=user_id,
        )
    except ValueError as e:
        return ResponseUtil.failure(msg=str(e))

    if not result.get('success'):
        return ResponseUtil.failure(msg=result.get('message', '确认失败'))

    return ResponseUtil.success(data=result, msg='对账单已确认')


# ---------------------------------------------------------------------------
# 供应商提出争议
# ---------------------------------------------------------------------------

@supplier_claim_controller.post(
    '/statements/{statement_id}/dispute',
    summary='供应商提出争议',
    response_model=DataResponseModel,
)
async def dispute_statement(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    statement_id: int = Path(..., description='对账单ID'),
    data: SupplierDisputeRequest = None,
):
    """
    供应商对对账单提出争议，需填写争议说明。
    """
    user_id = current_user.user.user_id if current_user.user else 0
    supplier_id = await _get_supplier_id_for_user(query_db, user_id)
    if not supplier_id:
        return ResponseUtil.failure(msg='当前用户未关联供应商')

    # 验证对账单归属
    stmt = await query_db.scalar(
        select(ReconciliationStatement).where(
            ReconciliationStatement.id == statement_id,
            ReconciliationStatement.supplier_id == supplier_id,
        )
    )
    if not stmt:
        return ResponseUtil.failure(msg='对账单不存在或无权操作')

    if not data or not data.dispute_reason:
        return ResponseUtil.failure(msg='争议说明不能为空')

    try:
        result = await SupplierClaimService.dispute_statement(
            db=query_db,
            statement_id=statement_id,
            operator_id=user_id,
            reason=data.dispute_reason,
        )
    except ValueError as e:
        return ResponseUtil.failure(msg=str(e))

    if not result.get('success'):
        return ResponseUtil.failure(msg=result.get('message', '提交争议失败'))

    return ResponseUtil.success(data=result, msg='争议已提交')


# ---------------------------------------------------------------------------
# 供应商提交账单
# ---------------------------------------------------------------------------

@supplier_claim_controller.post(
    '/claims',
    summary='供应商提交账单',
    response_model=DataResponseModel,
)
async def submit_supplier_claim(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data: SupplierClaimSubmitRequest,
):
    """
    供应商提交账单明细，系统将自动进行异常检测。
    提交后调用 AnomalyService.detect_anomalies 进行比对。
    """
    user_id = current_user.user.user_id if current_user.user else 0
    supplier_id = await _get_supplier_id_for_user(query_db, user_id)
    if not supplier_id:
        return ResponseUtil.failure(msg='当前用户未关联供应商')

    # 验证对账单归属
    stmt = await query_db.scalar(
        select(ReconciliationStatement).where(
            ReconciliationStatement.id == data.statement_id,
            ReconciliationStatement.supplier_id == supplier_id,
        )
    )
    if not stmt:
        return ResponseUtil.failure(msg='对账单不存在或无权操作')

    # 将 claim_items 转为 JSON 格式存储
    claim_data_json = [item.model_dump() for item in data.claim_items]

    # 创建 SupplierClaim 记录
    claim = SupplierClaim(
        statement_id=data.statement_id,
        supplier_id=supplier_id,
        claim_data=claim_data_json,
        submitted_by=user_id,
    )
    query_db.add(claim)
    await query_db.flush()

    # 调用异常检测服务
    anomaly_ids = []
    try:
        anomaly_ids = await AnomalyService.detect_anomalies(
            db=query_db,
            statement_id=data.statement_id,
            claim_data=claim_data_json,
            claim_id=claim.id,
            operator_id=user_id,
        )
    except Exception as e:
        logger.warning(
            f'[SupplierClaimController] 异常检测失败 statement_id={data.statement_id}: {e}'
        )
        # 异常检测失败不阻断账单提交，但记录日志

    await query_db.commit()

    response_data = {
        'claim_id': claim.id,
        'statement_id': data.statement_id,
        'anomaly_count': len(anomaly_ids),
        'anomaly_ids': anomaly_ids,
    }

    logger.info(
        f'[SupplierClaimController] 供应商提交账单成功 claim_id={claim.id} '
        f'statement_id={data.statement_id} anomaly_count={len(anomaly_ids)}'
    )

    return ResponseUtil.success(data=response_data, msg='账单提交成功')
