# 架构与数据流

系统由一条单向管线构成：采集 → 分段 → 上下文 → 视觉模型 → 落库 → 加密与索引。
下面依次是它要解决的问题、模块划分、两种运行路径，以及数据在每一层的形状。

## 项目背景

本项目是一个**实验室视觉日志系统**的 MVP（最小可行产品）实现。系统的核心目标是通过相机和视觉大模型，将实验室内的人物动作（使用设备和药品等）和设备运转状态自动记录为结构化文本日志，为更高级的智能体应用和 AI 实验室管家奠定基础。

### 核心特性

- **动态上下文视频理解**：使用动态上下文驱动的视频理解，基于当天事件缓存、人物外貌表缓存和二维码识别结果构建提示词，模型输出续写事件和外貌更新
- **视频理解**：支持 Qwen3-VL 、 Qwen3.5 、 Gemini2.5 系列视觉大模型，分析实验室视频，自动识别人物动作、设备操作等信息
- **人物外貌管理**：自动维护人物外貌表缓存，支持追加、更新、合并操作，使用并查集管理编号合并关系
- **二维码识别**：Android 采集端实时识别用户二维码，自动关联用户身份与视频片段
- **结构化日志**：将视频内容转换为带时间戳的结构化事件日志（事件不加密，直接写入数据库）
- **字段级加密**：支持对敏感字段（如人物外观特征）进行加密，使用混合加密方案（AES-GCM + RSA-OAEP）。日终处理时，系统会自动根据识别出的用户身份使用对应的公钥进行加密，确保隐私数据仅该用户可解。
- **向量检索**：支持日志的向量嵌入和语义搜索，便于后续的智能查询和分析。日终处理会自动触发索引构建。
- **紧急事件提醒**：视觉模型自动识别实验室紧急情况（如火焰），系统实时记录并向管理员发送 Web 弹窗/变红提醒。
- **Web 前端**：提供用户友好的 Web 界面，支持用户注册、登录、查看数据和管理功能
- **权限管理**：支持用户角色（admin/user），admin 用户可以查看数据库和进行向量搜索

### 系统架构

系统采用模块化设计，主要包含以下模块：

- **视频接入**：支持 MP4 视频文件处理（未来可扩展为流式处理）
- **视频分段**：使用关键帧对齐将长视频分割为处理段（约 60 秒），支持迭代式分段确保连续性
- **动态上下文**：维护当天事件缓存（最新 n 条）和人物外貌表缓存（全量），用于构建模型提示词
- **视频理解**：调用 Qwen 或 Gemini API 进行视频内容分析，使用动态上下文生成续写事件和外貌更新
- **人物外貌管理**：使用并查集管理人物编号合并关系，支持追加、更新、合并操作
- **日志写入**：将识别的事件直接写入数据库（不加密），人物外貌表缓存在内存/文件，日终再加密入库
- **向量嵌入**：对日志进行分块和向量化，支持语义搜索
- **存储**：使用 SeekDB 作为数据库，支持关系型、向量和全文搜索
- **Web 前端**：React + Vite 构建的用户界面，提供数据查看和管理功能
- **后端 API**：FastAPI 构建的 RESTful API，支持用户认证和数据访问
- **流媒体服务器**：WebSocket 服务器，接收 Android 端推送的 MP4 分段（经 H.264 编码），串行处理并写入日志 / 索引

## 工作流程

### 整体流程（逻辑视角）

#### 动态上下文模式（默认）

```
视频文件 (MP4) + 二维码识别结果
    ↓
[视频分段] 关键帧对齐，分为多个约 60 秒的片段（迭代式分段确保连续性）
    ↓
[动态上下文构建]
    ├─ 查询当天最新 n 条事件（从 JSONL 文件 logs_debug/event_logs.jsonl）
    ├─ 加载人物外貌表缓存（从内存/文件 logs_debug/appearances_today.json）
    └─ 获取二维码识别结果（从分段元数据）
    ↓
[视频理解] 调用 Qwen3-VL / Qwen3.5 API（Flash/Plus），输入动态上下文，输出：
    ├─ events_to_append: 续写的事件列表
    └─ appearance_updates: 外貌更新（add/update/merge）
    ↓
[事件写入] 立即写入 SeekDB 数据库（不加密）+ 调试 JSONL 文件
    ↓
[外貌更新] 更新人物外貌表缓存（内存）
    ↓
[周期性保存] 每处理 N 个分段，dump 外貌缓存到文件
    ↓
[日终处理] 并查集压缩 → 动态公钥获取与加密 → 写入数据库 → 更新事件 person_ids → 触发索引
    ↓
完成
```

