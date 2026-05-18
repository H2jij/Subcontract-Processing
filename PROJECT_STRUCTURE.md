# RuoYi-Vue3-FastAPI 项目结构文档

## 一、项目概述

基于若依框架迁移的企业级前后端分离快速开发平台：

- **前端**：Vue3 + Element Plus
- **移动端**：UniApp + Vue3 + TailwindCSS
- **后端**：FastAPI + SQLAlchemy + Redis + JWT

## 二、完整目录结构

```
RuoYi-Vue3-FastAPI/
├── .github/                                   # GitHub CI/CD 配置
│   ├── workflows/
│   │   ├── playwright.yml                     # Playwright 自动化测试
│   │   └── ruff.yml                           # Ruff 代码检查
│   └── FUNDING.yml                            # 赞助配置
├── ruoyi-fastapi-frontend/                    # Web前端 (Vue3 + Element Plus)
│   ├── src/
│   │   ├── api/                               # API 接口定义
│   │   ├── assets/                            # 静态资源
│   │   ├── components/                        # 公共组件
│   │   ├── directive/                         # 自定义指令
│   │   ├── layout/                            # 布局组件
│   │   ├── router/                            # 路由配置
│   │   ├── store/                             # 状态管理 (Vuex)
│   │   ├── utils/                             # 工具函数
│   │   ├── views/                             # 页面视图
│   │   ├── App.vue                            # 根组件
│   │   ├── main.js                            # 入口文件
│   │   ├── permission.js                      # 权限控制
│   │   └── settings.js                        # 全局设置
│   ├── vite/                                  # Vite 插件配置
│   ├── bin/                                   # 脚本文件
│   ├── public/                                # 静态资源目录
│   ├── html/                                  # HTML 模板
│   ├── .env.*                                 # 环境配置文件
│   ├── vite.config.js                         # Vite 配置
│   └── package.json                           # 依赖配置
├── ruoyi-fastapi-app/                         # 移动端 (UniApp)
│   ├── src/
│   │   ├── api/                               # API 接口
│   │   ├── pages/                             # 页面组件
│   │   ├── plugins/                           # 插件
│   │   ├── static/                            # 静态资源
│   │   ├── store/                             # 状态管理
│   │   ├── utils/                             # 工具函数
│   │   ├── App.vue
│   │   ├── main.ts
│   │   ├── pages.json                         # UniApp 页面路由
│   │   └── manifest.json                      # 应用配置
│   └── [构建配置]                             # vite.config.ts, tailwind.config.ts 等
├── ruoyi-fastapi-backend/                     # 后端服务 (FastAPI)
│   ├── cli/                                   # 命令行工具
│   ├── common/                                # 公共模块
│   ├── config/                                # 配置模块
│   ├── exceptions/                            # 异常处理
│   ├── middlewares/                           # 中间件
│   ├── module_admin/                          # 系统管理模块
│   ├── module_entrust/                        # 业务委托模块
│   ├── module_task/                           # 任务调度模块
│   ├── sub_applications/                      # 子应用
│   ├── tests/                                 # 测试用例
│   ├── utils/                                 # 工具函数
│   ├── alembic/                               # 数据库迁移
│   ├── assets/                                # 资源文件
│   ├── app.py                                 # 启动入口
│   ├── server.py                              # 应用工厂
│   └── .env.*                                 # 环境配置
├── CHANGELOG.md                               # 版本变更记录
├── LICENSE                                    # 许可证
├── README.md                                  # 项目说明
├── docker-compose.my.yml                      # Docker Compose (MySQL)
└── docker-compose.pg.yml                      # Docker Compose (PostgreSQL)
```

---

## 三、前端项目 (`ruoyi-fastapi-frontend/`)

### 3.1 根目录配置

| 文件 | 功能说明 |
|------|----------|
| `package.json` | 依赖配置与脚本命令 |
| `vite.config.js` | Vite 构建配置 |
| `.env.development` | 开发环境变量 |
| `.env.production` | 生产环境变量 |
| `.env.staging` | 测试环境变量 |
| `.env.docker` | Docker 环境变量 |
| `Dockerfile` | Docker 构建配置 |

