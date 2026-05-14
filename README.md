# K 线图形态识别系统项目说明

这份文档是给零基础同学阅读的项目学习手册。它会从“这个项目是干什么的”开始，逐步讲清楚目录结构、前端和后端怎么配合、数据库怎么保存数据、模型推理怎么接入、行情中心怎么取数、回测分析怎么计算，以及你以后想改功能应该去看哪些文件。

一句话理解这个项目：

> 用户登录系统后，可以上传一张 K 线图，或者输入股票代码和日期让系统自动生成 K 线图；FastAPI 业务后端负责保存图片、调用远程 AutoDL 模型服务识别形态、把结果写入 SQLite 数据库，再把结果返回给 Streamlit 前端展示；系统还支持行情查看、股票详情、历史记录管理、用户管理和轻量级回测验证。

完整链路可以概括为：

```text
浏览器用户
  -> Streamlit 前端
  -> FastAPI 业务后端
  -> AutoDL FastAPI 模型服务 /predict
  -> SQLite + outputs 图片目录
  -> 页面展示、行情分析、历史记录、回测验证
```

---

## 1. 项目整体目标

这个项目做的是一个 K 线图形态识别系统，当前主要支持 8 类功能：

1. 用户注册、登录、退出和个人密码修改。
2. 管理员创建用户、维护用户角色和状态、删除用户及其识别记录。
3. 查看行情中心，包括指数行情、市场涨跌分布、个股实时行情和股票详情。
4. 上传本地 K 线图图片并识别形态。
5. 输入股票代码、日期区间和窗口大小，自动拉取行情数据并生成 K 线图，再识别形态。
6. 保存每次识别记录，支持历史记录查询、详情查看和删除管理。
7. 根据识别记录后续几个交易日的涨跌表现，做轻量级回测验证。
8. 通过独立部署在 AutoDL 上的模型服务加载 Qwen2.5-VL + LoRA 完成图像推理。

系统目前支持的识别标签包括：

| 标签 | 含义 | 信号方向 |
| --- | --- | --- |
| 头肩顶 | 顶部反转形态 | 偏空 |
| 头肩底 | 底部反转形态 | 偏多 |
| 双顶 | 两个相近高点形成顶部 | 偏空 |
| 双底 | 两个相近低点形成底部 | 偏多 |
| 上升三角形 | 高点趋平、低点抬高 | 偏多 |
| 下降三角形 | 低点趋平、高点下移 | 偏空 |
| 无明显形态 | 未识别出明确目标形态 | 中性 |

---

## 2. 技术栈怎么理解

这个项目虽然有“前端”和“后端”，但前后端都主要用 Python 写。

| 技术 | 在项目里的角色 | 新手可以这样理解 |
| --- | --- | --- |
| Streamlit | 前端页面 | 做网页界面，负责按钮、表单、图片、图表和结果展示 |
| FastAPI | 业务后端 | 提供 HTTP API，接收前端请求，组织业务逻辑 |
| SQLite | 本地数据库 | 一个 `.sqlite3` 文件，保存用户和识别记录 |
| requests | HTTP 调用 | 前端调用业务后端，业务后端调用远程模型服务 |
| AkShare | 行情数据来源 | 拉取 A 股实时行情、指数行情、历史 K 线和分钟行情 |
| pandas | 表格数据处理 | 处理 OHLCV 行情表格、历史明细和回测序列 |
| mplfinance | K 线图绘制 | 把行情表格画成蜡烛图图片，供模型识别 |
| Plotly | 交互式图表 | 股票详情页展示分时图、日 K、周 K、月 K，可滚轮缩放 |
| Pillow | 图片处理 | 把生成的图片缩放到模型需要的尺寸 |
| Transformers + PEFT | 模型服务 | 在 AutoDL 推理服务里加载 Qwen2.5-VL 和 LoRA |
| python-multipart | 文件上传 | FastAPI 接收上传图片和模型服务接收推理图片 |

---

## 3. 整体架构

```mermaid
flowchart LR
    A[浏览器] --> B[Streamlit 前端]
    B -->|HTTP API| C[FastAPI 业务后端]
    C --> D[(SQLite 数据库)]
    C --> E[outputs 图片目录]
    C --> F[AkShare 行情数据]
    C --> G[AutoDL FastAPI 模型服务]
    G --> H[Qwen2.5-VL 基座模型 + LoRA]
```

需要特别分清两个“后端”：

| 后端 | 文件入口 | 作用 |
| --- | --- | --- |
| 业务后端 | `backend/main.py` | 给 Streamlit 调用，负责登录鉴权、业务流程、数据库、图片、行情、回测 |
| 模型推理后端 | `deployment/autodl_fastapi/app.py` | 独立部署在 AutoDL 等 GPU 机器上，真正加载 Qwen2.5-VL + LoRA |

也就是说，主项目本地启动后，通常是：

```text
浏览器
  -> Streamlit
  -> 本地 FastAPI 业务后端
  -> 远程 AutoDL 模型服务 /predict
```

这个架构可以理解为“基于 Streamlit + FastAPI 的前后端分离式 Python Web 架构”，并额外拆出了独立的远程 AI 推理服务。

---

## 4. 目录结构说明

项目根目录下的重要内容如下：

