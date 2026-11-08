# lab-vision-logger

**把实验室摄像头的连续画面，自动转成可检索的结构化事件日志。**

摄像头采集 → 关键帧对齐分段 → 动态上下文 → 视觉大模型 → 事件落库 → 日终加密与向量索引。

> 团队竞赛项目（“玻尔 + SciMaster” 科研智能体开发大赛，2025）。
> 仓库由原团队代码整理而来，提交历史压缩为单个初始提交。分工见 [Credits](#credits)，
> 原始仓库：[YangYixin0/lab-log](https://github.com/YangYixin0/lab-log)。

---

## 它解决什么问题

实验室里"谁在什么时候用了什么设备、动了什么试剂"，过去只能靠人写记录，写完也没人查。
这个系统让摄像头持续看，把画面变成一行行带时间戳、带人物编号、可被语义检索的事件。

难点不在"调视觉模型"，在三件事：

1. **视频是连续的，模型一次只能看 60 秒。** 逐段独立识别会导致同一个人在不同段里拿到不同编号。
2. **身份是渐进的。** 一个人可能先穿白大褂、后来脱了；可能被识别成两个编号，需要事后合并。
3. **画面里全是隐私。** 外貌特征落库前必须加密，而且缺公钥时宁可不入库也不能明文存。

## 架构

```
Android 采集端 (Kotlin/CameraX, ML Kit 二维码)
        │  H.264 分段 + 每段前置 SPS/PPS，WebSocket 上报
        ▼
streaming_server/         接收分段，落盘，喂管线
        ▼
segmentation/             关键帧（I 帧）对齐切段，迭代式保证连续无重叠
        ▼
context/                  动态上下文：当天最新 N 条事件 + 人物外貌表 + 二维码结果
        ▼
video_processing/         Qwen3-VL / Qwen3.5 / Gemini 2.5 → 续写事件 + 外貌更新
        ▼
log_writer/ + storage/    事件即时入库（logs_raw）；外貌表缓存在内存
        ▼
scripts/end_of_day.py     并查集压缩 → 按用户公钥加密 → 入库 → 触发索引
        ▼
indexing/                 分块 + 向量嵌入（1024 维），支持语义检索
        ▼
web_api/ + web_ui/        FastAPI + React：用户中心、数据浏览、向量搜索、紧急事件告警
```

## 跑起来

```bash
docker run -d --name seekdb -p 2881:2881 quay.io/oceanbase/seekdb:latest
cp .env.example .env          # 填 DASHSCOPE_API_KEY
./scripts/install_deps.sh     # uv venv + 依赖
python scripts/init_database.py
./start.sh                    # 后端 8000 + 前端 5173 + Nginx 50001
```

离线处理一个已有视频：

```bash
python scripts/process_video.py /path/to/video.mp4
python scripts/index_events.py          # 索引需手动触发
```

## 三个值得看的技术点

- **分段必须对齐关键帧**，且每段开头要补完整的 SPS/PPS，否则该段 MP4 无法独立解码。
  见 [docs/segmentation-and-h264.md](docs/segmentation-and-h264.md)
- **跨段身份一致性**用并查集维护：模型分配临时编号，合并方向固定为小号→大号，日终做路径压缩。
  见 [docs/identity-merge.md](docs/identity-merge.md)
- **隐私加密放在日终而不是写入时**：采集阶段需要明文外貌做比对，日终一次加密入库；
  有 `user_id` 但缺公钥时**报错中止**，不降级为明文。见 [docs/privacy-design.md](docs/privacy-design.md)

另外三篇硬件与协议上的踩坑记录（SPS 长度判定、NV12/I420 色彩格式、WebSocket 16MB 队列上限）
在 [docs/field-notes.md](docs/field-notes.md) —— 这三个问题都只有真机跑才会遇到。

## 文档

| 文档 | 内容 |
|---|---|
| [docs/architecture.md](docs/architecture.md) | 模块划分、两种运行路径、数据流、目录结构 |
| [docs/operations.md](docs/operations.md) | 部署、配置、日志查询、注意事项 |
| [docs/MODULES.md](docs/MODULES.md) | 模块边界，以及当前三处不健康的耦合 |
| [docs/mvp-architecture-and-interface.md](docs/mvp-architecture-and-interface.md) | MVP 阶段的设计边界（历史记录） |

## 技术栈

Python 3.10+ · FastAPI · SeekDB（OceanBase，向量+全文+关系）· Qwen3-VL / Gemini 2.5 Flash ·
React + Vite · Android Kotlin（CameraX / MediaCodec / ML Kit）· Nginx · Docker

## Credits

团队项目，两人协作，完整提交历史保留在本仓库。

| 模块 | 负责 |
|---|---|
| `segmentation/` `context/` `log_writer/`（含日终加密） | [@Tania-X](https://github.com/Tania-X) |
| `streaming_server/` `web_api/` `web_ui/` `android-camera/` | [@YangYixin0](https://github.com/YangYixin0) |
| `video_processing/` `indexing/` | 共同 |

模块边界与当前已知的耦合问题见 [docs/MODULES.md](docs/MODULES.md)。

## License

MIT — 见 [LICENSE](LICENSE)。