### 3.2 源码目录 (`src/`)

#### 3.2.1 API 接口 (`api/`)

| 目录/文件 | 功能说明 |
|-----------|----------|
| `api/login.js` | 登录认证接口 |
| `api/menu.js` | 菜单接口 |
| `api/system/user.js` | 用户管理接口 |
| `api/system/role.js` | 角色管理接口 |
| `api/system/menu.js` | 菜单管理接口 |
| `api/system/dept.js` | 部门管理接口 |
| `api/system/post.js` | 岗位管理接口 |
| `api/system/dict/` | 字典管理接口 |
| `api/system/config.js` | 参数配置接口 |
| `api/system/notice.js` | 通知公告接口 |
| `api/monitor/` | 监控模块接口（服务器、缓存、日志等） |
| `api/tool/gen.js` | 代码生成接口 |
| `api/ai/` | AI 模块接口 |
| `api/entrust/` | 委托业务接口 |

#### 3.2.2 静态资源 (`assets/`)

| 目录/文件 | 功能说明 |
|-----------|----------|
| `assets/styles/` | 全局样式文件 |
| `assets/images/` | 图片资源 |
| `assets/icons/` | 图标资源 |
| `assets/logo/` | Logo 资源 |
| `assets/404_images/` | 404 页面图片 |
| `assets/401_images/` | 401 页面图片 |

#### 3.2.3 公共组件 (`components/`)

| 文件 | 功能说明 |
|------|----------|
| `Breadcrumb/index.vue` | 面包屑导航 |
| `Hamburger/index.vue` | 菜单折叠按钮 |
| `Pagination/index.vue` | 分页组件 |
| `HeaderSearch/index.vue` | 头部搜索 |
| `IconSelect/index.vue` | 图标选择器 |
| `FileUpload/index.vue` | 文件上传 |
| `ImageUpload/index.vue` | 图片上传 |
| `ImagePreview/index.vue` | 图片预览 |
| `Editor/index.vue` | 富文本编辑器 |
| `Crontab/index.vue` | Cron 表达式编辑器 |
| `DictTag/index.vue` | 字典标签 |
| `SizeSelect/index.vue` | 尺寸选择 |
| `Screenfull/index.vue` | 全屏切换 |
| `RightToolbar/index.vue` | 右侧工具栏 |
| `ParentView/index.vue` | 父视图组件 |
| `TopNav/index.vue` | 顶部导航 |
| `iFrame/index.vue` | iframe 封装 |
| `RuoYi/` | RuoYi 官方组件 |
| `SvgIcon/index.vue` | SVG 图标组件 |
| `SvgIcon/svgicon.js` | SVG 图标工具 |

#### 3.2.4 自定义指令 (`directive/`)

| 文件 | 功能说明 |
|------|----------|
| `directive/index.js` | 指令入口 |
| `directive/permission/hasRole.js` | 角色权限指令 |
| `directive/permission/hasPermi.js` | 权限指令 |
| `directive/common/copyText.js` | 复制文本指令 |

#### 3.2.5 布局组件 (`layout/`)

| 文件 | 功能说明 |
|------|----------|
| `layout/index.vue` | 布局入口 |
| `layout/components/AppMain.vue` | 主内容区 |
| `layout/components/Sidebar/index.vue` | 侧边栏 |
| `layout/components/Sidebar/SidebarItem.vue` | 侧边栏菜单项 |
| `layout/components/Sidebar/Logo.vue` | Logo 组件 |
| `layout/components/TopBar/index.vue` | 顶部栏 |
| `layout/components/TagsView/index.vue` | 标签页 |
| `layout/components/Settings/index.vue` | 设置面板 |
| `layout/components/Copyright/index.vue` | 版权信息 |
| `layout/components/Navbar.vue` | 导航栏 |

#### 3.2.6 路由配置 (`router/`)

| 文件 | 功能说明 |
|------|----------|
| `router/index.js` | 路由配置入口 |

