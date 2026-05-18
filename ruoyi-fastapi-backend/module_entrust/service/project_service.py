"""
委外加工 — 项目管理 Service
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from module_entrust.entity.do.entrust_do import EntrustProject, EntrustMold, EntrustPart, EntrustAttachment
from module_entrust.entity.vo.entrust_vo import (
    ProjectCreate, ProjectUpdate, ProjectQuery, ProjectResponse,
    MoldCreate, MoldResponse, PartCreate, PartUpdate, PartResponse,
    AttachmentResponse,
)


class ProjectService:
    """项目管理服务"""

    @staticmethod
    async def get_project_list(db: AsyncSession, query: ProjectQuery, user_id: int):
        """获取项目列表"""
        stmt = select(EntrustProject).where(EntrustProject.id > 0)
        if query.name:
            stmt = stmt.where(EntrustProject.name.ilike(f'%{query.name}%'))
        if query.customer:
            stmt = stmt.where(EntrustProject.customer.ilike(f'%{query.customer}%'))
        if query.status:
            stmt = stmt.where(EntrustProject.status == query.status)

        # 总数
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar()

        # 分页
        offset = (query.page_num - 1) * query.page_size
        stmt = stmt.order_by(EntrustProject.created_at.desc()).offset(offset).limit(query.page_size)
        result = (await db.execute(stmt)).scalars().all()

        rows = [ProjectResponse.model_validate(r) for r in result]
        return rows, total

    @staticmethod
    async def get_project_detail(db: AsyncSession, project_id: int):
        """获取项目详情"""
        stmt = select(EntrustProject).where(EntrustProject.id == project_id)
        result = (await db.execute(stmt)).scalar_one_or_none()
        if not result:
            return None
        return ProjectResponse.model_validate(result)

    @staticmethod
    async def create_project(db: AsyncSession, data: ProjectCreate, user_id: int):
        """创建项目（自动生成项目编号）"""
        # 生成项目编号
        year_suffix = datetime.now().strftime('%y')
        count_stmt = select(func.count()).select_from(EntrustProject)
        count = (await db.execute(count_stmt)).scalar() or 0
        seq = count + 1
        project_no = f'E{year_suffix}-{seq:04d}'

        project = EntrustProject(
            project_no=project_no,
            name=data.name,
            customer=data.customer,
            deadline=data.deadline,
            unit_price=data.unit_price,
            quantity=data.quantity,
            description=data.description,
            status='drafted',
            created_by=user_id,
        )
        db.add(project)
        await db.flush()
        await db.commit()
        await db.refresh(project)
        return ProjectResponse.model_validate(project)

    @staticmethod
    async def update_project(db: AsyncSession, project_id: int, data: ProjectUpdate):
        """更新项目"""
        stmt = select(EntrustProject).where(EntrustProject.id == project_id)
        project = (await db.execute(stmt)).scalar_one_or_none()
        if not project:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for k, v in update_data.items():
            setattr(project, k, v)
        await db.flush()
        await db.commit()
        await db.refresh(project)
        return ProjectResponse.model_validate(project)

    @staticmethod
    async def delete_project(db: AsyncSession, project_id: int):
        """删除项目"""
        stmt = select(EntrustProject).where(EntrustProject.id == project_id)
        project = (await db.execute(stmt)).scalar_one_or_none()
        if not project:
            return False
        await db.delete(project)
        await db.flush()
        await db.commit()
        return True

    # --- 模具套 ---

    @staticmethod
    async def create_mold(db: AsyncSession, project_id: int, data: MoldCreate):
        mold = EntrustMold(
            project_id=project_id,
            name=data.name,
            sort_no=data.sort_no or 0,
            remark=data.remark,
        )
        db.add(mold)
        await db.flush()
        await db.commit()
        await db.refresh(mold)
        return MoldResponse.model_validate(mold)

    @staticmethod
    async def get_molds(db: AsyncSession, project_id: int):
        stmt = select(EntrustMold).where(EntrustMold.project_id == project_id).order_by(EntrustMold.sort_no)
        result = (await db.execute(stmt)).scalars().all()
        return [MoldResponse.model_validate(r) for r in result]

    # --- 零件 ---

    @staticmethod
    async def create_part(db: AsyncSession, project_id: int, data: PartCreate):
        part = EntrustPart(
            project_id=project_id,
            mold_id=data.mold_id,
            part_no=data.part_no or '',
            part_name=data.part_name,
            material=data.material,
            material_id=data.material_id,
            qty=data.qty,
            spec=data.spec,
            part_type=data.part_type,
            processes_json=data.processes,
            process_method_ids=data.process_method_ids,
        )
        db.add(part)
        await db.flush()
        await db.commit()
        await db.refresh(part)
        return PartResponse.model_validate(part)

    @staticmethod
    async def get_parts(db: AsyncSession, project_id: int):
        stmt = select(EntrustPart).where(EntrustPart.project_id == project_id).order_by(EntrustPart.id)
        result = (await db.execute(stmt)).scalars().all()
        return [PartResponse.model_validate(r) for r in result]

    @staticmethod
    async def update_part(db: AsyncSession, part_id: int, data: PartUpdate):
        stmt = select(EntrustPart).where(EntrustPart.id == part_id)
        part = (await db.execute(stmt)).scalar_one_or_none()
        if not part:
            return None
        update_data = data.model_dump(exclude_unset=True)
        if 'processes' in update_data:
            part.processes_json = update_data.pop('processes')
        for k, v in update_data.items():
            setattr(part, k, v)
        await db.flush()
        await db.commit()
        await db.refresh(part)
        return PartResponse.model_validate(part)

    # --- 附件 ---

    @staticmethod
    async def get_attachments(db: AsyncSession, related_type: str, related_id: int):
        stmt = select(EntrustAttachment).where(
            EntrustAttachment.related_type == related_type,
            EntrustAttachment.related_id == related_id,
        ).order_by(EntrustAttachment.created_at.desc())
        result = (await db.execute(stmt)).scalars().all()
        return [AttachmentResponse.model_validate(r) for r in result]

    @staticmethod
    async def add_attachment(db: AsyncSession, related_type: str, related_id: int,
                             file_name: str, file_path: str, file_size: int,
                             mime_type: str, category: str, uploaded_by: int):
        att = EntrustAttachment(
            related_type=related_type,
            related_id=related_id,
            file_name=file_name,
            file_path=file_path,
            file_size=file_size,
            mime_type=mime_type,
            category=category,
            uploaded_by=uploaded_by,
        )
        db.add(att)
        await db.flush()
        await db.commit()
        await db.refresh(att)
        return AttachmentResponse.model_validate(att)