```text
klineSystem/
├─ streamlit_app.py                 # Streamlit 启动入口，只调用 frontend.app.main()
├─ requirements.txt                 # 本地业务系统运行所需依赖
├─ README.md                        # 当前这份说明文档
│
├─ frontend/                        # Streamlit 前端
│  ├─ app.py                        # 前端总入口，负责选择当前页面并渲染
│  ├─ shared.py                     # 前端公共函数：API 调用、状态、样式、通用组件
│  └─ pages/                        # 各个页面的具体实现
│     ├─ auth.py                    # 登录、注册入口页
│     ├─ home.py                    # 首页，展示统计、状态、最近记录
│     ├─ market.py                  # 行情中心页
│     ├─ stock_detail.py            # 股票详情页，隐藏在导航中，由行情中心跳转
│     ├─ upload.py                  # 上传 K 线图识别页
│     ├─ generate.py                # 自动生成 K 线图并识别页
│     ├─ records.py                 # 历史识别记录页，支持查询、详情和删除
│     ├─ backtest.py                # 回测分析页
│     ├─ profile.py                 # 个人中心页，修改密码
│     └─ users.py                   # 用户管理页，仅管理员可见
│
├─ backend/                         # FastAPI 业务后端
│  ├─ main.py                       # 后端入口，创建 app、挂路由、挂静态资源、初始化数据库
│  ├─ auth.py                       # 解析 Authorization Token，提供当前用户依赖
│  ├─ config.py                     # 配置、目录发现、环境变量读取
│  ├─ schemas.py                    # Pydantic 请求/响应结构
│  ├─ routes/                       # API 路由层
│  │  ├─ auth.py                    # 注册、登录、当前用户、修改密码
│  │  ├─ users.py                   # 管理员用户管理接口
│  │  ├─ market.py                  # 行情中心和股票详情接口
│  │  ├─ context.py                 # 表单日期、窗口大小等上下文解析接口
│  │  ├─ prediction.py              # 上传识别、生成识别接口
│  │  ├─ records.py                 # 历史记录查询和删除接口
│  │  └─ backtest.py                # 回测接口
│  ├─ services/                     # 业务逻辑层
│  │  ├─ auth_service.py            # 用户、密码哈希、Token、管理员逻辑
│  │  ├─ market_service.py          # 行情中心、股票详情、行情缓存和兜底数据
│  │  ├─ context_service.py         # 根据交易日补全/校验前端输入
│  │  ├─ kline_service.py           # 拉行情、选窗口、生成 K 线图
│  │  ├─ record_service.py          # 创建记录、查询记录、删除记录、生成图片 URL
│  │  └─ backtest_service.py        # 根据识别记录做未来走势验证
│  ├─ db/                           # 数据库层
│  │  ├─ database.py                # SQLite 连接和建表
│  │  ├─ repository.py              # 识别记录 SQL 增查删操作
│  │  └─ user_repository.py         # 用户 SQL 增查改删操作
│  └─ utils/                        # 后端工具函数
│     ├─ date_utils.py              # 日期解析、标准化、时间戳
│     └─ labels.py                  # 标签映射、置信度处理、信号方向
│
├─ inference/
│  └─ model_service.py              # 业务后端调用远程 AutoDL /predict 模型服务
│
├─ kline_core/
│  ├─ data_loader.py                # 股票行情拉取、标准化、K 线图绘制、训练数据批量生成
│  └─ labeling.py                   # 基于规则的形态识别算法，主要用于数据构建和实验
│
├─ deployment/
│  └─ autodl_fastapi/               # 独立模型推理服务部署目录
│     ├─ app.py                     # 加载 Qwen2.5-VL + LoRA，并提供 /health 和 /predict
│     ├─ start.sh                   # Linux/AutoDL 基础启动脚本
│     ├─ run_service_autodl.sh      # AutoDL 常用启动脚本，会写日志并做健康检查
│     ├─ local_backend.env.example  # 本地业务后端连接 AutoDL 服务的环境变量示例
│     ├─ requirements.txt           # 模型服务依赖
│     └─ README.md                  # AutoDL 部署说明
│
├─ scripts/
│  ├─ start_local_services.ps1      # Windows 本地一键启动 Streamlit + FastAPI
│  ├─ dataset/                      # 数据集划分和 LLaMA-Factory JSON 构建脚本
│  └─ synthetic/                    # 合成 K 线训练图片脚本
│
├─ data/
│  └─ kline_system.sqlite3          # SQLite 数据库文件
│
├─ outputs/
│  ├─ uploads/                      # 用户上传图片保存处
│  ├─ generated/                    # 自动生成 K 线图保存处
│  ├─ backtests/                    # 回测相关输出预留目录
│  └─ tmp/                          # 启动日志、临时输出
│
├─ models/                          # 本地基座模型文件目录，普通运行一般不用本机加载
└─ adapters/                        # LoRA 适配器、checkpoint、训练结果
```

`__pycache__`、`*.cpython-*.pyc`、日志文件属于运行时产生的缓存或输出，不是理解业务逻辑的重点。

---

## 5. 前端如何工作

### 5.1 启动入口

前端启动文件是：

```text
streamlit_app.py
```

它只有一件事：

```python
from frontend.app import main

main()
```

真正的前端总控在：

```text
frontend/app.py
```

它的流程是：

1. 调用 `inject_css()` 注入页面样式。
2. 调用 `initialize_state()` 初始化 `st.session_state`，并尽量从 URL 参数恢复页面和登录会话。
3. 如果用户没有登录，渲染 `frontend/pages/auth.py`。
4. 如果用户已登录，读取当前页面，比如首页、行情中心、上传页、历史页。
5. 调后端 `/health` 获取系统状态。
6. 渲染左侧导航栏和顶部栏。
7. 根据当前页面调用对应的 `render_xxx_page()`。

### 5.2 登录和页面访问

系统内部页面需要登录后才能访问。登录成功后，前端会保存：

| 状态 | 用途 |
| --- | --- |
| `auth_token` | 调后端接口时放到 `Authorization: Bearer ...` 请求头 |
| `current_user` | 当前用户信息，包括用户名、角色、账号状态 |
| `auth_sid` | 当前浏览器标签页的会话标识，用来刷新后恢复登录状态 |

这也是为什么刷新内部页面后仍能留在原页面：页面名会保存在 URL 的 `page` 参数里，登录状态会通过 `auth_sid` 和前端内存缓存恢复。

注意：这个会话恢复主要服务于本地演示和毕设项目。它不是生产级单点登录系统，如果 Streamlit 进程重启，前端内存里的 `auth_sid` 缓存也会丢失。

### 5.3 页面怎么切换

页面信息定义在 `frontend/shared.py` 的 `PAGE_META` 中。

| 页面 key | 页面 | 说明 |
| --- | --- | --- |
| `home` | 首页 | 系统状态、统计卡片、最近识别 |
| `market` | 行情中心 | 指数、市场情绪、个股行情 |
| `stock_detail` | 股票详情 | 从行情中心点击股票进入，导航中隐藏 |
| `upload` | 上传 K 线图识别 | 上传图片并识别形态 |
| `generate` | 自动生成并识别 | 拉行情、生成 K 线图、识别形态 |
| `records` | 历史识别记录 | 查询、筛选、详情、删除记录 |
| `backtest` | 回测分析 | 选择记录做轻量走势验证 |
| `profile` | 个人中心 | 查看账号信息、修改密码 |
| `users` | 用户管理 | 管理员可见，创建/维护/删除用户 |

前端主要用两种方式记住当前页面：

| 状态来源 | 作用 |
| --- | --- |
| `st.session_state` | Streamlit 当前会话里的页面状态 |
| `st.query_params` | URL 上的 `?page=xxx` 参数 |

这样做的好处是，用户点击导航后页面能切换，刷新时也能尽量保留当前页面。

### 5.4 `frontend/shared.py` 为什么很重要

这个文件是前端公共工具箱，主要负责：

