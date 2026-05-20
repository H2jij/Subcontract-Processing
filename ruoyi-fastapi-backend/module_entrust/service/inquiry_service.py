"""
委外加工 — 询价/报价 Service
"""
import logging
from datetime import datetime
from decimal import Decimal

logger = logging.getLogger(__name__)

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from module_entrust.entity.do.entrust_do import (
    EntrustOutsourceRequest, EntrustInvitation, EntrustQuotation,
    EntrustOutsourceOrder, EntrustSupplier, EntrustProject, EntrustDrawing,
)
from module_entrust.entity.vo.entrust_vo import (
    InquiryCreate, InquirySend, InquiryQuery, InquiryResponse,
    QuoteSubmit, QuoteResponse, QuoteDraftSave, QuoteDecline,
    OutsourceOrderResponse, OrderStatusTransition,
    InquiryGroupedResponse, GroupedSupplierQuote, GroupedInquiryBrief,
    DrawingBrief,
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
            material_preparation=data.material_preparation or 'our_side',
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
        """发送询价邀请给多个加工方（跳过已存在待回复邀请的加工方）"""
        stmt = select(EntrustOutsourceRequest).where(EntrustOutsourceRequest.id == inquiry_id)
        inquiry = (await db.execute(stmt)).scalar_one_or_none()
        if not inquiry:
            return None

        # ---- 发送前自动查找/拆图，将 drawing_id 写入 scope_json ----
        await InquiryService._ensure_drawings(db, inquiry)

        # 查询该供应商在该项目中已有的待回复邀请
        project_id = inquiry.project_id
        existing_stmt = (
            select(EntrustInvitation)
            .join(EntrustOutsourceRequest, EntrustInvitation.request_id == EntrustOutsourceRequest.id)
            .where(
                EntrustOutsourceRequest.project_id == project_id,
                EntrustInvitation.supplier_id.in_(data.supplier_ids),
                EntrustInvitation.status.in_(('sent', 'draft_quoted')),
            )
        )
        existing_invs = (await db.execute(existing_stmt)).scalars().all()
        # 已有待回复的 supplier_ids
        pending_supplier_ids = {inv.supplier_id for inv in existing_invs}

        now = datetime.now()
        skipped = []
        for sid in data.supplier_ids:
            if sid in pending_supplier_ids:
                skipped.append(sid)
                continue
            inv = EntrustInvitation(
                request_id=inquiry_id,
                supplier_id=sid,
                status='sent',
                sent_at=now,
            )
            db.add(inv)

        if not skipped or len(skipped) < len(data.supplier_ids):
            inquiry.status = 'sent'
        await db.flush()
        await db.commit()
        return {'skipped': skipped}

    @staticmethod
    async def _ensure_drawings(db: AsyncSession, inquiry):
        """
        发送询价前，遍历 scope_json 中每个零件，
        用 mold_code + part_no 查图纸库 → 没有则去D盘找原图拆图 → drawing_id 写回 scope_json
        """
        from module_entrust.service.drawing_service import lookup_drawings

        scope_json = inquiry.scope_json
        if not scope_json or not isinstance(scope_json, list):
            return

        updated = False
        for item in scope_json:
            mold_code = item.get('mold_code', '')
            part_no = item.get('part_no', '')
            if not mold_code or not part_no:
                continue

            # 已有 drawing_id 则跳过
            if item.get('drawing_id'):
                continue

            try:
                results = await lookup_drawings(db, mold_code, part_no)
                if results and results[0].get('found'):
                    item['drawing_id'] = results[0]['drawing_id']
                    updated = True
                    logger.info(f'[询价图纸] {mold_code}/{part_no} → drawing_id={results[0]["drawing_id"]}')
                else:
                    msg = results[0].get('message', '未找到') if results else '未找到'
                    logger.warning(f'[询价图纸] {mold_code}/{part_no} 未找到: {msg}')
            except Exception as e:
                logger.error(f'[询价图纸] {mold_code}/{part_no} 查找异常: {e}')

        if updated:
            inquiry.scope_json = list(scope_json)  # 触发 SQLAlchemy 检测 JSON 变更
            await db.flush()

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

        # 检查该项目是否已存在委外工单（同一项目只能选标一次）
        existing_order = (await db.execute(
            select(EntrustOutsourceOrder).where(
                EntrustOutsourceOrder.project_id == inquiry.project_id,
                EntrustOutsourceOrder.status != 'cancelled',
            ).limit(1)
        )).scalar()
        if existing_order:
            raise ValueError('该项目已存在委外工单，不可重复选标')

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

    # 本地优先排序参考地区
    LOCAL_PROVINCE = '山东'
    LOCAL_CITY = '青岛'

    @staticmethod
    async def _query_project_drawings(db: AsyncSession, project_id: int) -> list[DrawingBrief]:
        """查询项目所有可用的拆图，返回 DrawingBrief 列表"""
        from module_entrust.entity.do.entrust_do import EntrustMold
        from module_entrust.service.drawing_service import normalize_mold_code

        # 查项目的模具号
        molds = (await db.execute(
            select(EntrustMold).where(EntrustMold.project_id == project_id)
        )).scalars().all()
        mold_codes = list({normalize_mold_code(m.name or '') for m in molds if m.name})

        if not mold_codes:
            return []

        # 查所有可用图纸
        drawings = (await db.execute(
            select(EntrustDrawing).where(
                EntrustDrawing.mold_code.in_(mold_codes),
                EntrustDrawing.is_latest == True,
                EntrustDrawing.status == 'available',
            ).order_by(EntrustDrawing.mold_code, EntrustDrawing.part_code)
        )).scalars().all()

        return [
            DrawingBrief(
                id=d.id,
                mold_code=d.mold_code,
                part_code=d.part_code,
                file_name=d.file_name,
                file_size_kb=d.file_size_kb,
                download_url=f'/entrust/drawing/download/{d.id}',
            )
            for d in drawings
        ]

    @staticmethod
    def _location_rank(province: str, city: str) -> int:
        if city == InquiryService.LOCAL_CITY and province == InquiryService.LOCAL_PROVINCE:
            return 0
        if province == InquiryService.LOCAL_PROVINCE:
            return 1
        return 2

    @staticmethod
    async def get_grouped_list(db: AsyncSession, page_num: int = 1, page_size: int = 10):
        """按项目分组查询询价汇总"""
        # 查询所有有询价单的项目
        project_ids_stmt = (
            select(EntrustOutsourceRequest.project_id, func.count(EntrustOutsourceRequest.id))
            .group_by(EntrustOutsourceRequest.project_id)
            .order_by(EntrustOutsourceRequest.project_id.desc())
        )
        project_rows = (await db.execute(project_ids_stmt)).all()

        total = len(project_rows)
        offset = (page_num - 1) * page_size
        paged = project_rows[offset:offset + page_size]

        results = []
        for project_id, inquiry_count in paged:
            # 获取项目信息
            proj_stmt = select(EntrustProject).where(EntrustProject.id == project_id)
            project = (await db.execute(proj_stmt)).scalar_one_or_none()
            if not project:
                continue

            # 获取该项目所有询价单
            req_stmt = select(EntrustOutsourceRequest).where(EntrustOutsourceRequest.project_id == project_id)
            requests = (await db.execute(req_stmt)).scalars().all()

            latest_at = None
            for r in requests:
                if r.created_at and (not latest_at or r.created_at > latest_at):
                    latest_at = r.created_at

            # 获取所有邀请（含供应商和报价）
            req_ids = [r.id for r in requests]
            all_suppliers = []

            if req_ids:
                inv_stmt = (
                    select(EntrustInvitation, EntrustSupplier)
                    .join(EntrustSupplier, EntrustInvitation.supplier_id == EntrustSupplier.id)
                    .where(EntrustInvitation.request_id.in_(req_ids))
                )
                inv_rows = (await db.execute(inv_stmt)).all()

                # 按 supplier_id 去重，取最新的一条
                supplier_map = {}
                for inv, supplier in inv_rows:
                    sid = supplier.id
                    if sid not in supplier_map:
                        supplier_map[sid] = (inv, supplier)
                    else:
                        # 保留最新的邀请（sent_at 更大的）
                        prev_inv, _ = supplier_map[sid]
                        if inv.sent_at and prev_inv.sent_at and inv.sent_at > prev_inv.sent_at:
                            supplier_map[sid] = (inv, supplier)

                quoted_count = 0
                # request_id -> delivery_date 映射
                req_delivery_map = {r.id: r.delivery_date for r in requests}

                for sid, (inv, supplier) in supplier_map.items():
                    quotation = None
                    quotation_id = None
                    if inv.status == 'quoted':
                        q_stmt = select(EntrustQuotation).where(EntrustQuotation.invitation_id == inv.id)
                        q = (await db.execute(q_stmt)).scalar_one_or_none()
                        if q:
                            quotation = q
                            quotation_id = q.id
                            quoted_count += 1

                    # 找到关联的 request_id
                    req_id = inv.request_id

                    all_suppliers.append({
                        'supplier_id': sid,
                        'supplier_name': supplier.name,
                        'province': supplier.province,
                        'city': supplier.city,
                        'invitation_id': inv.id,
                        'invitation_status': inv.status,
                        'request_id': req_id,
                        'quotation_id': quotation_id,
                        'unit_price': float(quotation.unit_price) if quotation and quotation.unit_price else None,
                        'lead_time_days': quotation.lead_time_days if quotation else None,
                        'delivery_date': req_delivery_map.get(req_id),
                        'lines_json': quotation.lines_json if quotation else inv.draft_quote_json,
                        'note': quotation.note if quotation else None,
                        'quoted_at': quotation.submitted_at if quotation else None,
                        'sent_at': inv.sent_at,
                    })

                # 排序：有报价的排前面 → 本地优先 → 价格升序
                all_suppliers.sort(key=lambda x: (
                    0 if x['unit_price'] is not None else 1,
                    InquiryService._location_rank(x.get('province', ''), x.get('city', '')),
                    x['unit_price'] if x['unit_price'] is not None else 999999,
                ))

                # 添加排名
                rank = 0
                for s in all_suppliers:
                    if s['unit_price'] is not None:
                        rank += 1
                        s['rank'] = rank
                        s['rank_description'] = ''  # 先空着，后续算法填充
                    else:
                        s['rank'] = None
                        s['rank_description'] = ''

            supplier_quotes = [GroupedSupplierQuote(**s) for s in all_suppliers]

            # 询价单摘要列表（用于导出）
            inquiry_briefs = [GroupedInquiryBrief.model_validate(r) for r in requests]

            # 检查该项目是否已存在委外工单
            order_check = (await db.execute(
                select(EntrustOutsourceOrder).where(
                    EntrustOutsourceOrder.project_id == project_id,
                    EntrustOutsourceOrder.status != 'cancelled',
                ).limit(1)
            )).scalar()
            has_order = order_check is not None

            # 查询项目图纸
            project_drawings = await InquiryService._query_project_drawings(db, project_id)

            results.append(InquiryGroupedResponse(
                project_id=project_id,
                project_name=project.name,
                project_no=project.project_no,
                inquiry_count=inquiry_count,
                latest_inquiry_at=latest_at,
                quoted_supplier_count=quoted_count if all_suppliers else 0,
                total_supplier_count=len(all_suppliers),
                suppliers=supplier_quotes,
                inquiries=inquiry_briefs,
                has_order=has_order,
                project_drawings=project_drawings,
            ))

        return results, total

    @staticmethod
    async def get_order_list(db: AsyncSession, page_num: int = 1, page_size: int = 10, status: str = None):
        """查询委外工单列表（含供应商名称、项目名称等）"""
        stmt = select(EntrustOutsourceOrder).where(EntrustOutsourceOrder.id > 0)
        if status:
            stmt = stmt.where(EntrustOutsourceOrder.status == status)
        # 总数
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar()
        # 分页
        offset = (page_num - 1) * page_size
        stmt = stmt.order_by(EntrustOutsourceOrder.created_at.desc()).offset(offset).limit(page_size)
        orders = (await db.execute(stmt)).scalars().all()

        results = []
        for order in orders:
            item = OutsourceOrderResponse.model_validate(order).model_dump()
            # 补充供应商名称
            if order.supplier_id:
                sup = (await db.execute(select(EntrustSupplier).where(EntrustSupplier.id == order.supplier_id))).scalar_one_or_none()
                item['supplier_name'] = sup.name if sup else ''
            # 补充项目名称
            if order.project_id:
                proj = (await db.execute(select(EntrustProject).where(EntrustProject.id == order.project_id))).scalar_one_or_none()
                item['project_name'] = proj.name if proj else ''
                item['project_no'] = proj.project_no if proj else ''
            # 补充询价单信息（scope_json, delivery_date, material_preparation 等）
            if order.request_id:
                req = (await db.execute(select(EntrustOutsourceRequest).where(EntrustOutsourceRequest.id == order.request_id))).scalar_one_or_none()
                if req:
                    item['scope_json'] = req.scope_json
                    item['delivery_date'] = req.delivery_date.isoformat() if req.delivery_date else None
                    item['material_preparation'] = req.material_preparation
                    item['customer_name'] = req.customer_name
                    item['order_no_ext'] = req.order_no
                    item['deadline'] = req.deadline.isoformat() if req.deadline else None
            # 补充报价明细
            if order.quotation_id:
                quote = (await db.execute(select(EntrustQuotation).where(EntrustQuotation.id == order.quotation_id))).scalar_one_or_none()
                if quote:
                    item['lines_json'] = quote.lines_json
                    item['quote_note'] = quote.note
            results.append(item)
        return results, total
