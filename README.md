# AI 测试实用工具 v2.0

这是一个基于 Flask 的 Web 应用程序，旨在提供一系列与 AI 模型评估和数据处理相关的实用工具。系统包含用户管理、活动日志、文件处理以及多个核心功能模块，用于自动化处理和评估基于 AI 的任务。

## 项目架构

项目采用典型的 Flask Web 应用架构，主要组件包括：

- **`run.py`**: 应用的启动入口，负责创建 Flask 应用实例并运行开发服务器。
- **`config.py`**: 包含应用的配置信息，如密钥、数据库 URI、日志文件路径等。
- **`app/`**: 核心应用代码目录。
    - **`__init__.py`**: 应用工厂函数 `create_app()`，用于初始化 Flask 应用、数据库、登录管理器和蓝图等。
    - **`models.py`**: 定义数据库模型（使用 Flask-SQLAlchemy），包括 `User`、`UserActivityLog` 和 `ButtonClickLog`。
    - **`routes.py`**: 定义应用的路由和视图函数，处理用户请求和业务逻辑。包含一个主蓝图 `main`。
    - **`auth/`**: 认证蓝图，包含用户注册、登录、登出等相关路由和表单 (`forms.py`)。
    - **`static/`**: 存放静态文件，如 CSS、JavaScript 和图片。
    - **`templates/`**: 存放 HTML 模板文件，用于渲染页面。
        - **`admin/`**: 存放管理员后台相关的模板。
        - **`auth/`**: 存放认证相关的模板。
- **`instance/`**: 存放实例相关的文件，如 SQLite 数据库文件 (`app.db`) 和日志文件 (`app.log`)。
- **`migrations/`**: 存放数据库迁移脚本（由 Flask-Migrate 生成）。
- **`TQ/`**: 包含与特定任务（如 Prompt 工程、AI 查询）相关的工具和脚本 (`tools.py`, `PromptTemplate.json`)。
- **`ZhiBiao/`**: 包含指标计算和评估相关的脚本 (`achieve.py`)。
- **`requirements.txt`**: 列出项目所需的 Python 依赖包。

## 主要功能模块

### 1. 用户认证与管理

- **用户注册与登录**: 用户可以注册账户并登录系统。注册时可能需要特定的注册码 (`REGISTRATION_KEY`)。
- **管理员功能**:
    - **创建管理员**: 管理员可以创建新的管理员账户。
    - **用户管理**: 管理员可以查看所有用户列表，并删除用户账户。
    - **权限控制**: 使用 `@login_required` 和自定义的 `@admin_required` 装饰器进行权限控制。

### 2. 用户活动日志

- 系统会记录用户的关键活动，如登录、登出、页面访问、文件上传、按钮点击等。
- 活动日志存储在 `UserActivityLog` 表中，包含用户 ID、时间戳、操作类型、详细信息和 IP 地址。
- 管理员可以查看用户活动日志，并进行分析（例如，通过图表展示活动频率）。
- 按钮点击事件会额外记录在 `ButtonClickLog` 表中。

### 3. 文件处理与核心 AI 功能 (Function1, Function3, Function4)

这些是系统的核心功能，主要围绕 Excel 文件的处理、AI 模型调用和评估展开。

- **文件上传**: 用户可以上传 Excel 文件到服务器 (`instance/uploads/` 目录下，通常会为每个任务创建一个唯一的子目录)。
- **后台任务处理**: 文件上传后，系统会启动后台线程 (`process_task_background` 在 `app/routes.py` 中定义) 执行耗时的数据处理和 AI 评估任务。这避免了阻塞用户界面。
    - **任务状态跟踪**: 后台任务的状态（如处理中、已完成、失败）会通过一个内存中的字典 `tasks_status` 进行跟踪，并通过 `/task_status/<task_id>` API 接口暴露给前端，实现异步任务状态更新。
    - **核心处理逻辑**: 后台任务会调用 `ZhiBiao/achieve.py` 中的 `process_and_evaluate_excel` 函数以及 `TQ/tools.py` 中的相关函数。这些函数可能执行以下操作：
        - 从上传的 Excel 文件中提取特定列数据 (`extract_column_to_new_excel`)。
        - 使用预设的 Prompt 模板 (`TQ/PromptTemplate.json`) 与 AI 模型（可能是内部部署的模型或外部 API，如 OpenAI）进行交互 (`ai_prompt_query`)。
        - 对 AI 模型的输出进行评估，可能涉及多种指标（如 ROUGE 分数、相似度计算等，使用了 `sentence-transformers`）。
        - 将处理和评估结果保存到新的 Excel 文件中。
- **结果下载**: 处理完成后，用户可以从 `instance/processed_files/` 目录下载生成的 Excel 文件。

### 4. 其他辅助功能

- **连接测试 (`/test_connection`)**: 用于测试系统与外部服务（如 AI 模型 API）的连通性。
- **日志记录**: 应用使用 Flask 的日志系统 (`current_app.logger`) 将运行日志记录到 `instance/app.log` 文件中。

## 数据库设计

系统使用 SQLite 数据库，通过 Flask-SQLAlchemy ORM 进行交互。主要数据模型定义在 `app/models.py` 中：

### 1. `User` 表

存储用户信息。

