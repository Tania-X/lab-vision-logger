# 模块边界与已知耦合

> 这份文档的目的不是"证明架构很好"，而是把当前结构、依赖方向、
> 以及哪些地方耦合得不健康，明确写出来。
> 一个能指出自己架构缺陷的仓库，比一个假装没有缺陷的仓库可信。

---

## 当前结构

顶层是**按技术职责平铺**，还没有收进一个统一的包命名空间下。

| 目录 | 职责 | 对外依赖 |
|---|---|---|
| `streaming_server/` | WebSocket 接收 Android 推送的 H.264 分段；`h264_parser.py` 负责 NAL 解析与关键帧检测 | `segmentation`, `orchestration` |
| `segmentation/` | 关键帧对齐切段，迭代式保证连续无重叠 | `utils` |
| `context/` | 动态上下文：`event_context`（读 JSONL 最近 N 条）、`appearance_cache`（并查集 + 外貌表）、`prompt_builder` | `storage`（仅 models） |
| `video_processing/` | 视觉模型适配层。一个处理器工厂 + 多个 provider 实现 | `storage`（models）, `context`（prompt 结构） |
| `log_writer/` | 事件写入 + 字段级加密（AES-GCM + RSA-OAEP） | `storage` |
| `storage/` | SeekDB 客户端、数据模型、DDL | 无（最底层） |
| `indexing/` | 分块策略（策略模式）+ 向量嵌入 | `storage` |
| `orchestration/` | 把上面这些串成一条管线 | 几乎全部 |
| `web_api/` | FastAPI 路由层 | `storage`, `indexing`, `log_writer` |
| `web_ui/` | React 前端，只跟 `web_api` 通信 | — |
| `config/` | 环境变量读取 | 无 |
| `utils/` | 时间解析等零散工具 | 无 |

依赖方向大致是单向的：

```
storage ← log_writer / indexing / context
   ↑
video_processing → context
   ↑
orchestration → streaming_server / scripts
   ↑
web_api → web_ui
```

---

## 已知的三处不健康耦合

### 1. `orchestration/` 是上帝对象

它 import 了几乎所有模块，导致任何单模块的测试都得先绕过它。
更干净的形态是：每个阶段暴露一个 `Stage` 接口（输入/输出都是纯数据），
`orchestration` 只负责按顺序调用，不碰内部实现。**未做。**

### 2. 身份合并逻辑埋在 `context/appearance_cache.py` 里

并查集（`union_find`）、外貌表存储、prompt 序列化三件事在同一个文件里。
并查集本身是一个**与视觉模型无关的纯数据结构**，被塞进"上下文构建"这个域里，
导致它既不好测，也不好复用。

**这是最应该拆的一处**：`identity/union_find.py`（纯数据结构）+ `identity/registry.py`（编号与合并记录），
`context/` 只负责把结果序列化进 prompt。

### 3. 两套管线并存

`video_processing/` 下同时有"动态上下文模式"和"传统模式"两条路径，
README 里写的是"传统模式未来将移除"。两套并存让"哪条是主路径"变得模糊，
也是新人（或未来的自己）最容易改错的地方。**建议直接删掉传统模式。**

---

## 刻意没做的事

- **没有改成 `src/lab-logger/` 的包布局**：收益是 import 路径规范，成本是全仓库改 import + 回归，
  而当前测试覆盖不足以保证改完不出问题。等测试补齐了再说。
- **没有引入 DI 容器 / 抽象基类工厂**：模块数量还不到需要这些的程度，加了反而是负担。
- **没有拆 `config/`**：20+ 个环境变量确实该收敛到 `pydantic-settings`，但它不影响主链路正确性，
  优先级低于把两套管线合并。

---

## 测试现状

**55 个用例：11 通过 / 34 失败 / 10 error。**

这不是"偶尔红"，是整套测试写于 `storage.models` 重构之前，接口已经变了：

| 测试引用的东西 | 现在的状态 |
|---|---|
| `VideoUnderstandingResult.persons / equipment / emergencies` | 字段已删除，只剩 `segment_id / remark / events` |
| `PersonInfo` | 类型已不存在 |
| `web_api.dependencies.verify_session` | 已改名 |
| `web_api.routers.users.generate_qr_data` | 已移走 |
| `log_writer.writer.FieldEncryptionService` | 已替换 |

`tests/test_orchestration.py` 和 `tests/test_streaming_server.py` 在采集期就 ImportError，
会中断整个收集过程（其余用例一个都跑不了），所以已在 `tests/conftest.py` 里用
`collect_ignore` 排除。

CI 里 pytest 这一步是**非阻塞**的：先让它跑起来作为观察窗口，不为它停下主链路。
重写测试这件事记在这里，不装成"已经通过"。

**如果要补，优先级**：
1. `end_of_day.py` 的加密路径（含"缺公钥必须中止"那条）
2. 并查集合并与路径压缩
3. 关键帧分段的边界（连续、不重叠、单段上限）
