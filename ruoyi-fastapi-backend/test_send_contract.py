"""
合同邮件分发 — 端到端测试脚本
=====================================
1. 在数据库创建一套虚拟测试数据（项目 + 供应商 + 询价单）
2. 走完整合同填充 + 邮件发送流程
3. 发送至指定邮箱并打印结果
4. 所有测试数据标记前缀 [TEST]，方便清理

运行方式：
    python test_send_contract.py [--to 收件邮箱] [--dry-run]
"""
import asyncio
import argparse
from datetime import date, timedelta
from pathlib import Path

# 确保能 import 后端模块
import sys
sys.path.insert(0, str(Path(__file__).parent))

from config.env import GetConfig
GetConfig()  # 加载 .env.dev

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, text
from config.env import DataBaseConfig

# ── 可修改的测试数据 ──────────────────────────────────────────────────────────
TEST_DATA = {
    # 收件邮箱
    "recipient_email": "18815361615@163.com",

    # 供应商（乙方）信息
    "supplier_name":    "[TEST] 上海虚拟钢料贸易有限公司",
    "supplier_category": "钢料",
    "supplier_province": "上海市",
    "supplier_city":    "浦东新区",
    "supplier_address": "测试路 888 号",
    "supplier_contact": "李测试",
    "supplier_phone":   "021-88888888",
    "supplier_email":   "18815361615@163.com",
    "supplier_credit":  "91310000TEST000001",

    # 询价单信息
    "inquiry_title":    "[TEST] 年度钢料采购框架合同测试",
    "order_no":         "TEST-2026-001",
    "inquiry_date":     date.today(),
    "delivery_date":    date.today() + timedelta(days=365),

    # 甲方信息（覆盖 sys_config，仅本次生效）
    "extra_values": {
        "甲方法定代表人": "张总",
        "甲方联系方式":   "0532-88888888",
        "甲方信用代码":   "91370200TEST000000",
        "包装指导书编号": "PKG-2026-TEST-001",
        "合同额度":       "500,000 元",
    },
}
# ─────────────────────────────────────────────────────────────────────────────


def build_db_url() -> str:
    c = DataBaseConfig
    return f"postgresql+asyncpg://{c.db_username}:{c.db_password}@{c.db_host}:{c.db_port}/{c.db_database}"


async def get_or_create_test_supplier(session: AsyncSession) -> int:
    """获取或创建测试供应商，返回 supplier_id。"""
    from module_entrust.entity.do.entrust_do import EntrustSupplier
    stmt = select(EntrustSupplier).where(EntrustSupplier.name == TEST_DATA["supplier_name"])
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        print(f"  ✓ 使用已有测试供应商 id={existing.id}")
        # 确保邮箱和信用代码已填
        existing.contact_email = TEST_DATA["supplier_email"]
        existing.credit_code   = TEST_DATA["supplier_credit"]
        await session.flush()
        return existing.id

    supplier = EntrustSupplier(
        name          = TEST_DATA["supplier_name"],
        category      = TEST_DATA["supplier_category"],
        province      = TEST_DATA["supplier_province"],
        city          = TEST_DATA["supplier_city"],
        address       = TEST_DATA["supplier_address"],
        contact_name  = TEST_DATA["supplier_contact"],
        contact_phone = TEST_DATA["supplier_phone"],
        contact_email = TEST_DATA["supplier_email"],
        credit_code   = TEST_DATA["supplier_credit"],
        status        = "active",
    )
    session.add(supplier)
    await session.flush()
    print(f"  ✓ 创建测试供应商 id={supplier.id}")
    return supplier.id


async def get_or_create_test_project(session: AsyncSession) -> int:
    """获取或创建测试项目，返回 project_id。"""
    from module_entrust.entity.do.entrust_do import EntrustProject
    stmt = select(EntrustProject).where(EntrustProject.project_no == "TEST-PROJ-2026")
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        print(f"  ✓ 使用已有测试项目 id={existing.id}")
        return existing.id

    project = EntrustProject(
        project_no  = "TEST-PROJ-2026",
        name        = "[TEST] 年度钢料采购测试项目",
        customer    = "青岛瑞利杰金属有限公司",
        deadline    = TEST_DATA["delivery_date"],
        unit_price  = 500000,
        quantity    = 1,
        description = "端到端测试自动创建，可安全删除",
        status      = "confirmed",
    )
    session.add(project)
    await session.flush()
    print(f"  ✓ 创建测试项目 id={project.id}")
    return project.id


