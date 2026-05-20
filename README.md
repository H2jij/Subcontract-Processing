# 委外加工管理系统（Subcontract Processing）

基于 RuoYi-Vue3-FastAPI 前后端分离框架开发的委外加工管理平台，实现从项目创建、供应商匹配、询价报价、选标下单到工单管理的全流程数字化管理。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + Element Plus + Vite + Pinia |
| 移动端 | UniApp + Vue 3 + TailwindCSS |
| 后端 | FastAPI + SQLAlchemy 2.0 (async) |
| 数据库 | PostgreSQL |
| 缓存 | Redis |
| 认证 | JWT |

## 环境要求

- Python >= 3.10
- Node.js >= 18
- PostgreSQL >= 14
- Redis >= 6.2

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/H2jij/Subcontract-Processing.git
cd Subcontract-Processing
```

### 2. 初始化数据库

```bash
# 创建 PostgreSQL 数据库
createdb -U postgres ruoyi_fastapi

# 导入基础表结构和菜单数据
psql -U postgres -d ruoyi_fastapi < ruoyi-fastapi-backend/sql/ruoyi-fastapi-pg.sql

# 导入委外业务表
psql -U postgres -d ruoyi_fastapi < ruoyi-fastapi-backend/sql/entrust_tables.sql

# 导入菜单配置
psql -U postgres -d ruoyi_fastapi < ruoyi-fastapi-backend/sql/entrust_menu.sql

# 导入加工工艺字典数据
psql -U postgres -d ruoyi_fastapi < ruoyi-fastapi-backend/sql/seed_process_methods.sql

# 导入角色和权限
psql -U postgres -d ruoyi_fastapi < ruoyi-fastapi-backend/sql/insert_roles.sql
psql -U postgres -d ruoyi_fastapi < ruoyi-fastapi-backend/sql/setup_roles.sql
```

### 3. 后端配置与启动

```bash
cd ruoyi-fastapi-backend

# 安装依赖
pip install -r requirements.txt

# 复制环境配置文件
cp .env.dev.example .env.dev

# 编辑 .env.dev，配置数据库和 Redis 连接信息
```

**.env.dev 关键配置项：**

```ini
# 数据库
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your_password
DB_NAME=ruoyi_fastapi

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

# 应用
APP_HOST=0.0.0.0
APP_PORT=8088
```

```bash
# 启动后端
python app.py
```

### 4. 前端配置与启动

```bash
cd ruoyi-fastapi-frontend

# 安装依赖
npm install --registry=https://registry.npmmirror.com