| 功能 | 相关函数 |
| --- | --- |
| 调后端接口 | `api_get()`、`api_post_json()`、`api_post_multipart()`、`api_patch_json()`、`api_delete()` |
| 登录态管理 | `store_auth_payload()`、`clear_auth_state()`、`auth_headers()`、`refresh_current_user()` |
| 页面状态 | `set_page()`、`get_current_page()`、`remember_record()` |
| 读取后端健康状态 | `load_health_status()` |
| 读取历史记录 | `load_records_payload()` |
| 自动回测 | `fetch_backtest_result()` |
| 判断记录能否回测 | `record_can_backtest()` |
| 表单校验 | `validate_upload_date_inputs()`、`validate_generate_form_inputs()` |
| 通用 UI | `render_stat_card()`、`render_fixed_image_preview()`、`render_backtest_visual()` 等 |

实际页面文件在 `frontend/pages/` 下。`shared.py` 底部还保留了一些旧版页面渲染函数，但当前 `frontend/app.py` 使用的是 `frontend/pages/*.py` 中的页面实现。

---

## 6. 后端如何工作

后端入口是：

```text
backend/main.py
```

它创建 FastAPI 应用，并做几件关键事情：

1. 设置应用标题、版本和说明。
2. 开启 CORS，允许前端跨域调用。
3. 把 `outputs/` 挂成静态资源目录。
4. 注册登录、用户、行情、预测、记录、回测等路由。
5. 启动时创建必要目录、初始化 SQLite 表，并确保默认管理员账号存在。
6. 提供 `/health` 健康检查接口，同时检查远程 AutoDL 模型服务是否可连通。

静态资源挂载很关键：

```python
app.mount(config.static_mount_path, StaticFiles(directory=str(config.outputs_dir)), name="outputs")
```

它的意思是：`outputs/` 里的图片可以通过类似下面的 URL 访问：

```text
http://127.0.0.1:8000/outputs/generated/xxx.png
```

前端拿到这个 URL 后，就可以展示图片。

---

## 7. 后端分层设计

这个项目的后端结构比较清楚，可以按 4 层理解。

### 7.1 routes：接收 HTTP 请求

目录：

```text
backend/routes/
```

它负责：

1. 定义 API 路径。
2. 接收请求参数。
3. 调用登录鉴权依赖，确认当前用户是谁。
4. 做少量参数转换。
5. 调用 service。
6. 把结果返回给前端。

你可以把 `routes` 理解成“前台接待员”。

### 7.2 schemas：定义数据长什么样

文件：

```text
backend/schemas.py
```

它使用 Pydantic 定义请求体和响应体。例如：

| 类名 | 作用 |
| --- | --- |
| `RegisterRequest`、`LoginRequest` | 注册和登录请求 |
| `AuthResponseSchema`、`UserSchema` | 登录结果和用户信息 |
| `AdminCreateUserRequest`、`AdminUpdateUserRequest` | 管理员创建/维护用户 |
| `GenerateAndPredictRequest` | 自动生成并识别接口的请求参数 |
| `PredictResponseSchema` | 上传识别接口返回结构 |
| `RecognitionRecordSchema` | 单条识别记录结构 |
| `MarketOverviewSchema` | 行情中心总览结构 |
| `MarketStockDetailSchema` | 股票详情结构 |
| `BacktestRequest` | 回测请求参数 |
| `BacktestResponseSchema` | 回测响应结构 |

你可以把 `schemas.py` 理解成“接口表格模板”。

### 7.3 services：真正做业务

目录：

```text
backend/services/
```

主要服务如下：

| 文件 | 职责 |
| --- | --- |
| `auth_service.py` | 用户创建、登录校验、密码哈希、Token 签发、管理员操作 |
| `market_service.py` | 获取行情中心数据、股票详情数据、缓存和示例兜底 |
| `context_service.py` | 根据股票交易日校验和补全日期、窗口大小 |
| `kline_service.py` | 拉行情、截取窗口、生成 K 线图 |
| `record_service.py` | 写入识别记录、查询记录、删除记录、给图片生成 URL |
| `backtest_service.py` | 根据识别记录做后续交易日验证 |

你可以把 `services` 理解成“真正干活的人”。

### 7.4 db：和数据库打交道

目录：

```text
backend/db/
```

主要文件：

| 文件 | 职责 |
| --- | --- |
| `database.py` | 打开 SQLite 连接、创建用户表和识别记录表 |
| `repository.py` | 执行识别记录 SQL，比如插入、查询、删除 |
| `user_repository.py` | 执行用户 SQL，比如创建、查询、更新、删除 |

你可以把 `db` 理解成“仓库管理员”。

---

## 8. API 接口总览

启动 FastAPI 后，可以打开在线接口文档：

```text
http://127.0.0.1:8000/docs
```

当前主要接口如下：

| 方法 | 路径 | 作用 | 主要由哪个页面调用 |
| --- | --- | --- | --- |
| `GET` | `/` | 后端根路径，确认服务运行 | 浏览器或调试 |
| `GET` | `/health` | 查看业务后端和远程模型服务状态 | 所有页面顶部状态栏 |
| `POST` | `/register` | 注册普通用户 | 入口页 |
| `POST` | `/login` | 登录并获取 Token | 入口页 |
| `GET` | `/me` | 获取当前登录用户 | 初始化、刷新会话 |
| `POST` | `/change_password` | 修改当前用户密码 | 个人中心 |
| `GET` | `/users` | 管理员查询用户列表 | 用户管理 |
| `POST` | `/users` | 管理员创建用户 | 用户管理 |
| `PATCH` | `/users/{user_id}` | 管理员修改用户角色/状态 | 用户管理 |
| `DELETE` | `/users/{user_id}` | 管理员删除用户及其记录/图片 | 用户管理 |
| `POST` | `/users/{user_id}/delete` | 删除用户的兼容接口 | 用户管理 |
| `POST` | `/users/{user_id}/reset_password` | 管理员重置用户密码 | 用户管理 |
| `GET` | `/market/overview` | 行情中心总览 | 行情中心 |
| `GET` | `/market/stock/{stock_code}` | 股票详情、分时和 K 线数据 | 股票详情页 |
| `POST` | `/resolve_upload_context` | 上传页表单日期/窗口校验和补全 | 上传页 |
| `POST` | `/resolve_generate_context` | 自动生成页表单校验和补全 | 自动生成页 |
| `POST` | `/predict_image` | 上传图片并识别 | 上传页 |
| `POST` | `/generate_and_predict` | 拉行情、生成图、识别 | 自动生成页 |
| `GET` | `/records` | 查询历史记录列表，支持股票代码模糊筛选 | 首页、历史页、回测页 |
| `GET` | `/record/{record_id}` | 查询单条历史记录详情 | 历史页 |
| `DELETE` | `/record/{record_id}` | 删除单条历史识别记录，并尝试清理关联图片 | 历史页 |
| `POST` | `/backtest` | 对某条识别记录做轻量级回测验证 | 上传页、自动生成页、回测页 |