#### 传统模式（兼容）

```
视频文件 (MP4)
    ↓
[视频分段] 关键帧对齐，分为多个约 60 秒的片段（迭代式分段确保连续性）
    ↓
[视频理解] 对每个片段调用 Qwen3-VL / Qwen3.5 API（Flash/Plus），提取事件
    ↓
[日志生成] 将识别的事件转换为结构化 EventLog
    ↓
[字段加密] 对配置的敏感字段进行混合加密（如人物外观）
    ↓
[数据写入] 写入 SeekDB 数据库 + 调试 JSONL 文件
    ↓
[可选] [日志分块] 使用配置的分块策略聚合事件（默认：每个事件一个块）
    ↓
[可选] [向量嵌入] 使用 Qwen text-embedding-v4 生成 1024 维向量
    ↓
[可选] [向量索引] 写入 logs_embedding 表，支持向量搜索
    ↓
完成
```

### 两种处理路径

1) **实时处理（Android 采集端 → WebSocket 服务器）**
   - Android 端用 MediaCodec 编码 H.264，并在关键帧前附带完整 SPS/PPS（关键经验：给 IDR 帧前置 SPS/PPS，保证每段 MP4 可独立解码），使用 MediaMuxer 生成小 MP4 分段，通过 WebSocket 发送到服务器。
   - **二维码识别**：采集过程中使用 ML Kit 实时识别用户二维码，按分段聚合识别结果（同一用户保留最高置信度），随 MP4 分段元数据一起上报。识别成功时播放提示音并在预览层显示提示。
   - 服务器 `streaming_server` 接收 Base64 MP4 文本消息（包含二维码识别结果），保存到 `recordings/<timestamp>/` 目录：
     - MP4 分段保存为 `{segment_id}.mp4`
     - 二维码识别结果保存为 `{segment_id}_qr.json`
   - 如果启用实时处理，立即进行视频理解并写入数据库；否则仅保存文件，后续可使用 `scripts/process_recording_session.py` 处理。
   - **动态上下文模式**（默认启用）：
     - 每个会话维护独立的人物外貌缓存（AppearanceCache）
     - 从 JSONL 文件（`logs_debug/event_logs.jsonl`）读取当天最新 n 条事件作为上下文
     - 启动时自动加载已存在的外貌缓存文件（`logs_debug/appearances_today.json`）
     - 模型输出续写事件和外貌更新，事件立即入库（不加密），外貌更新写入缓存
     - 每处理 N 个分段，自动保存外貌缓存到 `logs_debug/appearances_today.json`
   - 处理管线：动态上下文构建 → 视觉模型 → 解析多输出（事件、外貌、紧急情况）→ 数据写入数据库（logs_raw, emergencies）→ 外貌更新缓存 → 生成缩略图 → 单行 Realtime 日志输出。

2) **离线处理（已有 MP4 文件）**
   - 使用 `scripts/process_video.py /path/to/video.mp4` 直接跑 VideoLogPipeline。
   - 生成事件日志（logs_raw / event_logs.jsonl），每个分段理解后立即写入数据库。
   - 索引需要手动触发：使用 `scripts/index_events.py` 对未索引的事件进行分块和嵌入。

3) **处理已保存的采集会话**
   - 使用 `scripts/process_recording_session.py recordings/<session_dir>` 处理一次采集会话的所有分段。
   - 自动读取会话目录下的 MP4 分段和对应的二维码识别结果（`*_qr.json` 文件）。
   - 每个分段理解后立即写入数据库，二维码结果会传递给视频理解部分（当前暂不使用）。
   - 适用于处理实时采集后保存的会话数据，或重新处理历史会话。

### 数据流

1. **视频分段**：
   - 使用 ffprobe 检测所有关键帧（I 帧）位置
   - 以关键帧为边界进行分段，每个分段约 60 秒
   - 采用迭代式分段：每提取一个分段后，检查实际结束时间，从那里开始下一个分段
   - 确保分段连续且无重叠，每个分段不超过 5 分钟
2. **视频理解**（动态上下文模式）：
   - 构建动态提示词：包含视频片段、二维码识别结果、当天最新 n 条事件（从 JSONL 文件读取）、人物外貌表全量（从缓存文件加载）
   - 调用 Qwen3-VL / Qwen3.5 API 分析视频内容（可通过环境变量选择 Flash 或 Plus 模型）
   - 模型输出两部分：
     - `events_to_append`：续写的事件列表（event_id, start_time, end_time, event_type, person_ids, equipment, description）
     - `appearance_updates`：外貌更新操作（add/update/merge）
   - 应用外貌更新到缓存（使用并查集管理合并关系）
   - 生成结构化的事件列表（EventLog），事件不加密直接写入数据库和 JSONL 文件
