"""
委外加工 — 询价/报价 Service
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from module_entrust.entity.do.entrust_do import (
    EntrustOutsourceRequest, EntrustInvitation, EntrustQuotation,
    EntrustOutsourceOrder, EntrustSupplier,
)
from module_entrust.entity.vo.entrust_vo import (
    InquiryCreate, InquirySend, InquiryQuery, InquiryResponse,
    QuoteSubmit, QuoteResponse, QuoteDraftSave, QuoteDecline,
    OutsourceOrderResponse, OrderStatusTransition,
)


class InquiryService:
    """询价管理服务"""

    @staticmethod
    async def create_inquiry(db: AsyncSession, data: InquiryCreate, user_id: int):
        inquiry = EntrustOutsourceRequest(
            project_id=data.project_id,
            title=data.title,
            scope_json=data.scope_json,
            deadline=data.deadline,
            status='draft',
            created_by=user_id,
            customer_name=data.customer_name,
            customer_contact=data.customer_contact,
            customer_phone=data.customer_phone,
            order_no=data.order_no,
            inquiry_date=data.inquiry_date,
            delivery_date=data.delivery_date,
        )
        db.add(inquiry)
        await db.flush()
        await db.commit()
        await db.refresh(inquiry)
        return InquiryResponse.model_validate(inquiry)

    @staticmethod
    async def get_inquiry_list(db: AsyncSession, query: InquiryQuery):
        stmt = select(EntrustOutsourceRequest).where(EntrustOutsourceRequest.id > 0)
        if query.project_id:
            stmt = stmt.where(EntrustOutsourceRequest.project_id == query.project_id)
        if query.status:
            stmt = stmt.where(EntrustOutsourceRequest.status == query.status)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar()

        offset = (query.page_num - 1) * query.page_size
        stmt = stmt.order_by(EntrustOutsourceRequest.created_at.desc()).offset(offset).limit(query.page_size)
        result = (await db.execute(stmt)).scalars().all()

        rows = [InquiryResponse.model_validate(r) for r in result]
        return rows, total

    @staticmethod
    async def get_inquiry_detail(db: AsyncSession, inquiry_id: int):
        stmt = select(EntrustOutsourceRequest).where(EntrustOutsourceRequest.id == inquiry_id)
        result = (await db.execute(stmt)).scalar_one_or_none()
        if not result:
            return None
        return InquiryResponse.model_validate(result)

    @staticmethod
    async def delete_inquiry(db: AsyncSession, inquiry_id: int):
        """删除询价单"""
        stmt = select(EntrustOutsourceRequest).where(EntrustOutsourceRequest.id == inquiry_id)
        inquiry = (await db.execute(stmt)).scalar_one_or_none()
        if not inquiry:
            return None
        await db.delete(inquiry)
        await db.commit()
        return True

    @staticmethod
    async def send_inquiry(db: AsyncSession, inquiry_id: int, data: InquirySend):
        """发送询价邀请给多个加工方"""
        stmt = select(EntrustOutsourceRequest).where(EntrustOutsourceRequest.id == inquiry_id)
        inquiry = (await db.execute(stmt)).scalar_one_or_none()
        if not inquiry:
            return None

        now = datetime.now()
        for sid in data.supplier_ids:
            inv = EntrustInvitation(
                request_id=inquiry_id,
                supplier_id=sid,
                status='sent',
                sent_at=now,
            )
            db.add(inv)

        inquiry.status = 'sent'
        await db.flush()
        await db.commit()
        return True

    @staticmethod
    async def get_invitations(db: AsyncSession, inquiry_id: int):
        """获取询价单的邀请列表（含供应商名称、报价信息、拒绝备注）"""
        stmt = (
            select(EntrustInvitation, EntrustSupplier.name, EntrustSupplier.contact_name, EntrustSupplier.contact_phone)
            .join(EntrustSupplier, EntrustInvitation.supplier_id == EntrustSupplier.id)
            .where(EntrustInvitation.request_id == inquiry_id)
        )
        result = (await db.execute(stmt)).all()

        items = []
        for inv, supplier_name, contact_name, contact_phone in result:
            item = {
                'id': inv.id,
                'supplier_id': inv.supplier_id,
                'supplier_name': supplier_name,
                'supplier_contact': contact_name,
                'supplier_phone': contact_phone,
                'status': inv.status,
                'sent_at': inv.sent_at.isoformat() if inv.sent_at else None,
                'quoted_at': inv.quoted_at.isoformat() if inv.quoted_at else None,
                'decline_remark': inv.decline_remark,
                'quotation': None,
                'draft_quote_json': inv.draft_quote_json,
            }
            if inv.status == 'quoted':
                q_stmt = select(EntrustQuotation).where(EntrustQuotation.invitation_id == inv.id)
                q = (await db.execute(q_stmt)).scalar_one_or_none()
                if q:
                    item['quotation'] = QuoteResponse.model_validate(q).model_dump()
            items.append(item)
        return items

    @staticmethod
    async def save_draft_quote(db: AsyncSession, invitation_id: int, data: QuoteDraftSave):
        """加工方保存报价草稿（可反复修改）"""
        stmt = select(EntrustInvitation).where(EntrustInvitation.id == invitation_id)
        invitation = (await db.execute(stmt)).scalar_one_or_none()
        if not invitation:
            return None
        invitation.draft_quote_json = data.draft_quote_json
        if invitation.status == 'sent':
            invitation.status = 'draft_quoted'
        await db.flush()
        await db.commit()
        return True

    @staticmethod
    async def submit_quote(db: AsyncSession, invitation_id: int, data: QuoteSubmit, user_id: int):
        """加工方提交报价"""
        stmt = select(EntrustInvitation).where(EntrustInvitation.id == invitation_id)
        invitation = (await db.execute(stmt)).scalar_one_or_none()
        if not invitation:
            return None

        now = datetime.now()
        quote = EntrustQuotation(
            invitation_id=invitation_id,
            unit_price=data.unit_price,
            lead_time_days=data.lead_time_days,
            note=data.note,
            lines_json=data.lines,
            submitted_by=user_id,
            submitted_at=now,
        )
        db.add(quote)

        invitation.status = 'quoted'
        invitation.quoted_at = now

        # 同步更新询价单状态为 quoted
        req_stmt = select(EntrustOutsourceRequest).where(EntrustOutsourceRequest.id == invitation.request_id)
        inquiry = (await db.execute(req_stmt)).scalar_one_or_none()
        if inquiry and inquiry.status == 'sent':
            inquiry.status = 'quoted'

        await db.flush()
        await db.commit()
        await db.refresh(quote)
        return QuoteResponse.model_validate(quote)

    @staticmethod
    async def decline_invitation(db: AsyncSession, invitation_id: int, data: QuoteDecline):
        """加工方拒绝询价"""
        stmt = select(EntrustInvitation).where(EntrustInvitation.id == invitation_id)
        invitation = (await db.execute(stmt)).scalar_one_or_none()
        if not invitation:
            return None
        invitation.status = 'declined'
        invitation.decline_remark = data.decline_remark
        invitation.quoted_at = datetime.now()
        await db.flush()
        await db.commit()
        return True

    @staticmethod
    async def award_inquiry(db: AsyncSession, inquiry_id: int, quotation_id: int, user_id: int):
        """选标：将询价单授予某个报价"""
        inquiry_stmt = select(EntrustOutsourceRequest).where(EntrustOutsourceRequest.id == inquiry_id)
        inquiry = (await db.execute(inquiry_stmt)).scalar_one_or_none()
        if not inquiry:
            return None

        quote_stmt = select(EntrustQuotation).where(EntrustQuotation.id == quotation_id)
        quote = (await db.execute(quote_stmt)).scalar_one_or_none()
        if not quote:
            return None

        inv_stmt = select(EntrustInvitation).where(EntrustInvitation.id == quote.invitation_id)
        invitation = (await db.execute(inv_stmt)).scalar_one_or_none()

        # 生成委外工单
        import time
        order_no = f'EO-{int(time.time())}-{inquiry_id:04d}'

        order = EntrustOutsourceOrder(
            request_id=inquiry_id,
            quotation_id=quotation_id,
            supplier_id=invitation.supplier_id if invitation else None,
            project_id=inquiry.project_id,
            order_no=order_no,
            unit_price=quote.unit_price,
            lead_time_days=quote.lead_time_days,
            status='awarded',
            created_by=user_id,
        )
        db.add(order)

        inquiry.status = 'awarded'
        inquiry.winning_quote_id = quotation_id
        inquiry.closed_at = datetime.now()
        await db.flush()
        await db.commit()
        await db.refresh(order)
        return OutsourceOrderResponse.model_validate(order)
