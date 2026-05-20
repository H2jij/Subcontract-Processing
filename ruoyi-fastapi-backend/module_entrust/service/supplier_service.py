"""
委外加工 — 加工方管理 Service
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions.exception import ServiceException
from module_entrust.entity.do.entrust_do import EntrustSupplier, EntrustSupplierCapability
from module_entrust.entity.vo.entrust_vo import (
    SupplierCreate, SupplierUpdate, SupplierQuery, SupplierResponse,
)
from module_admin.entity.do.user_do import SysUser, SysUserRole
from utils.pwd_util import PwdUtil

# 加工方角色ID
PROCESSOR_ROLE_ID = 103
DEFAULT_PASSWORD = 'admin123'


class SupplierService:
    """加工方/供应商管理服务"""

    @staticmethod
    async def _enrich_response(db: AsyncSession, supplier: EntrustSupplier) -> SupplierResponse:
        """给响应补充关联用户名"""
        resp = SupplierResponse.model_validate(supplier)
        if supplier.user_id:
            user_stmt = select(SysUser).where(SysUser.user_id == supplier.user_id)
            user = (await db.execute(user_stmt)).scalar_one_or_none()
            if user:
                resp.link_username = user.user_name
        return resp

    @staticmethod
    async def get_supplier_list(db: AsyncSession, query: SupplierQuery):
        stmt = select(EntrustSupplier).where(EntrustSupplier.id > 0)
        if query.name:
            stmt = stmt.where(EntrustSupplier.name.ilike(f'%{query.name}%'))
        if query.category:
            stmt = stmt.where(EntrustSupplier.category == query.category)
        if query.status:
            stmt = stmt.where(EntrustSupplier.status == query.status)
        if hasattr(query, 'supplier_type') and query.supplier_type:
            stmt = stmt.where(EntrustSupplier.supplier_type == query.supplier_type)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar()

        offset = (query.page_num - 1) * query.page_size
        stmt = stmt.order_by(EntrustSupplier.created_at.desc()).offset(offset).limit(query.page_size)
        result = (await db.execute(stmt)).scalars().all()

        rows = []
        for r in result:
            rows.append(await SupplierService._enrich_response(db, r))
        return rows, total

    @staticmethod
    async def get_supplier_detail(db: AsyncSession, supplier_id: int):
        stmt = select(EntrustSupplier).where(EntrustSupplier.id == supplier_id)
        result = (await db.execute(stmt)).scalar_one_or_none()
        if not result:
            return None
        return await SupplierService._enrich_response(db, result)

    @staticmethod
    async def _create_link_user(db: AsyncSession, username: str, password: str, nick_name: str):
        """创建加工方登录账号并分配加工方角色，返回 user_id"""
        # 检查用户名是否重复
        exists = (await db.execute(
            select(SysUser).where(SysUser.user_name == username)
        )).scalar_one_or_none()
        if exists:
            raise ServiceException(message=f'用户名 {username} 已存在')

        hashed = PwdUtil.get_password_hash(password)
        user = SysUser(
            user_name=username,
            nick_name=nick_name,
            password=hashed,
            status='0',
            del_flag='0',
        )
        db.add(user)
        await db.flush()
        # 分配加工方角色
        user_role = SysUserRole(user_id=user.user_id, role_id=PROCESSOR_ROLE_ID)
        db.add(user_role)
        await db.flush()
        return user.user_id

    @staticmethod
    async def create_supplier(db: AsyncSession, data: SupplierCreate, user_id: int):
        link_user_id = None
        if data.link_username:
            pwd = data.link_password or DEFAULT_PASSWORD
            link_user_id = await SupplierService._create_link_user(
                db, data.link_username, pwd, data.name
            )

        supplier = EntrustSupplier(
            name=data.name,
            supplier_type=data.supplier_type or 'processor',
            category=data.category,
            province=data.province,
            city=data.city,
            address=data.address,
            legal_rep=data.legal_rep,
            contact_name=data.contact_name,
            contact_phone=data.contact_phone,
            contact_email=data.contact_email,
            credit_code=data.credit_code,
            bank_name=data.bank_name,
            bank_account=data.bank_account,
            bank_account_name=data.bank_account_name,
            rating=data.rating,
            base_price=data.base_price,
            contract_amount=data.contract_amount,
            contract_start=data.contract_start,
            contract_end=data.contract_end,
            signed_at=data.signed_at,
            status='active',
            remark=data.remark,
            created_by=user_id,
            user_id=link_user_id,
        )
        db.add(supplier)
        await db.flush()
        await db.commit()
        await db.refresh(supplier)
        return await SupplierService._enrich_response(db, supplier)

    @staticmethod
    async def update_supplier(db: AsyncSession, supplier_id: int, data: SupplierUpdate):
        stmt = select(EntrustSupplier).where(EntrustSupplier.id == supplier_id)
        supplier = (await db.execute(stmt)).scalar_one_or_none()
        if not supplier:
            return None

        # exclude_none=False 确保前端明确传入的空字符串也能清空字段
        update_data = data.model_dump(exclude_unset=True, exclude_none=False)

        # 处理关联账号（单独逻辑）
        link_username = update_data.pop('link_username', None)
        link_password = update_data.pop('link_password', None)

        if link_username and not supplier.user_id:
            pwd = link_password or DEFAULT_PASSWORD
            new_user_id = await SupplierService._create_link_user(
                db, link_username, pwd, supplier.name
            )
            supplier.user_id = new_user_id

        # 应用所有其他字段更新
        for k, v in update_data.items():
            if hasattr(supplier, k):
                setattr(supplier, k, v)

        await db.flush()
        await db.commit()
        await db.refresh(supplier)
        return await SupplierService._enrich_response(db, supplier)

    @staticmethod
    async def delete_supplier(db: AsyncSession, supplier_id: int):
        stmt = select(EntrustSupplier).where(EntrustSupplier.id == supplier_id)
        supplier = (await db.execute(stmt)).scalar_one_or_none()
        if not supplier:
            return False
        await db.delete(supplier)
        await db.flush()
        await db.commit()
        return True

    # --- 能力标签 ---

    @staticmethod
    async def get_capabilities(db: AsyncSession, supplier_id: int):
        stmt = select(EntrustSupplierCapability).where(
            EntrustSupplierCapability.supplier_id == supplier_id
        )
        result = (await db.execute(stmt)).scalars().all()
        return [{'id': r.id, 'process_name': r.process_name} for r in result]

    @staticmethod
    async def set_capabilities(db: AsyncSession, supplier_id: int, process_names: list[str]):
        # 删除旧的
        old_stmt = select(EntrustSupplierCapability).where(
            EntrustSupplierCapability.supplier_id == supplier_id
        )
        old = (await db.execute(old_stmt)).scalars().all()
        for o in old:
            await db.delete(o)
        await db.flush()

        # 添加新的
        for name in process_names:
            cap = EntrustSupplierCapability(supplier_id=supplier_id, process_name=name)
            db.add(cap)
        await db.flush()
        await db.commit()
        return True
