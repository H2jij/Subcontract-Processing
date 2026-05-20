"""
委外加工模块 — SQLAlchemy ORM 模型
表名前缀 entrust_*，避免与同事的 mold/project 等表冲突
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, Integer,
    Numeric, String, Text, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB

from config.database import Base


class EntrustSupplier(Base):
    """加工方/供应商表"""
    __tablename__ = 'entrust_suppliers'
    __table_args__ = (
        UniqueConstraint('name', name='uk_entrust_supplier_name'),
        {'comment': '加工方/供应商表'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    name = Column(String(255), nullable=False, comment='供应商名称')
    supplier_type = Column(String(32), default='processor', comment='类型：processor-加工方 material-材料方 other-其他')
    category = Column(String(128), comment='供应商分类')
    province = Column(String(64), comment='省')
    city = Column(String(64), comment='市')
    address = Column(String(512), comment='地址')
    legal_rep = Column(String(64), comment='法定代表人')
    contact_name = Column(String(64), comment='联系人')
    contact_phone = Column(String(32), comment='联系电话')
    contact_email = Column(String(255), comment='联系邮箱（合同发送收件地址）')
    credit_code = Column(String(64), comment='统一社会信用代码')
    bank_name = Column(String(128), comment='开户银行')
    bank_account = Column(String(64), comment='银行账号')
    bank_account_name = Column(String(128), comment='银行开户名')
    rating = Column(Numeric(4, 2), comment='评分')
    status = Column(String(32), default='active', comment='状态：active-启用 disabled-停用')
    base_price = Column(Numeric(14, 2), comment='基准加工单价（参考价）')
    contract_amount = Column(Numeric(14, 2), comment='框架合同额度')
    contract_start = Column(Date, comment='合同起始日期')
    contract_end = Column(Date, comment='合同终止日期')
    signed_at = Column(Date, comment='合同签订日期')
    remark = Column(Text, comment='备注')
    user_id = Column(BigInteger, comment='关联系统用户ID（加工方登录账号）')
    created_by = Column(BigInteger, comment='创建人')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class EntrustProject(Base):
    """委外项目表"""
    __tablename__ = 'entrust_projects'
    __table_args__ = (
        UniqueConstraint('project_no', name='uk_entrust_project_no'),
        {'comment': '委外项目表'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    project_no = Column(String(64), nullable=False, comment='项目编号')
    name = Column(String(255), nullable=False, comment='项目名称')
    customer = Column(String(255), nullable=False, comment='客户名称')
    deadline = Column(Date, comment='交期')
    unit_price = Column(Numeric(14, 2), comment='单价')
    quantity = Column(Integer, comment='数量')
    description = Column(Text, comment='项目描述')
    status = Column(String(32), nullable=False, default='drafted', comment='状态：drafted/confirmed/in_progress/completed')
    created_by = Column(BigInteger, comment='创建人')
    confirmed_at = Column(DateTime, comment='确认时间')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    drawing_status = Column(String(32), default='none', comment='拆图状态：none/splitting/done/error')
    drawing_message = Column(Text, default=None, comment='拆图结果信息')


class EntrustMold(Base):
    """模具套表"""
    __tablename__ = 'entrust_molds'
    __table_args__ = {'comment': '模具套表'}

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    project_id = Column(Integer, nullable=False, comment='项目ID')
    name = Column(String(255), comment='模具套名称')
    sort_no = Column(Integer, default=0, comment='排序号')
    remark = Column(Text, comment='备注')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class EntrustPart(Base):
    """零件表"""
    __tablename__ = 'entrust_parts'
    __table_args__ = {'comment': '零件表'}

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    project_id = Column(Integer, nullable=False, comment='项目ID')
    mold_id = Column(Integer, comment='模具套ID')
    part_no = Column(String(64), nullable=False, comment='零件编号')
    part_name = Column(String(255), comment='零件名称')
    material = Column(String(64), comment='材料')
    material_id = Column(Integer, comment='材料ID(外键)')
    qty = Column(Integer, nullable=False, default=1, comment='数量')
    spec = Column(String(255), comment='规格')
    part_type = Column(String(32), comment='零件类型：die/ins/part/frame/std')
    processes_json = Column(JSONB, comment='工序列表JSON')
    process_method_ids = Column(JSONB, comment='工艺方法ID列表')
    status = Column(String(32), default='pending', comment='状态')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class EntrustProcessMethod(Base):
    """工艺方法基础表"""
    __tablename__ = 'entrust_process_methods'
    __table_args__ = (
        UniqueConstraint('name', name='uk_entrust_process_method_name'),
        {'comment': '工艺方法基础表'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    name = Column(String(64), nullable=False, comment='工艺名称（如CNC开粗、热处理）')
    category = Column(String(64), comment='分类')
    remark = Column(Text, comment='备注')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')


class EntrustProcessCode(Base):
    """工艺代码对照表（带父子层级）"""
    __tablename__ = 'entrust_process_codes'
    __table_args__ = (
        UniqueConstraint('code', name='uk_entrust_process_code'),
        {'comment': '工艺代码对照表（父子层级）'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    code = Column(String(32), nullable=False, unique=True, comment='工序代码：Z-钻床 X-铣床 WC-快丝等')
    name = Column(String(64), nullable=False, comment='工序名称：钻床、铣床、快丝等')
    parent_id = Column(Integer, comment='父级ID（NULL表示顶级分类）')
    sort_no = Column(Integer, default=0, comment='排序号')
    is_active = Column(Integer, default=1, comment='是否启用：0-禁用 1-启用')
    remark = Column(Text, comment='备注')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')


class EntrustMaterial(Base):
    """材料基础表"""
    __tablename__ = 'entrust_materials'
    __table_args__ = {'comment': '材料基础表'}

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    name = Column(String(128), nullable=False, comment='材料名称')
    spec = Column(String(128), comment='规格')
    category = Column(String(64), comment='分类')
    unit = Column(String(32), comment='单位')
    remark = Column(Text, comment='备注')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')


class EntrustSupplierCapability(Base):
    """加工方能力表"""
    __tablename__ = 'entrust_supplier_capabilities'
    __table_args__ = (
        UniqueConstraint('supplier_id', 'process_name', name='uk_entrust_sup_cap'),
        {'comment': '加工方能力表'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    supplier_id = Column(Integer, nullable=False, comment='加工方ID')
    process_name = Column(String(64), nullable=False, comment='工艺名称')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')


class EntrustOutsourceRequest(Base):
    """委外询价单"""
    __tablename__ = 'entrust_outsource_requests'
    __table_args__ = {'comment': '委外询价单'}

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    project_id = Column(Integer, nullable=False, comment='项目ID')
    title = Column(String(255), nullable=False, comment='询价标题')
    scope_json = Column(JSONB, comment='询价范围(零件-工序维度)')
    deadline = Column(Date, comment='报价截止日期')
    status = Column(String(32), nullable=False, default='draft', comment='状态：draft/sent/closed/awarded')
    closed_at = Column(DateTime, comment='截止时间')
    winning_quote_id = Column(Integer, comment='中标报价ID')
    created_by = Column(BigInteger, comment='创建人')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    # 询价单扩展字段
    customer_name = Column(String(255), comment='客户名称（我方）')
    customer_contact = Column(String(64), comment='客户联系人')
    customer_phone = Column(String(32), comment='客户电话')
    order_no = Column(String(64), comment='订单号')
    inquiry_date = Column(Date, comment='询价日期')
    delivery_date = Column(Date, comment='交付日期')
    material_preparation = Column(String(32), default='our_side', comment='备料情况：our_side-我方备料 supplier-加工方备料')


class EntrustInvitation(Base):
    """询价邀请"""
    __tablename__ = 'entrust_invitations'
    __table_args__ = (
        UniqueConstraint('request_id', 'supplier_id', name='uk_entrust_inv_req_sup'),
        {'comment': '询价邀请'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    request_id = Column(Integer, nullable=False, comment='询价单ID')
    supplier_id = Column(Integer, nullable=False, comment='加工方ID')
    status = Column(String(32), nullable=False, default='sent', comment='状态：sent/draft_quoted/quoted/declined')
    sent_at = Column(DateTime, nullable=False, default=datetime.now, comment='发送时间')
    quoted_at = Column(DateTime, comment='报价时间')
    decline_remark = Column(Text, comment='拒绝备注')
    draft_quote_json = Column(JSONB, comment='报价草稿(未发送前可反复修改)')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')


class EntrustQuotation(Base):
    """报价单"""
    __tablename__ = 'entrust_quotations'
    __table_args__ = {'comment': '报价单'}

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    invitation_id = Column(Integer, nullable=False, unique=True, comment='邀请ID')
    unit_price = Column(Numeric(14, 2), comment='单价')
    lead_time_days = Column(Integer, comment='交期(天)')
    note = Column(Text, comment='备注')
    lines_json = Column(JSONB, comment='逐项报价明细')
    submitted_by = Column(BigInteger, comment='报价人')
    submitted_at = Column(DateTime, nullable=False, default=datetime.now, comment='报价时间')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')


class EntrustOutsourceOrder(Base):
    """委外工单"""
    __tablename__ = 'entrust_outsource_orders'
    __table_args__ = (
        UniqueConstraint('order_no', name='uk_entrust_order_no'),
        {'comment': '委外工单'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    request_id = Column(Integer, comment='询价单ID')
    quotation_id = Column(Integer, comment='报价单ID')
    supplier_id = Column(Integer, nullable=False, comment='加工方ID')
    project_id = Column(Integer, comment='项目ID')
    part_id = Column(Integer, comment='零件ID')
    order_no = Column(String(64), nullable=False, comment='委外单号')
    process_name = Column(String(200), comment='工序名称')
    unit_price = Column(Numeric(14, 2), comment='单价')
    quantity = Column(Integer, nullable=False, default=1, comment='数量')
    total_amount = Column(Numeric(14, 2), comment='总金额')
    lead_time_days = Column(Integer, comment='交期(天)')
    plan_delivery_date = Column(DateTime, comment='计划交付日期')
    actual_delivery_date = Column(DateTime, comment='实际交付日期')
    status = Column(String(32), nullable=False, default='awarded', comment='状态：awarded/accepted/producing/delivered/cancelled')
    quality_status = Column(String(32), comment='质检状态：pending/pass/fail')
    remark = Column(Text, comment='备注')
    created_by = Column(BigInteger, comment='创建人')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class EntrustAttachment(Base):
    """附件/图纸表"""
    __tablename__ = 'entrust_attachments'
    __table_args__ = {'comment': '附件/图纸表'}

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    related_type = Column(String(32), nullable=False, comment='关联类型：project/part/order')
    related_id = Column(Integer, nullable=False, comment='关联ID')
    file_name = Column(String(255), nullable=False, comment='文件名')
    file_path = Column(String(512), nullable=False, comment='文件路径')
    file_size = Column(Integer, comment='文件大小(字节)')
    mime_type = Column(String(128), comment='MIME类型')
    category = Column(String(64), comment='分类：drawing/document/photo')
    uploaded_by = Column(BigInteger, comment='上传人')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')


class EntrustDrawing(Base):
    """图纸表（拆分后的零件子图）"""
    __tablename__ = 'entrust_drawings'
    __table_args__ = {'comment': '图纸表（拆分后的零件子图，支持多版本）'}

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    mold_code = Column(String(64), nullable=False, comment='模具编号 如 M250247-P6')
    part_code = Column(String(64), nullable=False, comment='零件编号 如 DIE-10, B03')
    file_name = Column(String(255), nullable=False, comment='文件名 如 DIE-10_v2.dwg')
    file_path = Column(String(512), nullable=False, comment='项目内相对路径')
    file_size_kb = Column(Integer, comment='文件大小(KB)')
    version = Column(Integer, nullable=False, default=1, comment='版本号')
    is_latest = Column(Boolean, nullable=False, default=True, comment='是否最新版')
    source_type = Column(String(32), default='auto_split', comment='来源：auto_split/manual')
    split_at = Column(DateTime, comment='拆分/上传时间')
    status = Column(String(32), default='available', comment='状态：available/unavailable')
    remark = Column(Text, comment='备注')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class EntrustChatSession(Base):
    """聊天会话表"""
    __tablename__ = 'entrust_chat_sessions'
    __table_args__ = (
        UniqueConstraint('our_user_id', 'supplier_id', name='uk_chat_session'),
        {'comment': '聊天会话表'},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    our_user_id = Column(BigInteger, nullable=False, comment='我方用户ID')
    supplier_id = Column(Integer, nullable=False, comment='加工方ID')
    supplier_user_id = Column(BigInteger, comment='加工方登录用户ID（冗余，避免join）')
    project_id = Column(Integer, comment='关联项目ID')
    request_id = Column(Integer, comment='关联询价单ID')
    status = Column(String(32), nullable=False, default='inquiring', comment='会话状态: inquiring/quoted/negotiating/confirmed/completed')
    last_message = Column(Text, comment='最后一条消息')
    last_message_type = Column(String(16), default='text', comment='最后消息类型')
    last_message_at = Column(DateTime, comment='最后消息时间')
    our_hidden = Column(Boolean, nullable=False, default=False, comment='我方是否隐藏此会话')
    supplier_hidden = Column(Boolean, nullable=False, default=False, comment='加工方是否隐藏此会话')
    is_pinned = Column(Boolean, nullable=False, default=False, comment='是否置顶')
    pinned_at = Column(DateTime, comment='置顶时间')
    our_unread = Column(Integer, nullable=False, default=0, comment='我方未读消息数')
    supplier_unread = Column(Integer, nullable=False, default=0, comment='加工方未读消息数')
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class EntrustChatMessage(Base):
    """聊天消息表"""
    __tablename__ = 'entrust_chat_messages'
    __table_args__ = {'comment': '聊天消息表'}

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, nullable=False, comment='会话ID')
    sender_type = Column(String(16), nullable=False, comment='发送方类型: our/supplier')
    sender_id = Column(BigInteger, nullable=False, comment='发送者user_id')
    content = Column(Text, nullable=False, comment='消息内容')
    message_type = Column(String(16), nullable=False, default='text', comment='消息类型: text/quotation/inquiry/file')
    extra_data = Column(JSONB, comment='扩展数据(卡片/文件元信息)')
    created_at = Column(DateTime, default=datetime.now)


class EntrustContractRecord(Base):
    """合同发送历史记录表"""
    __tablename__ = 'entrust_contract_records'
    __table_args__ = {'comment': '合同发送历史记录'}

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    inquiry_id = Column(Integer, nullable=False, comment='询价单ID')
    supplier_id = Column(Integer, nullable=False, comment='加工方ID')
    recipient_email = Column(String(255), nullable=False, comment='收件邮箱')
    status = Column(String(16), nullable=False, default='sent', comment='状态：sent/failed')
    smtp_message_id = Column(String(255), comment='SMTP Message-ID')
    error_message = Column(Text, comment='失败原因')
    sent_at = Column(DateTime, default=datetime.now, comment='发送时间')
    created_by = Column(BigInteger, comment='操作人')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