3. **数据存储**（动态上下文模式）：
   - 事件立即写入 SeekDB 的 `logs_raw` 表（不加密，structured 字段包含 person_ids 列表）
   - 同时写入 `logs_debug/event_logs.jsonl` 用于调试
   - 人物外貌表缓存在内存中，每处理 N 个分段自动保存到 `logs_debug/appearances_today.json`
   - 每个分段理解后立即写入数据库，不等待所有分段完成
4. **日终处理**（脚本驱动）：
   - 使用 `scripts/end_of_day.py` 执行，处理 `logs_debug/appearances.json`。
   - **去重压缩**：执行并查集路径压缩，将同一人的多个临时编号映射到最终主编号。
   - **隐私加密（核心逻辑）**：
     - 如果记录关联了 `user_id`：从数据库获取该用户的 RSA 公钥，对 `appearance` 和 `user_id` 进行混合加密。
     - 如果记录无 `user_id`：以明文形式直接入库。
     - 如果有 `user_id` 但系统中缺失公钥：脚本将报错中止，防止隐私泄露。
   - **数据入库**：
     - 写入 `person_appearances` 表（复合主键：`person_id` + `date`）。
     - 写入 `field_encryption_keys` 表（双字段索引：`ref_id`=person_id, `ref_date`=nominal_date, `user_id`=NULL）。
   - **状态更新（暂未实现）**：遍历数据库中当天的事件，将 `structured` 数据中的旧人物编号（已被合并的编号）更新为最终的主编号。
   - **触发索引**：自动调用 `scripts/index_events.py` 对当天所有新事件进行向量化。
5. **索引构建**（手动触发）：
   - 使用 `scripts/index_events.py` 手动触发索引
   - 对未索引的事件（`is_indexed = FALSE`）进行分块和嵌入
   - 使用配置的分块策略聚合事件日志（默认：每个事件一个块）
   - 生成文本向量嵌入（Qwen text-embedding-v4，1024 维）
   - 写入 `logs_embedding` 表，支持后续的向量搜索
   - 索引完成后，将相关事件的 `is_indexed` 字段更新为 `TRUE`

### 日志分块与嵌入
- **默认行为**：视频处理不进行索引（分块和嵌入），每个分段理解后立即写入数据库
- **索引触发方式**：
  - 手动触发：使用 `scripts/index_events.py` 对未索引的事件进行分块和嵌入
  - 生产环境：在特定时间（如凌晨）通过定时任务调用 `scripts/index_events.py` 批量执行索引
- **索引状态跟踪**：
  - `logs_raw` 表新增 `is_indexed` 字段，标记事件是否已索引
  - 新插入的事件默认 `is_indexed = FALSE`
  - 索引完成后，相关事件的 `is_indexed` 字段更新为 `TRUE`
- **分块策略**：模块化设计，支持多种分块策略
  - 默认策略：每个事件一个块
  - 时间窗口策略：按时间窗口（可配置，默认 7.5 分钟）聚合事件
  - 无人事件间隔策略：以无人事件为间隔进行分块
  - LLM 智能分块策略：预留接口，支持未来使用 LLM 进行语义分块
- **向量嵌入**：使用 Qwen text-embedding-v4 生成 1024 维向量
- **向量搜索**：支持语义搜索，使用余弦距离进行相似度计算

## 目录结构

