"""
委外加工 — 框架合同发送任务 Service
=============================================
管理每个供应商的合同发送状态：
  - 新建供应商时自动创建 pending 任务
  - 支持延迟发送、拒绝发送、重新发送
  - 发送时更新状态并调用 ContractService
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from loguru import logger
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from module_entrust.entity.do.entrust_do import (
    EntrustContractTask, EntrustSupplier, EntrustContractRecord,
)


class ContractTaskService:

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    @staticmethod
    async def get_task_list(
        db: AsyncSession,
        status: Optional[str] = None,
        supplier_type: Optional[str] = None,
        page_num: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """获取合同任务列表，含供应商信息和最近发送记录。"""
        stmt = (
            select(EntrustContractTask, EntrustSupplier)
            .join(EntrustSupplier, EntrustContractTask.supplier_id == EntrustSupplier.id)
        )
        if status:
            stmt = stmt.where(EntrustContractTask.status == status)
        if supplier_type:
            stmt = stmt.where(EntrustSupplier.supplier_type == supplier_type)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar()

        offset = (page_num - 1) * page_size
        stmt = stmt.order_by(
            # pending 排最前（未发送高亮）
            EntrustContractTask.status.asc(),
            EntrustContractTask.updated_at.desc(),
        ).offset(offset).limit(page_size)

        rows = (await db.execute(stmt)).all()

        results = []
        for task, supplier in rows:
            # 查最近发送记录（最多3条）
            rec_stmt = (
                select(EntrustContractRecord)
                .where(EntrustContractRecord.supplier_id == task.supplier_id)
                .order_by(EntrustContractRecord.sent_at.desc())
                .limit(5)
            )
            recent_records = (await db.execute(rec_stmt)).scalars().all()

            results.append({
                "id": task.id,
                "supplier_id": task.supplier_id,
                "supplier_name": supplier.name,
                "supplier_type": supplier.supplier_type,
                "contact_email": supplier.contact_email,
                "legal_rep": supplier.legal_rep,
                "credit_code": supplier.credit_code,
                "status": task.status,
                "send_count": task.send_count,
                "last_sent_at": task.last_sent_at.isoformat() if task.last_sent_at else None,
                "deferred_until": task.deferred_until.isoformat() if task.deferred_until else None,
                "note": task.note,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "recent_records": [
                    {
                        "id": r.id,
                        "status": r.status,
                        "recipient_email": r.recipient_email,
                        "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                        "error_message": r.error_message,
                    }
                    for r in recent_records
                ],
            })

        return results, total

    @staticmethod
    async def get_task_by_supplier(db: AsyncSession, supplier_id: int) -> Optional[dict]:
        """获取指定供应商的合同任务。"""
        stmt = (
            select(EntrustContractTask, EntrustSupplier)
            .join(EntrustSupplier, EntrustContractTask.supplier_id == EntrustSupplier.id)
            .where(EntrustContractTask.supplier_id == supplier_id)
        )
        row = (await db.execute(stmt)).one_or_none()
        if not row:
            return None
        task, supplier = row
        return {"task": task, "supplier": supplier}

    # ------------------------------------------------------------------
    # 创建
    # ------------------------------------------------------------------

    @staticmethod
    async def ensure_task(db: AsyncSession, supplier_id: int, created_by: int = 0) -> EntrustContractTask:
        """确保供应商有合同任务（新建或返回已有）。"""
        stmt = select(EntrustContractTask).where(EntrustContractTask.supplier_id == supplier_id)
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            return existing

        task = EntrustContractTask(
            supplier_id=supplier_id,
            status="pending",
            send_count=0,
            created_by=created_by,
        )
        db.add(task)
        await db.flush()
        logger.info(f"[ContractTask] 创建合同任务 supplier_id={supplier_id}")
        return task

    # ------------------------------------------------------------------
    # 状态变更
    # ------------------------------------------------------------------

    @staticmethod
    async def reject_task(db: AsyncSession, task_id: int, note: str = "") -> bool:
        """拒绝发送（标记为 rejected）。"""
        task = await db.scalar(select(EntrustContractTask).where(EntrustContractTask.id == task_id))
        if not task:
            return False
        task.status = "rejected"
        task.note = note
        await db.flush()
        await db.commit()
        return True

    @staticmethod
    async def defer_task(db: AsyncSession, task_id: int, deferred_until: datetime, note: str = "") -> bool:
        """延迟发送。"""
        task = await db.scalar(select(EntrustContractTask).where(EntrustContractTask.id == task_id))
        if not task:
            return False
        task.status = "deferred"
        task.deferred_until = deferred_until
        task.note = note
        await db.flush()
        await db.commit()
        return True

    @staticmethod
    async def reset_to_pending(db: AsyncSession, task_id: int) -> bool:
        """重置为待发送。"""
        task = await db.scalar(select(EntrustContractTask).where(EntrustContractTask.id == task_id))
        if not task:
            return False
        task.status = "pending"
        task.note = None
        task.deferred_until = None
        await db.flush()
        await db.commit()
        return True

    # ------------------------------------------------------------------
    # 发送合同（调用 ContractService）
    # ------------------------------------------------------------------

    @staticmethod
    async def send_contract(
        db: AsyncSession,
        task_id: int,
        recipient_email: Optional[str] = None,
        extra_values: Optional[dict] = None,
        created_by: int = 0,
    ) -> dict:
        """
        发送框架合同，更新任务状态。
        """
        from module_entrust.service.contract_service import ContractService

        task = await db.scalar(select(EntrustContractTask).where(EntrustContractTask.id == task_id))
        if not task:
            return {"success": False, "message": "任务不存在"}

        supplier = await db.scalar(select(EntrustSupplier).where(EntrustSupplier.id == task.supplier_id))
        if not supplier:
            return {"success": False, "message": "供应商不存在"}

        email = recipient_email or supplier.contact_email
        if not email:
            return {"success": False, "message": "供应商邮箱未配置，请先在供应商档案中填写联系邮箱"}

        # 直接发送（不依赖询价单，用 direct 模式）
        result = await ContractService.send_contract_direct(
            db=db,
            supplier=supplier,
            recipient_email=email,
            extra_values=extra_values,
            created_by=created_by,
        )

        # 更新任务状态
        now = datetime.now()
        if result["success"]:
            task.status = "sent"
            task.last_sent_at = now
            task.send_count = (task.send_count or 0) + 1
        task.updated_at = now
        await db.flush()
        await db.commit()

        return result