| 字段名          | 类型        | 约束与说明                                       |
|-----------------|-------------|--------------------------------------------------|
| `id`            | Integer     | 主键                                             |
| `username`      | String(64)  | 用户名，唯一，索引，非空                           |
| `email`         | String(120) | 邮箱，唯一，索引，可为空                           |
| `password_hash` | String(128) | 哈希后的密码，非空                                 |
| `registered_on` | DateTime    | 注册时间，非空，默认为 `datetime.utcnow`           |
| `last_login`    | DateTime    | 最后登录时间，可为空                               |
| `is_admin`      | Boolean     | 是否为管理员，默认为 `False`                       |

- **关系**: 与 `UserActivityLog` 存在一对多关系 (`activities`)。
- **方法**:
    - `set_password(password)`: 设置并哈希用户密码。
    - `check_password(password)`: 校验用户密码。

### 2. `UserActivityLog` 表

记录用户活动日志。

| 字段名       | 类型        | 约束与说明                                                     |
|--------------|-------------|--------------------------------------------------------------|
| `id`         | Integer     | 主键                                                         |
| `user_id`    | Integer     | 外键，关联 `User.id`，非空                                     |
| `timestamp`  | DateTime    | 活动时间戳，非空，默认为 `datetime.utcnow`                     |
| `action`     | String(128) | 操作类型 (如 'login', 'upload_file')，非空                     |
| `details`    | Text        | 操作详情，可为空                                               |
| `ip_address` | String(45)  | 用户 IP 地址，可为空                                           |

- **关系**: 与 `User` 存在多对一关系 (`user`)。

### 3. `ButtonClickLog` 表

记录用户按钮点击事件。

| 字段名        | 类型        | 约束与说明                                                     |
|---------------|-------------|--------------------------------------------------------------|
| `id`          | Integer     | 主键                                                         |
| `user_id`     | Integer     | 外键，关联 `User.id`，可为空 (允许记录匿名用户点击)            |
| `button_name` | String(128) | 被点击的按钮名称/标识符，非空                                  |
| `timestamp`   | DateTime    | 点击时间戳，非空，默认为 `datetime.utcnow`                     |

- **关系**: 与 `User` 存在多对一关系。

### 数据库初始化与迁移

- 数据库使用 Flask-Migrate 进行版本控制和迁移。相关命令通常通过 Flask CLI 执行 (例如 `flask db init`, `flask db migrate`, `flask db upgrade`)。
- 首次运行时，如果 `instance/app.db` 不存在，Flask-SQLAlchemy 会根据模型定义自动创建数据库文件和表结构。

## 如何运行

1.  **克隆仓库** (如果适用)
2.  **创建并激活虚拟环境** (推荐):
    ```bash
    python -m venv venv
    source venv/bin/activate  # macOS/Linux
    # venv\Scripts\activate    # Windows
    ```
3.  **安装依赖**: 
    ```bash
    pip install -r requirements.txt
    ```
4.  **配置环境变量** (可选，但建议用于生产环境):
    - `SECRET_KEY`: 用于会话签名的密钥。
    - `DATABASE_URL`: 数据库连接字符串 (默认为 SQLite)。
    - `REGISTRATION_KEY`: 用户注册时可能需要的密钥。
    (可以将这些变量设置在 `.env` 文件中，并使用 `python-dotenv` 之类的库加载)
5.  **数据库初始化/迁移** (如果是首次运行或模型有更改):
    ```bash
    flask db init  # 如果还没有 migrations 文件夹
    flask db migrate -m "Initial migration or descriptive message"
    flask db upgrade
    ```
6.  **创建第一个管理员用户** (如果需要，可以运行 `create_first_admin.py` 脚本，或通过应用内功能创建):
    ```bash
    python create_first_admin.py
    ```
7.  **运行应用**:
    ```bash
    python run.py
    ```
    应用默认会在 `http://0.0.0.0:5001` 启动。

## 主要技术栈

- **后端**: Python, Flask
- **数据库**: SQLite (通过 Flask-SQLAlchemy)
- **用户认证**: Flask-Login
- **表单处理**: Flask-WTF
- **数据库迁移**: Flask-Migrate
- **数据处理**: Pandas, NumPy
- **AI/NLP 相关**: OpenAI (API), sentence-transformers, rouge, jieba, modelscope
- **前端**: HTML, CSS (可能使用 Bootstrap-Flask), JavaScript (用于异步任务状态更新等)

## 潜在改进点

- **后台任务管理**: 当前使用内存字典 `tasks_status` 跟踪任务状态，不适用于生产环境。可以考虑使用更健壮的方案，如 Celery + Redis/RabbitMQ。
- **错误处理与日志**: 进一步完善全局错误处理和更详细的日志记录。
- **安全性**: 对文件上传进行更严格的类型和大小校验；考虑 XSS、CSRF 等 Web 安全防护。
- **配置管理**: 对于敏感配置（如 API 密钥），应严格通过环境变量或专门的密钥管理服务管理，避免硬编码。
- **测试**: 增加单元测试和集成测试，确保代码质量和功能稳定性。
- **前端体验**: 优化前端交互，例如提供更实时的任务进度反馈。

---

本文档旨在提供对 AI 测试实用工具 v2.0 项目的全面理解。如有疑问或建议，请联系开发团队。