async def get_or_create_test_inquiry(session: AsyncSession, project_id: int) -> int:
    """获取或创建测试询价单，返回 inquiry_id。"""
    from module_entrust.entity.do.entrust_do import EntrustOutsourceRequest
    stmt = select(EntrustOutsourceRequest).where(
        EntrustOutsourceRequest.order_no == TEST_DATA["order_no"]
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        print(f"  ✓ 使用已有测试询价单 id={existing.id}")
        return existing.id

    inquiry = EntrustOutsourceRequest(
        project_id      = project_id,
        title           = TEST_DATA["inquiry_title"],
        order_no        = TEST_DATA["order_no"],
        inquiry_date    = TEST_DATA["inquiry_date"],
        delivery_date   = TEST_DATA["delivery_date"],
        customer_name   = "青岛瑞利杰金属有限公司",
        customer_contact= "张总",
        customer_phone  = "0532-88888888",
        status          = "sent",
    )
    session.add(inquiry)
    await session.flush()
    print(f"  ✓ 创建测试询价单 id={inquiry.id}")
    return inquiry.id


async def main(recipient_email: str, dry_run: bool):
    engine = create_async_engine(build_db_url(), echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("\n=== 合同邮件分发测试 ===")
    print(f"收件邮箱: {recipient_email}")
    print(f"调试模式: {'是（不实际发送）' if dry_run else '否（实际发送）'}\n")

    async with AsyncSessionLocal() as session:
        print("[1/4] 准备测试数据...")
        supplier_id = await get_or_create_test_supplier(session)
        project_id  = await get_or_create_test_project(session)
        inquiry_id  = await get_or_create_test_inquiry(session, project_id)
        await session.commit()

        print(f"\n[2/4] 运行合同生成流程...")
        print(f"  询价单 id={inquiry_id}  供应商 id={supplier_id}")

        # 临时覆盖 debug 模式
        from config.env import SmtpConfig
        original_debug = SmtpConfig.smtp_debug
        if dry_run:
            SmtpConfig.smtp_debug = True

        from module_entrust.service.contract_service import ContractService
        result = await ContractService.send_contract(
            db             = session,
            inquiry_id     = inquiry_id,
            supplier_id    = supplier_id,
            recipient_email= recipient_email,
            extra_values   = TEST_DATA["extra_values"],
            created_by     = 1,
        )

        SmtpConfig.smtp_debug = original_debug

        print(f"\n[3/4] 发送结果:")
        print(f"  成功:          {result['success']}")
        print(f"  消息:          {result['message']}")
        print(f"  SMTP ID:       {result.get('smtp_message_id', '—')}")
        print(f"  发送记录 ID:   {result.get('record_id', '—')}")
        if result.get('missing_fields'):
            print(f"  ⚠ 缺失字段:  {result['missing_fields']}")

        print(f"\n[4/4] 查询发送历史:")
        records = await ContractService.get_contract_records(session, inquiry_id)
        for r in records[:3]:
            print(f"  [{r['id']}] {r['status']} → {r['recipient_email']}  {r['sent_at']}")

    await engine.dispose()
    print("\n=== 测试完成 ===\n")
    print("测试数据保留在数据库中，如需清理执行：")
    print("  DELETE FROM entrust_outsource_requests WHERE order_no='TEST-2026-001';")
    print("  DELETE FROM entrust_projects WHERE project_no='TEST-PROJ-2026';")
    print("  DELETE FROM entrust_suppliers WHERE name LIKE '[TEST]%';")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--to", default=TEST_DATA["recipient_email"], help="收件邮箱")
    parser.add_argument("--dry-run", action="store_true", help="只打日志不实际发送")
    args = parser.parse_args()
    asyncio.run(main(args.to, args.dry_run))