大部分业务接口都需要登录 Token。前端的 `api_get()`、`api_post_json()` 等公共函数会自动带上 `Authorization` 请求头。

---

## 9. 核心业务链路一：登录鉴权与用户管理

对应前端页面：

```text
frontend/pages/auth.py
frontend/pages/profile.py
frontend/pages/users.py
```

对应后端文件：

```text
backend/routes/auth.py
backend/routes/users.py
backend/services/auth_service.py
backend/db/user_repository.py
```

登录流程如下：

1. 用户在入口页输入用户名和密码。
2. 前端调用 `POST /login`。
3. 后端用 `AuthService.authenticate()` 校验用户名、账号状态和密码。
4. 密码使用 `pbkdf2_sha256` 哈希保存，不在数据库里明文保存。
5. 校验成功后，后端签发一个简单的 HMAC Token。
6. 前端保存 `auth_token`、`current_user` 和 `auth_sid`。
7. 后续请求通过 `Authorization: Bearer <token>` 访问内部接口。

个人中心修改密码流程如下：

1. 用户输入当前密码、新密码和确认密码。
2. 前端调用 `POST /change_password`。
3. 后端确认当前密码正确后写入新密码哈希。
4. 前端提示成功，等待约 2 秒后清空登录状态并回到入口页重新登录。

管理员用户管理流程如下：

1. 管理员进入“用户管理”页面。
2. 可以创建用户、设置角色、启用或禁用账号。
3. 删除用户时，后端会先删除该用户的识别记录，再删除这些记录对应的系统管理图片。
4. 用户删除成功、创建成功、保存设置成功后，前端用 toast 提示，避免刷新导致提示一闪而过。

---

## 10. 核心业务链路二：行情中心与股票详情

对应前端页面：

```text
frontend/pages/market.py
frontend/pages/stock_detail.py
```

对应后端接口：

```text
GET /market/overview
GET /market/stock/{stock_code}
```

行情中心做的事情：

1. 后端调用 `MarketService.get_overview()`。
2. 个股实时行情优先尝试东方财富，失败后尝试新浪。
3. 指数实时行情优先尝试东方财富，失败后尝试新浪。
4. 后端计算市场涨跌家数、涨跌分布、市场情绪分、涨幅榜、跌幅榜、成交额榜、活跃榜。
5. 前端展示指数卡片、市场情绪、涨跌分布和个股行情表。
6. 用户可以按板块筛选、按代码或名称搜索、按关键指标排序。
7. 点击个股代码或名称后，跳转到股票详情页。

股票详情页做的事情：

1. 前端请求 `/market/stock/{stock_code}`。
2. 后端返回实时行情卡片、分时数据、两年左右的历史 K 线数据。
3. 历史 K 线固定取约两年数据，后端用 15 分钟缓存，避免频繁切换图表时重复拉取。
4. 日线历史数据源尝试顺序为东方财富、 新浪、腾讯。
5. 分钟行情尝试东方财富、 新浪，失败时使用示例分时兜底。
6. 前端展示分时图、日 K、周 K、月 K，并支持在图表上滚轮缩放。
7. 近期交易明细展示最近 30 个交易日。

行情中心里的数据主要用于查看市场和个股情况，不会直接写入识别记录。只有上传识别、自动生成识别才会创建识别记录。

---

## 11. 核心业务链路三：上传图片识别

对应前端页面：

```text
frontend/pages/upload.py
```

对应后端接口：

```text
POST /predict_image
```

完整流程如下：

1. 用户在上传页选择一张图片。
2. 用户可选填股票代码、开始日期、结束日期、窗口大小。
3. 前端调用 `validate_upload_date_inputs()`，内部会请求 `/resolve_upload_context` 做日期和交易日校验。
4. 前端通过 `api_post_multipart()` 把图片和表单字段发给 `/predict_image`。
5. 后端把图片保存到 `outputs/uploads/`。
6. 后端调用 `inference_service.predict(image_path=...)`。
7. `inference/model_service.py` 把图片作为 multipart 表单发送给远程 AutoDL 的 `POST /predict`。
8. 远程模型服务返回 `label`、`confidence`、`reason`、`raw_output`、`inference_model`。
9. 后端调用 `record_service.create_record()` 把结果写入 SQLite。
10. 后端调用 `attach_image_url()` 把本地图片路径转成前端可访问 URL。
11. 前端展示图片、标签、置信度、识别原因。
12. 如果这条记录有股票代码、窗口大小和日期，前端会自动调用 `/backtest` 做轻量验证。

这里有一个重要限制：

上传图片只有图片本身，通常没有原始 OHLC 行情数据。所以如果用户不补股票代码、日期和窗口大小，系统可以识别图片，但不能准确定位后续交易日，也就不能直接回测。

---

## 12. 核心业务链路四：自动生成 K 线图并识别

对应前端页面：

```text
frontend/pages/generate.py
```

对应后端接口：

```text
POST /generate_and_predict
```

完整流程如下：

1. 用户输入股票代码、开始日期、结束日期、窗口大小。
2. 前端调用 `validate_generate_form_inputs()`。
3. 这个校验函数会请求 `/resolve_generate_context`，由后端根据交易日补全缺失字段。
4. 前端把整理好的参数发给 `/generate_and_predict`。
5. 后端调用 `KlineChartService.generate_chart()`。
6. `generate_chart()` 先用 AkShare 拉行情，再按日期过滤。
7. 如果传了 `anchor_date`，会取锚点日期之前的窗口；否则默认取区间最后 `window_size` 个交易日。
8. 后端用 `mplfinance` 画 K 线图，再用 Pillow 缩放成 `448x448`。
9. 图片保存到 `outputs/generated/`。
10. 后端调用远程 AutoDL `/predict` 识别这张图。
11. 识别结果写入 SQLite。
12. 前端展示生成图、识别结果，并尝试自动回测。

自动生成链路比上传链路更适合回测，是因为它同时拥有：

| 数据 | 用途 |
| --- | --- |
| 图片 | 给视觉模型识别 |
| 股票代码 | 用于后续重新拉行情 |
| 日期区间 | 用于定位识别窗口 |
| 窗口大小 | 用于确定识别窗口长度 |
| OHLC 行情表格 | 用于生成图片和后续走势验证 |