#### 3.2.7 状态管理 (`store/`)

| 文件 | 功能说明 |
|------|----------|
| `store/index.js` | Vuex 入口 |
| `store/modules/app.js` | 应用状态 |
| `store/modules/user.js` | 用户状态 |
| `store/modules/permission.js` | 权限状态 |
| `store/modules/settings.js` | 设置状态 |
| `store/modules/tagsView.js` | 标签页状态 |
| `store/modules/dict.js` | 字典状态 |

#### 3.2.8 工具函数 (`utils/`)

| 文件 | 功能说明 |
|------|----------|
| `utils/index.js` | 工具入口 |
| `utils/auth.js` | 认证工具 |
| `utils/request.js` | HTTP 请求封装 |
| `utils/permission.js` | 权限处理 |
| `utils/dict.js` | 字典工具 |
| `utils/errorCode.js` | 错误码映射 |
| `utils/ruoyi.js` | RuoYi 工具 |
| `utils/theme.js` | 主题工具 |
| `utils/scroll-to.js` | 滚动工具 |
| `utils/validate.js` | 校验工具 |
| `utils/dynamicTitle.js` | 动态标题 |
| `utils/jsencrypt.js` | JSEncrypt 加密 |
| `utils/transportCrypto.js` | 传输加密 |
| `utils/transportCryptoPolicy.js` | 加密策略 |
| `utils/generator/` | 代码生成器 |

#### 3.2.9 页面视图 (`views/`)

| 目录/文件 | 功能说明 |
|-----------|----------|
| `views/login.vue` | 登录页 |
| `views/register.vue` | 注册页 |
| `views/redirect/index.vue` | 重定向页 |
| `views/dashboard/index.vue` | 首页仪表盘 |
| `views/system/user/index.vue` | 用户管理 |
| `views/system/user/profile/` | 用户个人中心 |
| `views/system/role/index.vue` | 角色管理 |
| `views/system/menu/index.vue` | 菜单管理 |
| `views/system/dept/index.vue` | 部门管理 |
| `views/system/post/index.vue` | 岗位管理 |
| `views/system/dict/index.vue` | 字典管理 |
| `views/system/config/index.vue` | 参数配置 |
| `views/system/notice/index.vue` | 通知公告 |
| `views/monitor/server/index.vue` | 服务器监控 |
| `views/monitor/cache/index.vue` | 缓存监控 |
| `views/monitor/logininfor/index.vue` | 登录日志 |
| `views/monitor/operlog/index.vue` | 操作日志 |
| `views/monitor/job/index.vue` | 定时任务 |
| `views/monitor/transportCrypto/index.vue` | 传输加密监控 |
| `views/tool/gen/index.vue` | 代码生成 |
| `views/tool/build/index.vue` | 在线构建器 |
| `views/tool/swagger/index.vue` | Swagger 文档 |
| `views/ai/model/index.vue` | AI 模型管理 |
| `views/ai/chat/index.vue` | AI 对话 |
| `views/entrust/` | 委托业务模块 |

### 3.3 Vite 插件 (`vite/`)

| 文件 | 功能说明 |
|------|----------|
| `vite/plugins/index.js` | 插件入口 |
| `vite/plugins/svg-icon.js` | SVG 图标插件 |
| `vite/plugins/setup-extend.js` | setup 扩展 |
| `vite/plugins/auto-import.js` | 自动导入 |
| `vite/plugins/compression.js` | Gzip 压缩 |

### 3.4 脚本文件 (`bin/`)

| 文件 | 功能说明 |
|------|----------|
| `bin/run-web.bat` | 运行 Web |
| `bin/build.bat` | 构建脚本 |
| `bin/package.bat` | 打包脚本 |
| `bin/nginx.dockermy.conf` | Nginx MySQL 配置 |
| `bin/nginx.dockerpg.conf` | Nginx PostgreSQL 配置 |

### 3.5 静态资源目录 (`public/`)

| 文件 | 功能说明 |
|------|----------|
| `public/favicon.ico` | 网站图标 |

