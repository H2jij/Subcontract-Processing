# 委外加工管理系统

基于 RuoYi-Vue3 + FastAPI 的前后端分离委外加工管理系统

## 项目简介

本系统是一个完整的委外加工管理平台，包含以下核心功能：

- **用户管理**：系统用户配置、权限管理
- **角色管理**：角色菜单权限分配、数据范围权限
- **菜单管理**：系统菜单配置、操作权限控制
- **部门管理**：组织机构管理（公司、部门、小组）
- **岗位管理**：用户职务管理
- **委外项目管理**：项目、模具套、零件管理
- **加工方管理**：供应商信息、能力管理
- **询价报价管理**：询价单创建、发送、报价、选标
- **委外工单管理**：工单生成、生产跟踪、质检
- **聊天沟通**：与加工方的即时沟通
- **AI 对话**：AI 模型管理和对话功能
- **系统监控**：服务器监控、缓存监控、日志查询
- **代码生成**：一键生成前后端代码

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue3 + Element Plus + Vite + Pinia |
| 移动端 | UniApp + Vue3 + TailwindCSS |
| 后端 | FastAPI + SQLAlchemy + PostgreSQL/MySQL |
| 缓存 | Redis |
| 认证 | OAuth2 + JWT |

## 环境要求

### 必备软件

- **Python** ≥ 3.10
- **Node.js** ≥ 18
- **MySQL** ≥ 5.7 或 **PostgreSQL**
- **Redis** ≥ 6.2
- **Git**

### 推荐工具

- 数据库连接工具（Navicat、DBeaver）
- API 测试工具（Postman、Apifox）

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/H2jij/Subcontract-Processing.git
cd Subcontract-Processing
```

### 2. 后端配置

```bash
cd ruoyi-fastapi-backend

# 安装 Python 依赖
pip install -r requirements.txt

# 配置环境变量
# 编辑 .env.dev 文件，配置数据库和 Redis 连接信息
```

**.env.dev 关键配置项：**

```ini
# 数据库配置
DATABASE_TYPE=postgresql  # 或 mysql
DB_HOST=localhost
DB_PORT=5432
DB_USER=your_username
DB_PASSWORD=your_password
DB_NAME=ruoyi_fastapi

# Redis 配置
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0

# 应用配置
APP_HOST=0.0.0.0
APP_PORT=80
```

### 3. 初始化数据库

```bash
# 方式 1：使用数据库工具运行 SQL 文件
# MySQL: sql/ruoyi-fastapi.sql
# PostgreSQL: sql/ruoyi-fastapi-pg.sql

# 方式 2：使用命令行
# MySQL:
mysql -u root -p < sql/ruoyi-fastapi.sql

# PostgreSQL:
psql -U postgres -d ruoyi_fastapi < sql/ruoyi-fastapi-pg.sql
```

### 4. 启动后端服务

```bash
cd ruoyi-fastapi-backend

# 方式 1：使用 CLI 命令（推荐）
ruoyi app run --env=dev

# 方式 2：直接运行
python app.py
```

后端启动入口：`app.py`

### 5. 前端配置

```bash
cd ruoyi-fastapi-frontend

# 安装 Node.js 依赖（使用国内镜像加速）
npm install --registry=https://registry.npmmirror.com

# 启动开发服务器
npm run dev
```

### 6. 访问系统

| 项目 | 地址 |
|------|------|
| 前端页面 | http://localhost:80 |
| 后端接口 | http://localhost:80/api |
| API 文档 | http://localhost:80/docs |

**默认账号：**
- 账号：`admin`
- 密码：`admin123`

## 目录结构

```
Subcontract-Processing/
├── ruoyi-fastapi-frontend/     # 前端项目 (Vue3)
│   ├── src/
│   │   ├── api/                # API 接口
│   │   ├── views/              # 页面视图
│   │   ├── components/         # 公共组件
│   │   ├── store/              # 状态管理
│   │   └── utils/              # 工具函数
│   ├── .env.development        # 开发环境配置
│   └── package.json
├── ruoyi-fastapi-app/          # 移动端项目 (UniApp)
│   ├── src/
│   │   ├── pages/              # 页面
│   │   ├── api/                # API 接口
│   │   └── utils/              # 工具函数
│   └── manifest.json
├── ruoyi-fastapi-backend/      # 后端项目 (FastAPI)
│   ├── app.py                  # 启动入口
│   ├── server.py               # 应用工厂
│   ├── cli/                    # 命令行工具
│   ├── module_entrust/         # 委外模块
│   │   ├── controller/         # 控制器
│   │   ├── service/            # 服务层
│   │   ├── entity/             # 实体类
│   │   └── dao/                # 数据访问层
│   ├── module_admin/           # 系统管理模块
│   ├── sql/                    # SQL 脚本
│   ├── .env.dev                # 开发环境配置
│   └── requirements.txt
├── sql/                        # 数据库脚本
│   ├── ruoyi-fastapi.sql       # MySQL 建表脚本
│   └── ruoyi-fastapi-pg.sql    # PostgreSQL 建表脚本
├── docker-compose.my.yml       # Docker Compose MySQL 配置
├── docker-compose.pg.yml       # Docker Compose PostgreSQL 配置
└── README.md
```

## 核心功能说明

### 委外业务流程

1. **项目管理**：创建项目 → 添加模具套 → 添加零件
2. **询价管理**：创建询价单 → 选择加工方 → 发送邀请
3. **报价管理**：加工方收到邀请 → 查看询价详情 → 提交报价
4. **选标管理**：我方查看报价 → 选择中标方 → 生成委外工单
5. **工单管理**：工单分配 → 生产跟踪 → 质量检验 → 交付确认

### 权限控制

- 支持角色权限、部门权限、数据范围权限
- 支持动态菜单加载
- 支持按钮级权限控制

## Docker 部署

### MySQL 版本

```bash
docker compose -f docker-compose.my.yml up -d --build
```

### PostgreSQL 版本

```bash
docker compose -f docker-compose.pg.yml up -d --build
```

## 常见问题

### 1. 端口冲突

如果 80 端口被占用，修改 `.env.dev` 中的 `APP_PORT` 配置。

### 2. 数据库连接失败

- 确认数据库服务已启动
- 检查 `.env.dev` 中的数据库连接配置
- 确认数据库已创建

### 3. Redis 连接失败

- 确认 Redis 服务已启动
- 检查 `.env.dev` 中的 Redis 连接配置

### 4. 前端依赖安装失败

使用国内镜像源：
```bash
npm install --registry=https://registry.npmmirror.com
```

## 项目结构文档

详细的目录结构和功能说明请参考 [PROJECT_STRUCTURE.md](./PROJECT_STRUCTURE.md)

## 注意事项

- 图纸文件（.prt、.dxf）已排除在 Git 管理之外，不会上传到仓库
- 首次运行前请务必初始化数据库
- 建议使用 PostgreSQL 数据库以获得更好的性能
- 生产环境请修改默认账号密码

## 开发规范

- 后端代码使用 Ruff 进行代码检查
- 遵循 PEP 8 编码规范
- 前端使用 ESLint 进行代码检查

## 许可证

MIT License