---

## 13. 核心业务链路五：历史记录查询与删除

对应前端页面：

```text
frontend/pages/records.py
```

对应后端接口：

```text
GET /records
GET /record/{record_id}
DELETE /record/{record_id}
```

查询流程如下：

1. 前端先调用 `/records` 获取记录列表。
2. 用户可以按股票代码、识别类型筛选。
3. 股票代码筛选是模糊查询，比如输入 `519` 可以匹配 `600519`。
4. 用户选择某条记录后，前端调用 `/record/{id}` 拉取详情。
5. 后端只会返回当前登录用户自己的记录。
6. `RecordService.attach_image_url()` 把 `image_path` 转成 `image_url`。
7. 前端展示图片、标签、置信度、来源、时间、推理模型、回测入口等信息。

删除流程如下：

1. 用户在历史记录页选择一条记录并查看详情。
2. 前端显示“删除记录”区域，用户需要先勾选“确认删除记录 #id”。
3. 点击“删除该记录”后，前端通过 `api_delete()` 请求 `DELETE /record/{id}`。
4. 后端确认这条记录属于当前用户。
5. 后端先删除 SQLite 中的记录。
6. 如果这条记录的图片位于项目 `outputs/` 目录下，`record_service.delete_record()` 会继续尝试删除对应图片文件。
7. 删除成功后，前端清空当前详情、回测缓存和相关页面状态，并刷新历史列表。

历史记录页负责展示、筛选、详情查看和删除入口，不直接做模型识别。

---

## 14. 核心业务链路六：回测分析

对应前端页面：

```text
frontend/pages/backtest.py
```

对应后端接口：

```text
POST /backtest
```

回测逻辑在：

```text
backend/services/backtest_service.py
```

它不是完整量化交易系统，而是一个轻量级信号验证：

1. 根据 `record_id` 找到历史识别记录。
2. 确认记录里有 `stock_code`、`window_size`、`end_date`。
3. 从图片文件名或记录字段里解析识别窗口结束日期。
4. 拉取从开始日期到未来一段时间的行情。
5. 找到识别窗口结束日的位置。
6. 取后面 `horizon_days` 个交易日。
7. 比较窗口结束日收盘价和未来第 `horizon_days` 个交易日收盘价。
8. 根据标签判断结果是否成功：
   - 偏多标签未来上涨算成功。
   - 偏空标签未来下跌算成功。
   - 中性标签不判断成功或失败。

这里的“未来收益率”不是未来每天收益率的平均值，而是最后一天相对识别窗口结束日的累计收益率：

```text
future_return = (未来第 N 个交易日收盘价 - 识别窗口结束日收盘价) / 识别窗口结束日收盘价
```

表格里每一天的 `return_rate` 也是“截至该日相对识别窗口结束日的累计收益率”。

一条记录能否回测，取决于它是否具备这些字段：

| 字段 | 为什么需要 |
| --- | --- |
| `stock_code` | 回测需要重新拉行情 |
| `window_size` | 回测需要知道当时识别窗口多长 |
| `end_date` | 回测需要定位识别窗口结束位置 |

所以：

1. 自动生成页产生的记录通常可以回测。
2. 上传页如果没有补充股票代码、日期和窗口大小，就通常不能回测。

更准确地说，这个功能应理解为“识别信号有效性验证”，不是专业量化回测。它不包含仓位管理、止盈止损、手续费、滑点、资金曲线、最大回撤、夏普比率等交易系统指标。

---

## 15. 数据库怎么设计

数据库文件在：

```text
data/kline_system.sqlite3
```

项目使用 SQLite，不需要单独安装 MySQL 或 PostgreSQL。SQLite 的特点是数据库就是一个本地文件，适合小型项目、课程项目和演示系统。

后端启动时会自动执行：

```python
init_db()
```

### 15.1 用户表

用户表 SQL 在 `backend/db/database.py` 中：

```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    last_login_at TEXT
);
```

字段说明：

| 字段 | 含义 |
| --- | --- |
| `id` | 用户编号，自增主键 |
| `username` | 用户名，唯一 |
| `password_hash` | 哈希后的密码 |
| `role` | 用户角色，`admin` 或 `user` |
| `is_active` | 是否启用，0 表示禁用，1 表示启用 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |
| `last_login_at` | 最近登录时间 |

系统启动时，如果用户表为空，会创建默认管理员账号。默认账号和密码来自环境变量：

```text
KLINE_DEFAULT_ADMIN_USERNAME
KLINE_DEFAULT_ADMIN_PASSWORD
```

如果没有设置，默认是：

```text
admin / admin123456
```

### 15.2 识别记录表

识别记录表 SQL 在 `backend/db/database.py` 中：

```sql
CREATE TABLE IF NOT EXISTS recognition_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    stock_code TEXT,
    image_path TEXT NOT NULL,
    predicted_label TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0,
    reason TEXT,
    source_type TEXT NOT NULL,
    window_size INTEGER,
    start_date TEXT,
    end_date TEXT,
    inference_model TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

字段说明：

| 字段 | 含义 |
| --- | --- |
| `id` | 识别记录编号，自增主键 |
| `user_id` | 创建这条记录的用户 ID |
| `stock_code` | 股票代码，比如 `600519` |
| `image_path` | 图片在本地磁盘上的绝对路径 |
| `predicted_label` | 模型预测出的形态标签 |
| `confidence` | 置信度，范围 0 到 1 |
| `reason` | 识别原因说明 |
| `source_type` | 来源类型，`upload` 或 `generated` |
| `window_size` | 识别窗口大小 |
| `start_date` | 识别区间开始日期 |
| `end_date` | 识别区间结束日期 |
| `inference_model` | 本次识别使用的推理模型名称 |
| `created_at` | 记录创建时间 |

注意：数据库里保存的是图片路径，不是图片二进制本身。

删除识别记录时，系统执行的是物理删除：数据库中的这一行会被移除，不会额外保留“已删除”状态字段。删除接口返回的 `image_deleted` 表示关联图片文件是否也被成功清理。

删除用户时，系统会先删除该用户的识别记录和系统管理图片，再删除用户本身。

图片和数据库的配合关系是：

```text
图片保存到 outputs/
  -> SQLite 保存 image_path
  -> 后端转换成 image_url
  -> 前端用 image_url 显示图片