# 启动开发服务器
npm run dev
```

### 5. 访问系统

| 项目 | 地址 |
|------|------|
| 前端页面 | http://localhost:80 |
| 后端接口 | http://localhost:8088 |
| API 文档 | http://localhost:8088/docs |

**默认账号：** admin / admin123

## 目录结构

```
Subcontract-Processing/
├── ruoyi-fastapi-backend/          # 后端
│   ├── app.py                      # 启动入口
│   ├── server.py                   # 应用工厂
│   ├── config/                     # 配置（数据库、Redis、环境变量）
│   ├── module_entrust/             # 委外加工模块（核心业务）
│   │   ├── controller/             #   接口层
│   │   ├── service/                #   业务逻辑层
│   │   ├── entity/                 #   数据模型（ORM + VO）
│   │   └── dao/                    #   数据访问层
│   ├── module_admin/               # 系统管理模块（用户/角色/菜单/部门）
│   ├── module_ai/                  # AI 模块（对话/模型管理）
│   ├── module_generator/           # 代码生成器
│   ├── module_task/                # 定时任务
│   ├── sql/                        # 数据库脚本
│   ├── assets/font/                # 字体资源
│   ├── utils/                      # 工具类
│   ├── common/                     # 公共模块
│   ├── middlewares/                 # 中间件
│   ├── exceptions/                 # 异常定义
│   └── sub_applications/           # 子应用
│
├── ruoyi-fastapi-frontend/         # 前端
│   ├── src/
│   │   ├── api/                    # API 接口
│   │   │   └── entrust/            #   委外模块接口
│   │   ├── views/                  # 页面
│   │   │   ├── entrust/            #   委外业务页面
│   │   │   ├── system/             #   系统管理页面
│   │   │   ├── monitor/            #   系统监控页面
│   │   │   └── tool/               #   工具页面
│   │   ├── components/             # 公共组件
│   │   ├── store/                  # Pinia 状态管理
│   │   └── utils/                  # 工具函数
│   └── package.json
│
├── ruoyi-fastapi-app/              # 移动端（UniApp）
│   └── src/
│       ├── pages/                  # 页面
│       ├── api/                    # API 接口
│       └── store/                  # 状态管理
│
├── ruoyi-fastapi-test/             # 自动化测试
│   ├── common/                     # 公共测试工具
│   ├── system/                     # 系统模块测试
│   ├── monitor/                    # 监控模块测试
│   └── tool/                       # 工具模块测试
│
├── uploads/drawings/               # 图纸文件存储
└── README.md
```

## 核心功能

### 系统管理（RuoYi 框架内置）

| 功能 | 说明 |
|------|------|
| 用户管理 | 系统用户配置、密码管理 |
| 角色管理 | 角色菜单权限分配、数据范围控制 |
| 菜单管理 | 动态菜单配置、按钮级权限 |
| 部门管理 | 组织机构树（公司→部门→小组） |
| 岗位管理 | 用户职务管理 |
| 通知公告 | 系统通知发布 |
| 日志管理 | 操作日志、登录日志查询 |
| 系统监控 | 服务器状态、缓存监控 |
| AI 对话 | 集成多模型对话功能 |

### 委外加工业务（核心模块）

#### 1. 项目管理

- 创建项目，关联模具套和零件
- 零件信息：名称、数量、材质、加工要求、图纸上传（DXF 格式）
- 支持 DXF 图纸在线预览
- 项目状态流转：草稿 → 确认 → 进行中 → 完成

#### 2. 供应商管理

- 供应商基本信息维护（名称、联系人、电话、地址、地区）
- 供应商工艺能力配置（支持多种加工工艺的匹配）
- 供应商状态管理（启用/停用）

#### 3. 智能匹配

- 基于零件加工工艺自动匹配具备相应能力的供应商
- 按工艺覆盖度和地区匹配度排序推荐

#### 4. 询价管理

- 从项目零件发起询价，选择候选加工方
- 设置交期、备料情况（我方备料/加工方备料）
- 群发询价邀请给多个加工方
- 询价单按项目分组展示，支持状态标记（待报价/已报价/已截止）

#### 5. 报价管理

- 加工方收到询价邀请后查看零件清单和图纸
- 逐项填写单价、备注，提交报价
- 我方汇总对比各加工方报价

#### 6. 选标与委外工单

- 比价后选择中标方，系统自动生成委外工单
- 同一项目仅可选标一次，防止重复下单
- 工单包含：工单号（P+日期+序号）、供应商、零件清单、总金额、交期

#### 7. 委外工单管理

- 工单列表查看，按状态筛选（已下单/已接受/生产中/已交付）
- 工单详情查看
- 导出委外工单 PDF（含公司抬头、零件明细、签字栏）

#### 8. 加工方视角

- 加工方登录后查看收到的询价邀请
- 在线查看零件图纸、提交报价
- 查看自己的加工订单和状态

#### 9. 数据导出

- 询价单、报价单、工单列表支持 XLSX 导出（带样式）
- 委外工单支持 PDF 导出

#### 10. 即时沟通

- 我方与加工方在线聊天
- WebSocket 实时消息推送
- 沟通记录可追溯

#### 11. 工作台与仪表板

- 工作台：待办事项、快捷入口
- 仪表板：项目统计、询价状态汇总、数据可视化

## 业务流程

```
创建项目 → 添加零件（含图纸） → 智能匹配供应商
    ↓
发起询价（选择加工方、设交期、选备料方式）→ 群发邀请
    ↓
加工方报价 → 我方比价 → 选标（中标）
    ↓
自动生成委外工单 → 导出PDF工单 → 生产跟踪 → 交付
```

## 数据库脚本说明

`ruoyi-fastapi-backend/sql/` 目录下各脚本用途：

| 文件 | 说明 |
|------|------|
| `ruoyi-fastapi-pg.sql` | RuoYi 框架基础表（用户/角色/菜单等） |
| `entrust_tables.sql` | 委外业务表（项目/零件/供应商/询价/报价/工单） |
| `entrust_menu.sql` | 委外模块菜单配置 |
| `seed_process_methods.sql` | 加工工艺字典初始数据 |
| `insert_roles.sql` | 角色初始数据 |
| `setup_roles.sql` | 角色菜单权限配置 |
| `entrust_process_codes.sql` | 工艺编码数据 |
| `hide_menus.sql` | 隐藏不需要的菜单 |
| `add_supplier_region.sql` | 供应商地区字段 |
| `add_supplier_userid.sql` | 供应商关联用户 |
| `alter_supplier_capabilities.sql` | 供应商能力表结构调整 |

**导入顺序**：先 `ruoyi-fastapi-pg.sql`，再 `entrust_tables.sql`，然后按需导入其余脚本。

## 注意事项

- 图纸文件（.prt、.dxf）通过 `.gitignore` 排除，不会上传到仓库
- 首次运行前务必按顺序导入数据库脚本
- 生产环境请修改默认账号密码和 JWT 密钥
- 日志文件存放在 `ruoyi-fastapi-backend/logs/` 目录

## 许可证

MIT License
