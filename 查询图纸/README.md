# 查询图纸 & 拆图模块

从采购系统独立拆离，包含两大功能：

- **查询图纸**：查已生成的拆图文件，按订单号/模具编号/子订单ID等检索
- **拆图**：从完整大模具图纸中按零件编号拆出指定部分，生成独立 DWG 文件

## 依赖条件

### 查询功能（只需数据库）
- PostgreSQL 数据库，含以下两张表：
  - `supplier_shortlist_chaidan_wujin`
  - `wujin_items_v4`

### 拆图功能（需额外环境）
- PostgreSQL（同上）
- `ODAFileConverter.exe` 安装在本机（[下载地址](https://www.opendesign.com/guestfiles/oda_file_converter)）
- 网络共享盘可访问（图纸源文件存放位置，由 `CAD_SEARCH_ROOT` 指定）
- `ezdxf` Python 包（pip 安装即可）

## 目录结构

```
查询图纸/
├── README.md           # 说明文档
├── requirements.txt    # 依赖包
├── .env.example        # 环境变量示例（复制为 .env 后填写）
├── main.py             # 启动入口（FastAPI，端口 7000）
├── db.py               # 数据库连接
├── models.py           # 查询响应数据模型
├── crud.py             # 查询 SQL 逻辑
├── router.py           # 查询 API 路由
├── split_router.py     # 拆图 API 路由
└── chaitu1.py          # 拆图核心引擎（从原项目复制）
```

## 快速启动

```bash
cd 查询图纸
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，至少填写 PG_DSN；如需拆图功能，还需填写 CAD_SEARCH_ROOT 和 ODA_FILE_CONVERTER_PATH

python main.py
# 访问 http://localhost:7000/docs 查看完整接口文档
```

## 接口列表

### 📐 查询图纸（/dwg/...）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/dwg/by_group_uid` | 根据子订单ID查图纸路径 |
| GET | `/dwg/by_no` | 根据请购单号查所有图纸 |
| GET | `/dwg/by_order_code` | 根据模具编号查图纸 |
| GET | `/dwg/list` | 分页查询图纸列表 |
| GET | `/dwg/search` | 多条件组合搜索 |

### ✂️ 拆图（/split/...）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/split/locate`  | 验证源文件是否存在，返回文件路径 |
| GET  | `/split/preview` | 预览图纸中所有可识别的子图编号 |
| POST | `/split/chaitu`  | 执行拆图，返回生成的 DWG 文件路径 |

### 系统

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查（含数据库、ODA、图纸库状态） |

---

## 拆图使用示例

### 第一步：验证模具图纸是否存在

```
GET /split/locate?model_code=M250247-P6
```

返回：
```json
{
  "success": true,
  "model_code": "M250247-P6",
  "source_dwg": "E:\\2025---M250001~300\\...\\M250247-P6.2025.04.01.dwg",
  "file_size_mb": 12.3,
  "last_modified": "2025-04-01T10:30:00"
}
```

### 第二步：预览图纸中有哪些子图

```
GET /split/preview?model_code=M250247-P6
```

返回：
```json
{
  "success": true,
  "model_code": "M250247-P6",
  "total": 18,
  "sub_drawings": ["A-10", "B03", "DIE-10", "PH-02", "UP", ...]
}
```

### 第三步：拆出需要的子图

```
POST /split/chaitu
{
  "model_code": "M250247-P6",
  "sub_codes": "DIE-10,A-10",
  "save_to_db": false
}
```

返回：
```json
{
  "success": true,
  "message": "拆图成功",
  "dwg_path": "static/dwg/chaidan/M250247-P6_DIE-10_A-10_20250516_143022.dwg",
  "dwg_url": "http://localhost:8000/static/dwg/chaidan/M250247-P6_DIE-10_A-10_20250516_143022.dwg",
  "filename": "M250247-P6_DIE-10_A-10_20250516_143022.dwg",
  "model_code": "M250247-P6",
  "sub_codes": "DIE-10,A-10"
}
```

### 拆图并同时写入数据库

```json
{
  "model_code": "M250247-P6",
  "sub_codes": "DIE-10,A-10",
  "save_to_db": true,
  "group_uid": "550e8400-e29b-41d4-a716-446655440000",
  "no": "WJJQG202512080005"
}
```

---

## 子图编号格式说明

以下三种写法都会被识别为相同的子图：

| 写法 | 说明 |
|------|------|
| `DIE-10` | 纯编号（推荐） |
| `M250247-P6-DIE-10` | 带模具号前缀（自动去除） |
| `M250247.P6-DIE-10` | 点分格式（自动转换） |

多个子图用英文逗号分隔：`DIE-10,A-10,B03`

---

## 整合到其他项目

### 方式一：直接 HTTP 调用

把这个模块作为独立服务运行，其他项目通过 HTTP 调用接口即可。

### 方式二：直接复制代码

把以下文件复制到目标项目中即可：
- `crud.py` — 查询逻辑
- `split_router.py` — 拆图逻辑  
- `chaitu1.py` — 拆图引擎
- `db.py` — 数据库连接

调整 `db.py` 中的连接方式以适配目标项目的数据库管理方式即可。
