"""
委外加工 — 框架合同发送任务 Controller
"""
from typing import Annotated, Optional

from fastapi import Path, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import io
from datetime import datetime

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from module_admin.entity.vo.user_vo import CurrentUserModel
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel, ResponseBaseModel
from module_entrust.service.contract_task_service import ContractTaskService
from module_entrust.entity.do.entrust_do import EntrustSupplier, EntrustContractRecord
from utils.response_util import ResponseUtil

contract_task_controller = APIRouterPro(
    prefix='/entrust/contract-tasks',
    order_num=15,
    tags=['委外管理-合同分发'],
    dependencies=[PreAuthDependency()],
)


# ── 请求模型 ──────────────────────────────────────────────────────────────────

class SendTaskRequest(BaseModel):
    recipient_email: Optional[str] = Field(default=None, description='收件邮箱（空则从档案获取）')
    extra_values: Optional[dict[str, str]] = Field(default=None, description='额外占位符覆盖值')


class DeferTaskRequest(BaseModel):
    deferred_until: datetime = Field(..., description='延迟到指定时间发送')
    note: Optional[str] = None


class RejectTaskRequest(BaseModel):
    note: Optional[str] = Field(default='', description='拒绝原因')


# ── 接口 ──────────────────────────────────────────────────────────────────────

@contract_task_controller.get(
    '/list',
    summary='获取合同发送任务列表',
    response_model=PageResponseModel,
)
async def get_task_list(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    status: str = Query(default=None, description='状态筛选：pending/sent/deferred/rejected'),
    supplier_type: str = Query(default=None, description='供应商类型：processor/material'),
    page_num: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    rows, total = await ContractTaskService.get_task_list(
        query_db, status=status, supplier_type=supplier_type,
        page_num=page_num, page_size=page_size,
    )
    return ResponseUtil.success(rows=rows, dict_content={'total': total})


@contract_task_controller.post(
    '/{task_id}/send',
    summary='发送框架合同',
    response_model=DataResponseModel,
)
async def send_contract(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    task_id: int = Path(..., description='任务ID'),
    data: SendTaskRequest = None,
):
    req = data or SendTaskRequest()
    result = await ContractTaskService.send_contract(
        db=query_db,
        task_id=task_id,
        recipient_email=req.recipient_email,
        extra_values=req.extra_values,
        created_by=current_user.user.user_id if current_user.user else 0,
    )
    if not result['success']:
        return ResponseUtil.failure(msg=result['message'])
    return ResponseUtil.success(
        data={'smtp_message_id': result.get('smtp_message_id'), 'record_id': result.get('record_id')},
        msg='发送成功',
    )


@contract_task_controller.post(
    '/{task_id}/defer',
    summary='延迟发送',
    response_model=ResponseBaseModel,
)
async def defer_task(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    task_id: int = Path(..., description='任务ID'),
    data: DeferTaskRequest = None,
):
    ok = await ContractTaskService.defer_task(query_db, task_id, data.deferred_until, data.note or '')
    if not ok:
        return ResponseUtil.failure(msg='任务不存在')
    return ResponseUtil.success(msg='已标记为延迟发送')


@contract_task_controller.post(
    '/{task_id}/reject',
    summary='拒绝发送',
    response_model=ResponseBaseModel,
)
async def reject_task(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    task_id: int = Path(..., description='任务ID'),
    data: RejectTaskRequest = None,
):
    req = data or RejectTaskRequest()
    ok = await ContractTaskService.reject_task(query_db, task_id, req.note or '')
    if not ok:
        return ResponseUtil.failure(msg='任务不存在')
    return ResponseUtil.success(msg='已拒绝发送')


@contract_task_controller.post(
    '/{task_id}/reset',
    summary='重置为待发送',
    response_model=ResponseBaseModel,
)
async def reset_task(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    task_id: int = Path(..., description='任务ID'),
):
    ok = await ContractTaskService.reset_to_pending(query_db, task_id)
    if not ok:
        return ResponseUtil.failure(msg='任务不存在')
    return ResponseUtil.success(msg='已重置为待发送')


@contract_task_controller.get(
    '/{task_id}/records',
    summary='获取该供应商的发送历史',
    response_model=DataResponseModel,
)
async def get_send_records(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    task_id: int = Path(..., description='任务ID'),
):
    from module_entrust.entity.do.entrust_do import EntrustContractTask
    task = await query_db.scalar(select(EntrustContractTask).where(EntrustContractTask.id == task_id))
    if not task:
        return ResponseUtil.failure(msg='任务不存在')

    records = (await query_db.execute(
        select(EntrustContractRecord)
        .where(EntrustContractRecord.supplier_id == task.supplier_id)
        .order_by(EntrustContractRecord.sent_at.desc())
        .limit(50)
    )).scalars().all()

    return ResponseUtil.success(data=[
        {
            "id": r.id,
            "status": r.status,
            "recipient_email": r.recipient_email,
            "smtp_message_id": r.smtp_message_id,
            "error_message": r.error_message,
            "sent_at": r.sent_at.isoformat() if r.sent_at else None,
        }
        for r in records
    ])


@contract_task_controller.get(
    '/{task_id}/preview',
    summary='预览/下载合同 DOCX',
)
async def preview_contract(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    task_id: int = Path(..., description='任务ID'),
):
    from module_entrust.entity.do.entrust_do import EntrustContractTask
    from module_entrust.service.contract_service import (
        _pick_template, _get_party_a_config, DocxFiller
    )
    from urllib.parse import quote

    task = await query_db.scalar(select(EntrustContractTask).where(EntrustContractTask.id == task_id))
    if not task:
        return ResponseUtil.failure(msg='任务不存在')

    supplier = await query_db.scalar(select(EntrustSupplier).where(EntrustSupplier.id == task.supplier_id))
    if not supplier:
        return ResponseUtil.failure(msg='供应商不存在')

    from datetime import date
    today = date.today()
    party_a = await _get_party_a_config(query_db)

    values = {
        "乙方名称": supplier.name or "",
        "乙方地址": f"{supplier.province or ''}{supplier.city or ''}{supplier.address or ''}".strip() or "【待填写】",
        "乙方法定代表人": supplier.legal_rep or supplier.contact_name or "【待填写】",
        "乙方联系电话": supplier.contact_phone or "【待填写】",
        "统一社会信用代码": supplier.credit_code or "【待填写】",
        "合同期限_起_年": str(today.year),
        "合同期限_起_月": f"{today.month:02d}",
        "合同期限_起_日": f"{today.day:02d}",
        "合同期限_止_年": "【待确认】",
        "合同期限_止_月": "【待确认】",
        "合同期限_止_日": "【待确认】",
        "签订日期_年": str(today.year),
        "签订日期_月": f"{today.month:02d}",
        "签订日期_日": f"{today.day:02d}",
        "合同额度": supplier.contract_amount and f"¥{supplier.contract_amount:,.2f}" or "【待填写】",
        "乙方印章": "【待盖章】",
        "乙方签字": "【待签字】",
        "乙方签字日期_年": "", "乙方签字日期_月": "", "乙方签字日期_日": "",
    }
    values.update(party_a)

    template_path = _pick_template(supplier.category)
    filler = DocxFiller(str(template_path))
    docx_bytes = filler.fill(values)
    filename = f"年度采购框架合同_{supplier.name}.docx"
    encoded_name = quote(filename, safe='')

    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        headers={'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_name}"},
    )