### 3.6 HTML 模板 (`html/`)

| 文件 | 功能说明 |
|------|----------|
| `html/ie.html` | IE 浏览器兼容页面 |

---

## 四、移动端应用 (`ruoyi-fastapi-app/`)

### 4.1 根目录配置

| 文件 | 功能说明 |
|------|----------|
| `package.json` | 依赖配置 |
| `vite.config.ts` | Vite 配置 |
| `tailwind.config.ts` | TailwindCSS 配置 |
| `tsconfig.json` | TypeScript 配置 |
| `index.html` | HTML 入口 |
| `platform.ts` | 平台配置 |
| `postcss.config.ts` | PostCSS 配置 |

### 4.2 源码目录 (`src/`)

#### 4.2.1 API 接口 (`api/`)

| 文件 | 功能说明 |
|------|----------|
| `api/login.js` | 登录注册接口 |
| `api/system/user.js` | 用户接口 |
| `api/system/dict/data.js` | 字典数据接口 |
| `api/system/dict/type.js` | 字典类型接口 |

#### 4.2.2 页面组件 (`pages/`)

| 文件 | 功能说明 |
|------|----------|
| `pages/login.vue` | 登录页 |
| `pages/register.vue` | 注册页 |
| `pages/index.vue` | 首页 |
| `pages/work/index.vue` | 工作台 |
| `pages/mine/index.vue` | 个人中心 |
| `pages/mine/avatar/index.vue` | 修改头像 |
| `pages/mine/info/index.vue` | 个人信息 |
| `pages/mine/info/edit.vue` | 编辑资料 |
| `pages/mine/pwd/index.vue` | 修改密码 |
| `pages/mine/setting/index.vue` | 设置 |
| `pages/mine/help/index.vue` | 帮助 |
| `pages/mine/about/index.vue` | 关于 |
| `pages/common/agreement/index.vue` | 用户协议 |
| `pages/common/privacy/index.vue` | 隐私政策 |
| `pages/common/webview/index.vue` | 网页浏览 |
| `pages/common/textview/index.vue` | 文本浏览 |

#### 4.2.3 插件 (`plugins/`)

| 文件 | 功能说明 |
|------|----------|
| `plugins/index.js` | 插件入口 |
| `plugins/auth.js` | 认证插件 |
| `plugins/modal.js` | 弹窗插件 |
| `plugins/tab.js` | TabBar 插件 |

#### 4.2.4 静态资源 (`static/`)

| 文件/目录 | 功能说明 |
|-----------|----------|
| `static/images/banner/` | 轮播图 |
| `static/images/tabbar/` | TabBar 图标 |
| `static/images/profile.jpg` | 默认头像 |
| `static/logo.png` | Logo |
| `static/favicon.ico` | 图标 |

#### 4.2.5 状态管理 (`store/`)

| 文件 | 功能说明 |
|------|----------|
| `store/index.js` | 状态管理入口 |
| `store/modules/user.js` | 用户状态 |
| `store/modules/dict.js` | 字典状态 |
| `store/modules/config.js` | 配置状态 |

#### 4.2.6 工具函数 (`utils/`)

| 文件 | 功能说明 |
|------|----------|
| `utils/auth.js` | 认证工具 |
| `utils/common.js` | 通用工具 |
| `utils/constant.js` | 常量定义 |
| `utils/dict.js` | 字典工具 |
| `utils/errorCode.js` | 错误码 |
| `utils/permission.js` | 权限工具 |
| `utils/request.js` | 请求封装 |
| `utils/storage.js` | 存储工具 |
| `utils/transportCrypto.js` | 传输加密 |
| `utils/transportCryptoPolicy.js` | 加密策略 |
| `utils/transportForge.js` | Forge 加密 |
| `utils/upload.js` | 上传工具 |
| `utils/validate.js` | 校验工具 |

---

## 五、后端服务 (`ruoyi-fastapi-backend/`)

### 5.1 启动文件

| 文件 | 功能说明 |
|------|----------|
| `app.py` | 启动入口 |
| `server.py` | 应用工厂 |

