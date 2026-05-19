# -*- coding: utf-8 -*-
"""
API 响应数据模型（Pydantic）
"""
from typing import Optional, List
from pydantic import BaseModel, Field


class DwgRecord(BaseModel):
    """单条图纸记录"""

    # -------- 订单/分组标识 --------
    group_uid: Optional[str] = Field(None, description="子订单唯一ID（UUID）")
    group_name: Optional[str] = Field(None, description="分组名称，对应供应商报价分组")
    no: Optional[str] = Field(None, description="请购单编号，如 WJJQG202512080005")

    # -------- 模具/项目编号 --------
    req_code: Optional[str] = Field(None, description="请购单代码，如 M250247-P6-WUJIN")
    order_code: Optional[str] = Field(None, description="模具订单编号，如 M250247-P6")
    project_code: Optional[str] = Field(None, description="项目编号，如 M250247")

    # -------- 图纸路径 --------
    dwg_path: Optional[str] = Field(None, description="DWG 文件相对路径，如 static/dwg/chaidan/xxx.dwg")
    dwg_url: Optional[str] = Field(None, description="DWG 文件完整访问 URL（带域名）")
    dwg_raw: Optional[str] = Field(None, description="数据库原始 dwg 字段值（JSON 字符串）")

    # -------- 供应商 --------
    supplier_code: Optional[str] = Field(None, description="供应商编码")

    # -------- 时间 --------
    created_at: Optional[str] = Field(None, description="记录创建时间")
    updated_at: Optional[str] = Field(None, description="记录最后更新时间")
    eta_date: Optional[str] = Field(None, description="预计交货日期")

    # -------- 状态 --------
    status: Optional[str] = Field(None, description="当前状态，如 待拆单/待接单/跟单/加工完成")


class DwgListResponse(BaseModel):
    """图纸列表响应"""
    success: bool = True
    total: int = Field(0, description="符合条件的总记录数")
    page: int = Field(1, description="当前页码")
    page_size: int = Field(20, description="每页条数")
    data: List[DwgRecord] = Field(default_factory=list)


class DwgSingleResponse(BaseModel):
    """单条图纸查询响应"""
    success: bool = True
    data: Optional[DwgRecord] = None
    message: Optional[str] = None