```

---

## 16. 图片文件怎么管理

项目里的图片输出主要在：

```text
outputs/
├─ uploads/      # 上传页保存用户上传图片
├─ generated/    # 自动生成页保存生成的 K 线图
├─ backtests/    # 回测输出预留目录
└─ tmp/          # 启动日志、临时文件
```

后端会把 `outputs/` 整个目录挂载为静态资源，所以图片可以通过 HTTP 地址访问。

例如本地文件：

```text
D:\Projects\klineSystem\outputs\generated\600519_xxx.png
```

可能会被转换为：

```text
http://127.0.0.1:8000/outputs/generated/600519_xxx.png
```

转换逻辑在：

```text
backend/services/record_service.py
```

核心函数是：

```python
attach_image_url()
```

删除记录时也会用到同一个服务文件里的 `delete_record()`。它只会尝试删除 `outputs/` 目录下由系统管理的图片，避免误删项目外部文件。

---

## 17. K 线图怎么生成

核心文件：

```text
backend/services/kline_service.py
kline_core/data_loader.py
```

生成流程如下：

1. `KlineChartService.fetch_dataframe()` 调用 `fetch_stock_data()`。
2. `fetch_stock_data()` 使用 AkShare 尝试多个数据源。
3. 拉到数据后统一字段格式为：
   - `Date`
   - `Open`
   - `High`
   - `Low`
   - `Close`
   - `Volume`
4. 根据用户输入的日期过滤数据。
5. 通过 `select_window()` 选取识别窗口。
6. 通过 `save_and_resize_chart()` 画图并缩放到 `448x448`。
7. 图片保存到 `outputs/generated/`。

为什么要统一字段名？

不同数据源返回的列名可能不同，比如有的叫 `日期`，有的叫 `date`。模型和绘图逻辑不能每次适配各种名字，所以项目会先统一成标准 OHLCV 格式。

---

## 18. 模型推理怎么实现

推理调用入口在：

```text
inference/model_service.py
```

它本身不直接加载大模型，而是负责：

1. 判断远程模型服务是否配置好。
2. 把图片通过 multipart 表单发给远程 `/predict`。
3. 解析远程模型服务返回的 JSON。
4. 把模型输出统一成 `PredictionResult`。

当前业务后端只使用一种远程协议：

| 协议 | 配置值 | 说明 |
| --- | --- | --- |
| 自定义 FastAPI | `custom_fastapi` | 调用 AutoDL 模型服务的 `POST /predict` |

当前 `scripts/start_local_services.ps1` 默认配置的是：

```powershell
$env:KLINE_INFERENCE_BACKEND = "remote_api"
$env:KLINE_REMOTE_API_PROTOCOL = "custom_fastapi"
$env:KLINE_REMOTE_API_PREDICT_PATH = "/predict"
$env:KLINE_REMOTE_API_HEALTH_PATH = "/health"
```

真正加载 Qwen2.5-VL + LoRA 的服务在：

```text
deployment/autodl_fastapi/app.py
```

它会：

1. 读取 `KLINE_MODEL_BASE_DIR` 找到 Qwen2.5-VL 基座模型。
2. 读取 `KLINE_LORA_DIR` 找到 LoRA 适配器。
3. 用 Transformers 加载 `Qwen2_5_VLForConditionalGeneration`。
4. 用 PEFT 的 `PeftModel.from_pretrained()` 挂载 LoRA。
5. 提供：
   - `GET /health`
   - `POST /predict`

`POST /predict` 的返回结构类似：

```json
{
  "label": "双底",
  "confidence": 0.78,
  "reason": "图中出现两个相近低点，中间存在明显反弹，符合双底特征。",
  "raw_output": "双底",
  "inference_model": "Qwen2.5-VL-7B-Instruct + LoRA"
}
```

业务后端和模型后端的职责边界如下：

| 模块 | 是否加载大模型 | 主要职责 |
| --- | --- | --- |
| `backend/main.py` | 否 | 业务 API、登录、数据库、图片、行情、回测 |
| `inference/model_service.py` | 否 | 调远程模型、解析结果 |
| `deployment/autodl_fastapi/app.py` | 是 | 加载 Qwen2.5-VL + LoRA 并实际推理 |

---

## 19. 规则识别代码有什么用

规则识别相关代码在：

```text
kline_core/labeling.py
```

它不看图片，而是看 OHLC 表格数据。基本思路是：

1. 从 `High` 和 `Low` 序列中提取局部高点和低点。
2. 对价格序列做轻微平滑，减少噪声。
3. 针对每种形态写一套判断规则。
4. 对候选形态计算分数。
5. 选分数最高的形态。
6. 都不满足时返回“无明显形态”。

主要规则函数：

| 函数 | 识别形态 |
| --- | --- |
| `check_double_bottom()` | 双底 |
| `check_double_top()` | 双顶 |
| `check_head_and_shoulders_top()` | 头肩顶 |
| `check_head_and_shoulders_bottom()` | 头肩底 |
| `check_ascending_triangle()` | 上升三角形 |
| `check_descending_triangle()` | 下降三角形 |
| `check_no_clear_pattern()` | 无明显形态 |

当前主流程里的图片识别已经统一走远程 AutoDL `/predict` 模型服务。规则识别代码主要用于数据构建、合成数据校验和后续实验扩展，不再作为当前业务识别接口的自动兜底分支。

---

## 20. 配置和环境变量

配置入口：

```text
backend/config.py
```

它负责：

1. 自动找到项目根目录。
2. 自动确定 `data/`、`outputs/`、`uploads/`、`generated/` 等路径。
3. 读取环境变量。
4. 创建必要目录。

常用环境变量如下：

| 环境变量 | 作用 | 默认值 |
| --- | --- | --- |
| `BACKEND_HOST` | FastAPI 主机 | `127.0.0.1` |
| `BACKEND_PORT` | FastAPI 端口 | `8000` |
| `STREAMLIT_BACKEND_URL` | Streamlit 调后端的地址 | `http://127.0.0.1:8000` |
| `KLINE_INFERENCE_BACKEND` | 推理后端模式 | `remote_api` |
| `KLINE_REMOTE_API_PROTOCOL` | 远程推理协议 | `custom_fastapi` |
| `KLINE_REMOTE_API_BASE_URL` | 远程模型服务地址 | `http://127.0.0.1:6006` |
| `KLINE_REMOTE_API_PREDICT_PATH` | 远程推理路径 | `/predict` |
| `KLINE_REMOTE_API_HEALTH_PATH` | 远程健康检查路径 | `/health` |
| `KLINE_REMOTE_API_DISPLAY_NAME` | 模型显示名兜底值 | `Qwen2.5-VL-7B-Instruct + LoRA` |
| `KLINE_REMOTE_API_TIMEOUT` | 远程接口超时时间 | `300` |
| `KLINE_MODEL_MAX_NEW_TOKENS` | 发给模型服务的最大生成长度 | `160` |
| `KLINE_MODEL_TEMPERATURE` | 发给模型服务的采样温度 | `0.0` |
| `KLINE_AUTH_SECRET` | 本地 Token 签名密钥 | `kline-system-local-auth-secret` |
| `KLINE_AUTH_TOKEN_EXPIRE_MINUTES` | Token 有效分钟数 | `1440` |
| `KLINE_DEFAULT_ADMIN_USERNAME` | 默认管理员用户名 | `admin` |
| `KLINE_DEFAULT_ADMIN_PASSWORD` | 默认管理员密码 | `admin123456` |