### 5.2 命令行工具 (`cli/`)

#### 5.2.1 核心组件 (`cli/core/`)

| 文件 | 功能说明 |
|------|----------|
| `app_builder.py` | 应用构建器 |
| `completion_dispatcher.py` | 命令补全分发器 |
| `context_factory.py` | 上下文工厂 |
| `execution.py` | 执行器 |

#### 5.2.2 命令分组 (`cli/groups/`)

| 目录 | 功能说明 |
|------|----------|
| `app/` | 应用管理命令 |
| `cache/` | 缓存管理命令 |
| `config/` | 配置管理命令 |
| `crypto/` | 加密管理命令 |
| `db/` | 数据库管理命令 |
| `dev/` | 开发工具命令 |
| `gen/` | 代码生成命令 |
| `job/` | 任务调度命令 |
| `ops/` | 运维管理命令 |

#### 5.2.3 运行时服务 (`cli/runtime/`)

| 目录 | 功能说明 |
|------|----------|
| `app/` | 应用运行时 |
| `cache/` | 缓存运行时 |
| `config/` | 配置运行时 |
| `crypto/` | 加密运行时 |
| `db/` | 数据库运行时 |
| `dev/` | 开发运行时 |
| `gen/` | 代码生成运行时 |
| `job/` | 任务运行时 |
| `ops/` | 运维运行时 |

#### 5.2.4 终端 UI (`cli/tui/`)

| 目录 | 功能说明 |
|------|----------|
| `actions/` | 动作定义 |
| `adapters/` | 适配器 |
| `copy/` | 复制操作 |
| `screens/` | 屏幕组件 |
| `widgets/` | 小部件 |

#### 5.2.5 向导流程 (`cli/wizard/`)

| 文件/目录 | 功能说明 |
|-----------|----------|
| `flows/` | 向导流程定义 |
| `base.py` | 基础类 |
| `commands.py` | 命令定义 |
| `prompts.py` | 提示组件 |
| `presenters.py` | 展示器 |

#### 5.2.6 命令补全 (`cli/completion/`)

| 文件 | 功能说明 |
|------|----------|
| `commands.py` | 补全命令 |
| `controller.py` | 控制器 |
| `doctor.py` | 诊断工具 |
| `installers.py` | 安装器 |
| `providers.py` | 提供器 |
| `shells.py` | Shell 支持 |

#### 5.2.7 元数据 (`cli/metadata/`)

| 文件 | 功能说明 |
|------|----------|
| `command_specs.py` | 命令规范 |
| `option_specs.py` | 选项规范 |
| `risk_specs.py` | 风险规范 |

#### 5.2.8 其他文件

| 文件 | 功能说明 |
|------|----------|
| `cli/main.py` | CLI 入口 |
| `cli/bootstrap.py` | 启动引导 |
| `cli/context.py` | 上下文管理 |
| `cli/guards.py` | 安全守卫 |
| `cli/output.py` | 输出格式化 |
| `cli/exit_codes.py` | 退出码定义 |
| `cli/utils.py` | 工具函数 |

### 5.3 公共模块 (`common/`)

| 文件/目录 | 功能说明 |
|-----------|----------|
| `common/constant.py` | 常量定义 |
| `common/enums.py` | 枚举定义 |
| `common/router.py` | 路由注册 |
| `common/vo.py` | 视图对象 |
| `common/context.py` | 请求上下文 |
| `common/annotation/` | 自定义注解 |
| `common/aspect/` | AOP 切面 |

### 5.4 配置模块 (`config/`)

| 文件 | 功能说明 |
|------|----------|
| `config/env.py` | 环境配置 |
| `config/database.py` | 数据库配置 |
| `config/get_db.py` | 数据库连接 |
| `config/get_redis.py` | Redis 连接 |
| `config/get_scheduler.py` | 调度器配置 |

### 5.5 中间件 (`middlewares/`)

