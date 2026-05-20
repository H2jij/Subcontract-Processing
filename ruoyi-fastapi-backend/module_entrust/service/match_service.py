"""
委外加工 — 加工方匹配 Service

匹配逻辑：
1. 收集项目下所有零件的 process_method_ids
2. 查询所有启用状态的加工方及其能力标签
3. 对每个加工方计算：能覆盖多少所需工艺（覆盖率）
4. 分组：A=全覆盖  B=覆盖>=50%  C=覆盖<50%
5. 组内排序：有价格排上方（本地优先+价格升序），无价格排下方（本地优先+覆盖率降序）
"""
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from module_entrust.entity.do.entrust_do import (
    EntrustPart, EntrustProcessMethod,
    EntrustSupplier, EntrustSupplierCapability,
    EntrustOutsourceRequest, EntrustInvitation,
)

# 本地优先排序参考地区（TODO: 后续从系统配置或项目地址取）
LOCAL_PROVINCE = '山东'
LOCAL_CITY = '青岛'


def _location_rank(province: str, city: str) -> int:
    """地区排序优先级：同城(0) > 同省(1) > 其他(2)"""
    if city == LOCAL_CITY and province == LOCAL_PROVINCE:
        return 0
    if province == LOCAL_PROVINCE:
        return 1
    return 2


class MatchService:
    """加工方匹配服务"""

    @staticmethod
    async def get_project_required_processes(db: AsyncSession, project_id: int) -> list[int]:
        """收集项目所有零件需要的工艺方法ID（去重）"""
        stmt = select(EntrustPart.process_method_ids).where(
            EntrustPart.project_id == project_id,
            EntrustPart.process_method_ids.isnot(None),
        )
        rows = (await db.execute(stmt)).scalars().all()
        required = set()
        for ids in rows:
            if isinstance(ids, list):
                required.update(ids)
        return sorted(required)

    @staticmethod
    async def get_all_active_suppliers_with_capabilities(db: AsyncSession) -> list[dict]:
        """获取所有启用状态的加工方及其能力"""
        # 查加工方
        sup_stmt = select(EntrustSupplier).where(EntrustSupplier.status == 'active')
        suppliers = (await db.execute(sup_stmt)).scalars().all()

        # 查所有能力
        cap_stmt = select(EntrustSupplierCapability)
        all_caps = (await db.execute(cap_stmt)).scalars().all()

        # supplier_id -> [process_name, ...]
        cap_map = defaultdict(set)
        for c in all_caps:
            cap_map[c.supplier_id].add(c.process_name)

        # 查工艺方法名称映射
        pm_stmt = select(EntrustProcessMethod)
        pm_rows = (await db.execute(pm_stmt)).scalars().all()
        pm_name_map = {r.id: r.name for r in pm_rows}  # id -> name

        result = []
        for s in suppliers:
            result.append({
                'id': s.id,
                'name': s.name,
                'category': s.category,
                'province': s.province or '',
                'city': s.city or '',
                'contact_name': s.contact_name or '',
                'contact_phone': s.contact_phone or '',
                'rating': float(s.rating) if s.rating else None,
                'base_price': float(s.base_price) if s.base_price else None,
                'capabilities': list(cap_map.get(s.id, set())),  # process names
            })
        return result, pm_name_map

    @staticmethod
    async def match_suppliers(db: AsyncSession, project_id: int) -> dict:
        """
        核心匹配：返回按 A/B/C 分组的加工方列表
        组内排序：有价格排上方（本地优先+价格升序），无价格排下方（本地优先）
        """
        # 1. 获取项目所需工艺
        required_ids = await MatchService.get_project_required_processes(db, project_id)
        if not required_ids:
            return {
                'required_processes': [],
                'groups': {'A': [], 'B': [], 'C': []},
            }

        # 2. 获取工艺名称映射
        suppliers, pm_name_map = await MatchService.get_all_active_suppliers_with_capabilities(db)

        # 所需工艺名称集合
        required_names = set()
        required_list = []
        for pid in required_ids:
            name = pm_name_map.get(pid, '')
            if name:
                required_names.add(name)
                required_list.append({'id': pid, 'name': name})

        if not required_names:
            return {
                'required_processes': required_list,
                'groups': {'A': [], 'B': [], 'C': []},
            }

        # 3. 查询该项目已有询价邀请，按 supplier_id 汇总最新状态
        inv_stmt = (
            select(EntrustInvitation)
            .join(EntrustOutsourceRequest, EntrustInvitation.request_id == EntrustOutsourceRequest.id)
            .where(EntrustOutsourceRequest.project_id == project_id)
            .order_by(EntrustInvitation.sent_at.desc())
        )
        all_invitations = (await db.execute(inv_stmt)).scalars().all()
        # supplier_id -> 最新的 invitation status（优先：sent/draft_quoted > quoted > declined）
        supplier_inquiry_status = {}
        for inv in all_invitations:
            sid = inv.supplier_id
            if sid not in supplier_inquiry_status:
                supplier_inquiry_status[sid] = inv.status
            else:
                # 如果已有状态是 sent/draft_quoted（待回复），优先保留
                existing = supplier_inquiry_status[sid]
                if existing in ('sent', 'draft_quoted'):
                    pass  # keep
                else:
                    supplier_inquiry_status[sid] = inv.status

        # 4. 逐个加工方计算覆盖率并分组
        total = len(required_names)
        groups = {'A': [], 'B': [], 'C': []}

        for s in suppliers:
            sup_caps = set(s['capabilities'])
            covered = required_names & sup_caps
            cover_count = len(covered)
            coverage_ratio = cover_count / total if total > 0 else 0

            # 计算匹配到的工艺和缺失的工艺
            matched = [n for n in required_list if n['name'] in sup_caps]
            missing = [n for n in required_list if n['name'] not in sup_caps]

            has_price = s['base_price'] is not None

            entry = {
                'supplier_id': s['id'],
                'supplier_name': s['name'],
                'category': s['category'],
                'province': s['province'],
                'city': s['city'],
                'contact_name': s['contact_name'],
                'contact_phone': s['contact_phone'],
                'rating': s['rating'],
                'base_price': s['base_price'],
                'has_price': has_price,
                'coverage_ratio': round(coverage_ratio, 2),
                'covered_count': cover_count,
                'total_required': total,
                'matched_processes': matched,
                'missing_processes': missing,
                'inquiry_status': supplier_inquiry_status.get(s['id']),
            }

            if coverage_ratio >= 1.0:
                groups['A'].append(entry)
            elif coverage_ratio >= 0.5:
                groups['B'].append(entry)
            elif coverage_ratio > 0:
                groups['C'].append(entry)

        # 5. 组内排序：有价格排上方，本地优先，价格升序/覆盖率降序
        for group in groups.values():
            group.sort(key=lambda x: (
                0 if x['has_price'] else 1,                                    # 有价格排上面
                _location_rank(x['province'], x['city']),                     # 本地优先
                x['base_price'] if x['base_price'] is not None else 999999,   # 价格升序
                -(x['coverage_ratio'] or 0),                                   # 无价格时按覆盖率
            ))

        return {
            'required_processes': required_list,
            'groups': groups,
        }