如果你通过 `scripts/start_local_services.ps1` 启动，本地脚本会帮你设置远程模型服务地址、协议、推理路径和健康检查路径。

---

## 21. 本地如何运行

### 21.1 安装依赖

建议先创建虚拟环境：

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 21.2 一键启动

Windows 下可以运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_local_services.ps1
```

这个脚本会：

1. 设置远程模型服务相关环境变量。
2. 启动 FastAPI 后端，默认端口 `8000`。
3. 启动 Streamlit 前端，默认端口 `8501`。
4. 把日志写入 `outputs/tmp/`。
5. 打印后端健康检查结果。

访问地址：

```text
Streamlit 前端：http://127.0.0.1:8501
FastAPI 文档：http://127.0.0.1:8000/docs
```

如果远程 AutoDL 服务地址变了，需要修改：

```text
scripts/start_local_services.ps1
```

里面的：

```powershell
$RemoteApiBaseUrl = "..."
```

这里应该填写 AutoDL 模型服务的根地址，不要带 `/v1`，例如：

```text
https://你的AutoDL公网地址:8443
```

或者本地端口映射地址：

```text
http://127.0.0.1:6006
```

### 21.3 手动启动

如果你想手动启动，可以开两个终端。

终端 1 启动后端：

```powershell
$env:KLINE_INFERENCE_BACKEND="remote_api"
$env:KLINE_REMOTE_API_PROTOCOL="custom_fastapi"
$env:KLINE_REMOTE_API_BASE_URL="http://127.0.0.1:6006"
$env:KLINE_REMOTE_API_PREDICT_PATH="/predict"
$env:KLINE_REMOTE_API_HEALTH_PATH="/health"
$env:STREAMLIT_BACKEND_URL="http://127.0.0.1:8000"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

终端 2 启动前端：

```powershell
python -m streamlit run streamlit_app.py --server.port 8501
```

---

## 22. AutoDL 模型服务如何运行

AutoDL 部署目录是：

```text
deployment/autodl_fastapi/
```

需要上传到 AutoDL 的主要文件：

```text
app.py
requirements.txt
start.sh
run_service_autodl.sh
README.md
```

同时还需要准备：

```text
Qwen2.5-VL-7B-Instruct 基座模型目录
LoRA 适配器目录
```

常用启动命令是：

```bash
chmod +x /root/autodl-tmp/deployment/autodl_fastapi/run_service_autodl.sh
bash /root/autodl-tmp/deployment/autodl_fastapi/run_service_autodl.sh
tail -f /root/autodl-tmp/kline_fastapi.out
```

当前 `run_service_autodl.sh` 默认使用这些路径：

```text
/root/autodl-tmp/deployment/autodl_fastapi
/root/autodl-tmp/models/Qwen2.5-VL-7B-Instruct
/root/autodl-tmp/adapters/kline_lora_v3_lr5e5_ep5/checkpoint-1050
```

如果你远程机器上的模型或 LoRA 目录不同，需要修改 `run_service_autodl.sh` 里的：

```bash
PROJECT_DIR
MODEL_BASE_DIR
LORA_DIR
PROCESSOR_SOURCE
```

服务启动成功后提供：

```text
GET  /health
POST /predict
```

可以在 AutoDL 机器上先测：

```bash
curl http://127.0.0.1:6006/health
curl -X POST "http://127.0.0.1:6006/predict" -F "file=@/root/test.png"
```

---

## 23. scripts 目录有什么用

`scripts/` 主要是辅助脚本，不是 Web 服务必须理解的第一优先级。

| 目录或文件 | 作用 |
| --- | --- |
| `scripts/start_local_services.ps1` | Windows 本地启动前后端 |
| `scripts/dataset/split_dataset.py` | 把分类图片数据集按 train/val/test 划分 |
| `scripts/dataset/build_llamafactory_json.py` | 生成 LLaMA-Factory 训练所需 JSON |
| `scripts/synthetic/generate_artificial_v1.py` | 合成部分形态的 K 线训练图片 |
| `scripts/synthetic/generate_artificial_v2.py` | 更丰富的合成图片脚本，支持三角形、噪声、多样性参数 |

如果你只是运行系统，看 `start_local_services.ps1` 就够了。

如果你要训练或扩充数据集，再看 `dataset/` 和 `synthetic/`。

---

## 24. models 和 adapters 目录

这两个目录和模型训练、推理有关。

| 目录 | 作用 |
| --- | --- |
| `models/Qwen2.5-VL-7B-Instruct/` | Qwen2.5-VL 基座模型文件 |
| `adapters/kline_lora_v3_lr5e5_ep5/` | 针对 K 线形态识别训练出的 LoRA 适配器 |
| `adapters/.../checkpoint-*` | 训练过程中的 checkpoint |
| `adapters/.../trainer_state.json` | 训练状态，可能记录最佳 checkpoint |
| `adapters/.../training_loss.png` | 训练 loss 曲线 |

主业务后端默认通过远程 API 推理，不建议在普通本地电脑直接加载大模型。真正加载大模型通常放到 GPU 机器上的 `deployment/autodl_fastapi/app.py`。

---

## 25. 新手推荐阅读顺序

如果你想逐步看懂项目，建议按这个顺序读代码：

1. `streamlit_app.py`
2. `frontend/app.py`
3. `frontend/pages/auth.py`
4. `frontend/shared.py` 里的 `api_get()`、`api_post_json()`、`initialize_state()`
5. `backend/main.py`
6. `backend/routes/auth.py`
7. `backend/services/auth_service.py`
8. `frontend/pages/upload.py`
9. `frontend/pages/generate.py`
10. `backend/routes/prediction.py`
11. `inference/model_service.py`
12. `deployment/autodl_fastapi/app.py`
13. `backend/services/kline_service.py`
14. `frontend/pages/records.py`
15. `backend/routes/records.py`
16. `backend/services/record_service.py`
17. `frontend/pages/backtest.py`
18. `backend/services/backtest_service.py`
19. `frontend/pages/market.py`
20. `frontend/pages/stock_detail.py`
21. `backend/services/market_service.py`
22. `frontend/pages/users.py`
23. `backend/routes/users.py`
24. `backend/db/database.py`
25. `backend/db/repository.py`
26. `backend/db/user_repository.py`