| 文件 | 功能说明 |
|------|----------|
| `middlewares/handle.py` | 中间件注册 |
| `middlewares/cors_middleware.py` | 跨域处理 |
| `middlewares/context_middleware.py` | 上下文注入 |
| `middlewares/gzip_middleware.py` | Gzip 压缩 |
| `middlewares/trace_middleware/` | 链路追踪 |
| `middlewares/transport_crypto_middleware.py` | 传输加密 |
| `middlewares/demo_mode_middleware.py` | 演示模式 |

### 5.6 系统管理模块 (`module_admin/`)

#### 5.6.1 Controller 层

| 文件 | 功能说明 |
|------|----------|
| `login_controller.py` | 登录认证 |
| `user_controller.py` | 用户管理 |
| `role_controller.py` | 角色管理 |
| `menu_controller.py` | 菜单管理 |
| `dept_controller.py` | 部门管理 |
| `post_controller.py` | 岗位管理 |
| `dict_controller.py` | 字典管理 |
| `config_controller.py` | 参数配置 |
| `job_controller.py` | 定时任务 |
| `log_controller.py` | 日志管理 |
| `notice_controller.py` | 通知公告 |
| `cache_controller.py` | 缓存管理 |
| `server_controller.py` | 服务器监控 |
| `captcha_controller.py` | 验证码 |
| `online_controller.py` | 在线用户 |
| `transport_crypto_controller.py` | 传输加密 |

#### 5.6.2 Service 层

| 文件 | 功能说明 |
|------|----------|
| `login_service.py` | 登录业务 |
| `user_service.py` | 用户业务 |
| `role_service.py` | 角色业务 |
| `menu_service.py` | 菜单业务 |
| `dept_service.py` | 部门业务 |
| `job_service.py` | 任务业务 |
| `log_service.py` | 日志业务 |
| `dict_service.py` | 字典业务 |
| `cache_service.py` | 缓存业务 |
| `transport_crypto_service.py` | 加密业务 |

#### 5.6.3 DAO 层

| 文件 | 功能说明 |
|------|----------|
| `user_dao.py` | 用户数据访问 |
| `role_dao.py` | 角色数据访问 |
| `menu_dao.py` | 菜单数据访问 |
| `dept_dao.py` | 部门数据访问 |
| `dict_dao.py` | 字典数据访问 |
| `job_dao.py` | 任务数据访问 |
| `log_dao.py` | 日志数据访问 |

#### 5.6.4 Entity 层

**DO（数据库实体）**：

| 文件 | 对应表 |
|------|--------|
| `user_do.py` | sys_user |
| `role_do.py` | sys_role |
| `menu_do.py` | sys_menu |
| `dept_do.py` | sys_dept |
| `dict_do.py` | sys_dict |
| `job_do.py` | sys_job |
| `log_do.py` | sys_log |

**VO（视图对象）**：

| 文件 | 功能说明 |
|------|----------|
| `user_vo.py` | 用户视图 |
| `role_vo.py` | 角色视图 |
| `menu_vo.py` | 菜单视图 |
| `login_vo.py` | 登录视图 |
| `common_vo.py` | 通用视图 |

### 5.7 业务委托模块 (`module_entrust/`)

| 文件 | 功能说明 |
|------|----------|
| `controller/chat_controller.py` | 聊天接口 |
| `controller/inquiry_controller.py` | 询价接口 |
| `controller/project_controller.py` | 项目接口 |
| `controller/supplier_controller.py` | 供应商接口 |
| `service/chat_service.py` | 聊天业务 |
| `service/inquiry_service.py` | 询价业务 |
| `service/match_service.py` | 匹配业务 |
| `service/project_service.py` | 项目业务 |
| `service/supplier_service.py` | 供应商业务 |

### 5.8 工具函数 (`utils/`)

| 文件 | 功能说明 |
|------|----------|
| `utils/response_util.py` | 响应封装 |
| `utils/log_util.py` | 日志工具 |
| `utils/pwd_util.py` | 密码加密 |
| `utils/crypto_util.py` | 加密工具 |
| `utils/transport_crypto_util.py` | 传输加密 |
| `utils/page_util.py` | 分页工具 |
| `utils/string_util.py` | 字符串工具 |
| `utils/upload_util.py` | 上传工具 |
| `utils/excel_util.py` | Excel 工具 |
| `utils/cron_util.py` | Cron 工具 |
| `utils/ai_util.py` | AI 工具 |