```
lab-log/
├── streaming_server/    # WebSocket 流媒体服务器
│   ├── server.py            # WebSocket 服务器（接收MP4分段，实时处理）
│   ├── test_qr_server.py    # 测试服务器（仅接收和保存MP4分段，打印二维码识别结果）
│   ├── h264_parser.py       # H264流解析器（关键帧检测）
│   └── monitoring.py        # 监控和统计模块
├── web_api/            # FastAPI RESTful API
│   ├── main.py              # FastAPI 应用入口
│   ├── dependencies.py      # 依赖注入
│   ├── auth.py              # 认证逻辑（bcrypt、session）
│   ├── routers/             # API 路由
│       │   ├── auth.py          # 认证路由（注册、登录）
    │   │   ├── users.py         # 用户路由（用户信息、二维码）
    │   │   ├── admin.py         # Admin 路由（数据库查看、向量搜索）
    │   │   └── emergencies.py   # 紧急情况路由（报警查询、状态处理）
    │   └── models/              # Pydantic 数据模型
    ├── web_ui/              # React 前端
    │   ├── src/
    │   │   ├── components/      # React 组件
    │   │   │   ├── Login.jsx           # 登录页面
    │   │   │   ├── Register.jsx       # 注册页面
    │   │   │   ├── UserDashboard.jsx  # 用户中心
    │   │   │   ├── AdminDashboard.jsx # 数据库查看
    │   │   │   ├── VectorSearch.jsx   # 向量搜索
    │   │   │   ├── Emergencies.jsx    # 紧急通知管理
    │   │   │   ├── QRCode.jsx         # 二维码展示
    │   │   │   └── Navbar.jsx         # 导航栏
│   │   ├── hooks/          # React Hooks
│   │   │   └── useAuth.js  # 认证状态管理
│   │   └── api/            # API 客户端
│   └── package.json        # 前端依赖
├── config/              # 配置模块
├── context/             # 动态上下文模块
│   ├── appearance_cache.py      # 人物外貌缓存管理器（并查集）
│   ├── event_context.py         # 事件上下文查询（从 JSONL 文件读取）
│   └── prompt_builder.py        # 动态提示词构建器
├── storage/             # 数据库存储
├── segmentation/        # 视频分段
├── video_processing/    # 视频理解
│   ├── qwen3_vl_processor.py        # 处理器工厂（根据环境变量选择模型）
│   ├── qwen3_vl_flash_processor.py  # Qwen3-VL Flash 处理器
│   ├── qwen3_vl_plus_processor.py   # Qwen3-VL Plus 处理器
│   ├── qwen35_flash_processor.py    # Qwen3.5 Flash 处理器
│   └── qwen35_plus_processor.py     # Qwen3.5 Plus 处理器
├── log_writer/          # 日志写入与加密
├── indexing/            # 分块与嵌入
│   ├── chunker.py              # 分块器（策略模式）
│   ├── chunking_strategies.py  # 分块策略实现
│   └── embedding_service.py    # 向量嵌入服务
├── orchestration/       # 流程编排
├── utils/               # 工具函数
│   └── segment_time_parser.py  # 分段时间解析工具函数
├── nginx/               # Nginx 配置
│   └── lab-log.conf     # Nginx 反向代理配置
├── scripts/             # 工具脚本
│   ├── process_video.py              # 视频处理入口（处理未分段视频）
│   ├── process_recording_session.py  # 处理已保存的采集会话（包含二维码结果）
│   ├── concat_videos.py              # 连接录制会话中的视频片段（重新编码并统一帧率）
│   ├── index_events.py              # 手动触发索引（分块和嵌入）
│   ├── end_of_day.py                # 日终处理脚本（外貌缓存压缩、加密入库、更新事件 person_ids）
│   ├── init_database.py             # 数据库初始化
│   ├── clear_test_data.py           # 清空测试数据
│   ├── test_segmentation.py         # 测试分段功能
│   ├── analyze_keyframes.py         # 分析关键帧
│   ├── extract_segment_aligned.py   # 对齐关键帧提取片段
│   └── test_vector_search.py        # 测试向量搜索
├── start.sh             # 启动脚本（后端+前端+Nginx）
├── stop.sh              # 停止脚本
└── logs_debug/          # 调试日志（JSONL 格式）
```

## 技术栈

### 后端

- **Python 3.10+**：主要开发语言
- **uv**：快速 Python 包管理工具
- **FastAPI**：现代、快速的 Web 框架，用于构建 API
- **SeekDB**：AI 原生混合搜索数据库（支持向量、全文、JSON）
- **Qwen3-VL Flash / Plus**：视频理解模型（DashScope API）
- **Qwen3.5 Flash / Plus**：视频理解模型（DashScope API）
- **Gemini 2.5 Flash**：视频理解模型（OpenRouter API）
- **Qwen text-embedding-v4**：文本向量嵌入模型（1024 维）
- **ffmpeg/ffprobe**：视频处理和分段
- **Cryptography**：混合加密（AES-GCM + RSA-OAEP）
- **bcrypt**：密码哈希加密

### Android 采集端

- **Kotlin**：主要开发语言
- **CameraX**：相机框架，支持 Preview 和 ImageAnalysis
- **MediaCodec**：H.264 硬件编码
- **MediaMuxer**：MP4 封装
- **ML Kit Barcode Scanning**：二维码识别（版本 17.3.0+，支持 16KB 页面大小）
- **OkHttp**：WebSocket 客户端

### 前端

- **React**：用户界面库
- **Vite**：快速的前端构建工具
- **React Router**：客户端路由
- **Axios**：HTTP 客户端
- **WebCrypto API**：浏览器原生加密 API，用于生成密钥对

### 基础设施

- **Nginx**：反向代理服务器，统一前端和后端访问
- **Docker**：用于运行 SeekDB 容器