这个顺序是从“用户看见的页面”一路追到“后端业务”和“模型推理”，比较容易建立整体感。

---

## 26. 想改功能时应该看哪里

| 你想改什么 | 主要看哪里 |
| --- | --- |
| 改登录、注册、修改密码 | `frontend/pages/auth.py`、`frontend/pages/profile.py`、`backend/routes/auth.py`、`backend/services/auth_service.py` |
| 改用户管理 | `frontend/pages/users.py`、`backend/routes/users.py`、`backend/services/auth_service.py`、`backend/db/user_repository.py` |
| 改页面布局、按钮、文字 | `frontend/pages/*.py`、`frontend/shared.py` |
| 改前端调用哪个接口 | `frontend/shared.py` |
| 新增页面 | `frontend/pages/`、`frontend/app.py`、`frontend/shared.py` 的 `PAGE_META` |
| 改接口参数 | `backend/schemas.py`、`backend/routes/*.py` |
| 改上传识别逻辑 | `frontend/pages/upload.py`、`backend/routes/prediction.py`、`inference/model_service.py` |
| 改自动生成 K 线图逻辑 | `frontend/pages/generate.py`、`backend/services/kline_service.py`、`kline_core/data_loader.py` |
| 改模型调用方式 | `inference/model_service.py` |
| 改 AutoDL 模型服务 | `deployment/autodl_fastapi/app.py` |
| 改历史记录字段 | `backend/db/database.py`、`backend/db/repository.py`、`backend/schemas.py`、`backend/services/record_service.py` |
| 改历史记录查询或删除 | `frontend/pages/records.py`、`frontend/shared.py`、`backend/routes/records.py`、`backend/services/record_service.py`、`backend/db/repository.py` |
| 改行情中心 | `frontend/pages/market.py`、`backend/routes/market.py`、`backend/services/market_service.py` |
| 改股票详情 | `frontend/pages/stock_detail.py`、`backend/services/market_service.py` |
| 改回测逻辑 | `frontend/pages/backtest.py`、`backend/services/backtest_service.py` |
| 改标签名称、置信度、信号方向 | `backend/utils/labels.py` |
| 改规则识别算法 | `kline_core/labeling.py` |

---

## 27. 常见问题

### 27.1 现在系统属于前后端分离吗

算是前后端分离，但不是传统 Vue/React + REST 后端那种。

更准确地说，它是：

```text
浏览器 -> Streamlit 前端服务 -> FastAPI 业务后端 -> AutoDL FastAPI 模型服务
```

Streamlit 负责页面交互，FastAPI 负责业务 API，AutoDL 服务负责模型推理。

### 27.2 为什么前端也是 Python

因为项目使用 Streamlit。Streamlit 适合快速做数据应用、AI 应用和演示系统，不需要写 React 或 Vue，也能做出可交互页面。

### 27.3 为什么还需要 FastAPI

Streamlit 负责界面，FastAPI 负责业务接口。这样前端和后端边界更清楚：

```text
Streamlit：收集输入、展示结果
FastAPI：处理业务、调模型、存数据库、做行情和回测
```

### 27.4 为什么数据库不直接存图片

图片文件通常比较大。项目选择把图片放在 `outputs/` 目录，数据库只保存路径。这样数据库更轻，前端也可以通过静态 URL 访问图片。

### 27.5 为什么自动生成识别比上传识别更适合回测

自动生成时，系统知道股票代码、日期、窗口大小和原始行情数据。上传图片时，如果用户不补这些信息，系统只知道“有一张图片”，就无法准确定位后续交易日。

### 27.6 这个回测能代表真实交易收益吗

不能直接代表真实交易收益。当前回测是轻量验证，只看识别窗口结束后若干交易日的涨跌方向，主要用于展示“识别结果是否与后续走势大致一致”。

### 27.7 删除记录会不会删除图片

会尝试删除。系统先删除 SQLite 里的识别记录，再判断 `image_path` 是否位于项目的 `outputs/` 目录下；如果是系统管理的图片文件，就一并删除。若图片不存在或路径不在 `outputs/` 下，接口仍会返回记录删除结果，但 `image_deleted` 会是 `false`。

### 27.8 删除用户会不会删除他的识别记录

会。管理员删除用户时，后端会调用 `RecordService.delete_records_for_user()`，把该用户的识别记录和对应的系统管理图片一起清理，然后再删除用户。

### 27.9 行情数据为什么有时显示示例数据

行情中心依赖 AkShare 去访问东方财富、新浪、腾讯等数据源。外部数据源可能因为网络、接口变化、频率限制而失败。为了页面不空白，系统会在失败时使用示例数据兜底，并在页面上显示数据源说明。

### 27.10 远程模型服务地址为什么不能带 `/v1`

现在业务后端调用的是 AutoDL FastAPI 的：

```text
POST /predict
```

所以 `KLINE_REMOTE_API_BASE_URL` 应该是模型服务根地址，例如：

```text
http://127.0.0.1:6006
```

不要写成：

```text
http://127.0.0.1:6006/v1
```

否则会变成请求 `/v1/predict`，和当前部署服务不匹配。代码里已经对误填 `/v1` 做了归一处理，但推荐从配置上就写正确。

---

## 28. 最后用一段话总结

这个项目是一个完整的 Python AI 应用原型：`Streamlit` 负责页面，`FastAPI` 负责业务 API，`SQLite` 保存用户和识别记录，`outputs/` 保存图片，`AkShare + mplfinance` 负责行情和 K 线图生成，`Plotly` 负责股票详情交互图表，`inference/model_service.py` 负责调用远程 AutoDL `/predict` 推理服务，`deployment/autodl_fastapi/app.py` 负责真正加载 Qwen2.5-VL + LoRA，`backtest_service.py` 则把识别结果继续延伸到后续走势验证。

理解这个项目时，只要始终抓住 5 个问题就不容易迷路：

1. 用户输入从哪个页面进来？
2. 前端调用了哪个 FastAPI 接口？
3. 后端把图片和记录保存到了哪里？
4. 模型服务是本地业务后端调用远程 `/predict` 得到的，还是页面自己做的？
5. 识别结果如何回到页面，并能不能继续查看行情、回测或删除？