### 5.9 测试用例 (`tests/`)

| 目录 | 功能说明 |
|------|----------|
| `tests/cli/` | CLI 测试 |
| `tests/cli/root/` | 根命令测试 |
| `tests/cli/core/` | 核心组件测试 |
| `tests/cli/runtime/` | 运行时测试 |
| `tests/cli/tui/` | TUI 测试 |
| `tests/cli/wizard/` | 向导测试 |
| `tests/cli/completion/` | 补全测试 |

### 5.10 数据库迁移 (`alembic/`)

| 文件 | 功能说明 |
|------|----------|
| `alembic/env.py` | 环境配置 |
| `alembic/script.py.mako` | 脚本模板 |
| `alembic.ini` | 配置文件 |

### 5.11 异常处理 (`exceptions/`)

| 文件 | 功能说明 |
|------|----------|
| `exceptions/exception.py` | 自定义异常定义 |
| `exceptions/handle.py` | 全局异常处理器 |

### 5.12 子应用 (`sub_applications/`)

| 文件 | 功能说明 |
|------|----------|
| `sub_applications/handle.py` | 子应用挂载入口 |
| `sub_applications/staticfiles.py` | 静态文件服务配置 |

### 5.13 任务调度模块 (`module_task/`)

| 文件 | 功能说明 |
|------|----------|
| `module_task/__init__.py` | 模块初始化 |
| `module_task/scheduler_test.py` | 调度器测试 |

### 5.14 资源文件 (`assets/`)

| 文件 | 功能说明 |
|------|----------|
| `assets/font/Arial.ttf` | 字体文件 |

---

## 六、技术架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        前端层                                      │
│  ┌─────────────────────┐  ┌──────────────────────────────────┐   │
│  │   Vue3 Frontend     │  │      UniApp Mobile               │   │
│  │  (Element Plus)     │  │   (Vue3 + TailwindCSS)          │   │
│  └──────────┬──────────┘  └────────────────┬─────────────────┘   │
└─────────────┼───────────────────────────────┼─────────────────────┘
              │                               │
              ▼                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      传输层 (加密通信)                               │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        后端层 (FastAPI)                             │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────────┐   │
│  │ Controller  │→│   Service   │→│          DAO              │   │
│  │ (路由控制)  │  │ (业务逻辑)  │  │ (数据访问)               │   │
│  └─────────────┘  └─────────────┘  └───────────┬──────────────┘   │
│       │                  │                      │                  │
│       ▼                  ▼                      ▼                  │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────────┐   │
│  │ Middleware  │  │  Exception  │  │         Utils           │   │
│  │ (中间件)    │  │  (异常处理) │  │ (工具层)                 │   │
│  └─────────────┘  └─────────────┘  └──────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
       PostgreSQL       Redis           Scheduler
     (业务数据)      (缓存/会话)      (定时任务)
```

---

## 七、核心特性

| 特性类别 | 说明 |
|----------|------|
| **安全特性** | JWT 认证、传输加密、RBAC 权限控制、数据权限隔离 |
| **技术特性** | 异步支持、定时任务、Redis 缓存、日志聚合、代码生成 |
| **架构特性** | 前后端分离、分层架构、模块化设计、自动路由注册 |
| **部署特性** | Docker 支持、多环境配置、CLI 管理工具 |

---

## 八、启动命令

### 前端
```bash
cd ruoyi-fastapi-frontend
npm install
npm run dev
```

### 移动端
```bash
cd ruoyi-fastapi-app
pnpm install
pnpm run dev:h5        # H5
pnpm run dev:mp-weixin # 微信小程序
```

### 后端
```bash
cd ruoyi-fastapi-backend
pip install -r requirements.txt
ruoyi app run --env=dev
```