---
title: FastAPI + Celery 异步/同步架构重构：从事件循环冲突到统一后台任务模型
description: 深度剖析 Python 异步/同步混合架构中的事件循环冲突、协程未 await、SQLAlchemy 外键解析等问题，以及如何通过职责分离实现稳定的后台任务处理系统
author: Alden
date: 2025-12-25 10:21:00 +0800
categories: [Coding Lab]
tags: [python, fastapi, celery, asyncio, sqlalchemy, architecture, best practice]
pin: false
mermaid: true
comments: true
---

## 问题背景

在一个基于 Python 3.12 + FastAPI + SQLAlchemy + aiomysql + Celery + Redis 的视频处理系统中，执行端到端测试脚本 `test_full_pipeline.py` 时，发现任务状态异常：

- 一段 30 秒的视频，切片任务超过 500 秒仍未完成
- 任务状态始终停留在 `pending`，进度为 0%
- 服务端日志显示 SQL 查询正常执行，但状态未更新

技术栈构成：
- Web 框架：FastAPI（async）
- ORM：SQLAlchemy 2.0 + aiomysql（async）+ pymysql（sync）
- 任务队列：Celery + Redis
- 日志：structlog + asyncio.Queue + 后台 Worker 批量写入 MySQL

系统架构中存在两套数据库会话工厂，这是后续问题的伏笔：

```python
# database.py
# 同步引擎（Alembic 迁移、Celery Worker）
sync_engine = create_engine(settings.DATABASE_URL, ...)
SessionLocal = sessionmaker(bind=sync_engine)

# 异步引擎（FastAPI API 层、Service 层）
async_engine = create_async_engine(settings.ASYNC_DATABASE_URL, ...)
AsyncSessionLocal = async_sessionmaker(bind=async_engine, class_=AsyncSession)
```
{: file="app/db/database.py" }

## 第一阶段：协程未 await 问题

### 观察到的现象

Celery Worker 日志显示任务"成功完成"，但数据库状态未更新：

```
[WARNING] RuntimeWarning: coroutine 'TaskService.save_scene_result' was never awaited
[WARNING] RuntimeWarning: coroutine 'TaskService.update_task_progress' was never awaited
[WARNING] RuntimeWarning: coroutine 'TaskService.update_task_status' was never awaited
[INFO] Task process_video_task succeeded in 23.1s: {'status': 'completed', 'scenes': 19}
```

客户端轮询结果：
```
状态: pending, 进度: 0%
状态: pending, 进度: 0%
...（持续 500+ 秒）
```

关键矛盾点：Celery 日志显示 `succeeded`，但客户端看到的状态是 `pending`。这说明任务执行了，但数据库写入没有生效。

> Python 的 `RuntimeWarning: coroutine was never awaited` 是一个容易被忽略的警告，它不会阻止程序继续执行，但意味着异步操作被跳过了。
{: .prompt-warning }

### 根因分析

`TaskService` 的方法签名为 `async def`，但 Celery task 是同步函数。直接调用 `task_service.update_task_status()` 只是创建了协程对象，没有执行：

```python
# TaskService（为 FastAPI 设计的异步服务）
class TaskService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def update_task_status(self, task_id: str, status: TaskStatus, ...):
        task = await self.get_task(task_id)
        task.status = status
        await self.db.commit()

# Celery task（同步函数）
@celery_app.task
def process_video_task(self, task_id: str, ...):
    db = SessionLocal()  # ← 同步 Session
    task_service = TaskService(db)  # ← 传入同步 Session 给期望 AsyncSession 的服务
    task_service.update_task_status(task_id, TaskStatus.COMPLETED)  # ← 返回协程对象，未执行
```
{: file="app/workers/video_processor.py" }

### 方案对比与决策

**方案 A：用 `asyncio.run()` 包装异步调用**

```python
def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)

@celery_app.task
def process_video_task(self, task_id: str, ...):
    async def _process():
        async with AsyncSessionLocal() as db:
            task_service = TaskService(db)
            await task_service.update_task_status(task_id, TaskStatus.COMPLETED)
    
    run_async(_process())
```

| 维度 | 评估 |
|------|------|
| 复杂度 | 中等，需要处理事件循环 |
| 性能 | 有开销（事件循环切换） |
| 稳定性 | **潜在风险**：Celery prefork worker 是 fork 出来的子进程，`asyncio.get_event_loop()` 可能拿到父进程已关闭的循环 |
| 代码维护 | 复用现有代码，但混用 async/sync |
| 调试 | 较难（异步堆栈） |

**方案 B：在 Worker 中使用同步数据库操作**

```python
def sync_update_task_status(db: Session, task_id: str, status: TaskStatus, ...):
    task = db.execute(select(Task).where(Task.id == task_id)).scalar_one_or_none()
    if task:
        task.status = status
        db.commit()

@celery_app.task
def process_video_task(self, task_id: str, ...):
    db = SessionLocal()
    try:
        sync_update_task_status(db, task_id, TaskStatus.COMPLETED)
    finally:
        db.close()
```

| 维度 | 评估 |
|------|------|
| 复杂度 | 低，直接同步调用 |
| 性能 | 更高效，原生同步 |
| 稳定性 | 稳定，Celery 天然同步 |
| 代码维护 | 职责分离，各司其职 |
| 调试 | 简单直观 |

**决策：选择方案 B**

核心理由：

1. **Celery 本质是同步的** - Celery 的 prefork 模型基于多进程，每个 worker 是独立的同步进程，强行塞异步代码是逆流而上
2. **事件循环风险** - `asyncio.get_event_loop()` 在 fork 的 worker 进程中行为不可预测，可能抛出 `RuntimeError: There is no current event loop`
3. **已有同步 Session** - `database.py`{: .filepath} 中已经定义了 `SessionLocal`（同步会话工厂），无需额外配置
4. **职责清晰** - FastAPI 用 async，Celery 用 sync，边界分明，便于维护

> Celery 的 prefork 模型基于多进程，每个 worker 是独立的同步进程。在这种环境中强行使用异步代码会引入不可预测的事件循环问题。
{: .prompt-tip }

### 实施：同步数据库操作

在 `video_processor.py`{: .filepath} 中新增同步数据库操作函数：

```python
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.models.task import Task, TaskStatus
from app.models.scene import Scene

def sync_update_task_status(db: Session, task_id: str, status: TaskStatus, error_message: str | None = None):
    """同步更新任务状态"""
    task = db.execute(select(Task).where(Task.id == task_id)).scalar_one_or_none()
    if not task:
        return
    task.status = status
    task.updated_at = datetime.now(timezone.utc)
    if status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
        task.completed_at = datetime.now(timezone.utc)
    if error_message:
        task.error_message = error_message
    db.commit()

def sync_update_task_progress(db: Session, task_id: str, processed_frames: int, total_frames: int):
    """同步更新任务进度"""
    task = db.execute(select(Task).where(Task.id == task_id)).scalar_one_or_none()
    if not task:
        return
    task.processed_frames = processed_frames
    task.total_frames = total_frames
    task.progress = int((processed_frames / total_frames) * 100) if total_frames > 0 else 0
    task.updated_at = datetime.now(timezone.utc)
    db.commit()

def sync_save_scene_result(db: Session, task_id: str, scene_num: int, frame_number: int, motion_value: float, original_path: str):
    """同步保存场景切片结果"""
    scene = Scene(
        task_id=task_id,
        scene_num=scene_num,
        frame_number=frame_number,
        motion_value=motion_value,
        original_path=original_path,
    )
    db.add(scene)
    db.commit()
```
{: file="app/workers/video_processor.py" }

Celery task 改为使用同步函数：

```python
@celery_app.task(bind=True, name="process_video_task")
def process_video_task(self, task_id: str, video_path: str, params: dict) -> dict:
    db = SessionLocal()
    try:
        sync_update_task_status(db, task_id, TaskStatus.PROCESSING)
        # ... 业务逻辑 ...
        sync_update_task_status(db, task_id, TaskStatus.COMPLETED)
        return {"task_id": task_id, "status": "completed", "scenes": total_scenes}
    except Exception as e:
        sync_update_task_status(db, task_id, TaskStatus.FAILED, error_message=str(e))
        raise
    finally:
        db.close()
```
{: file="app/workers/video_processor.py" }

## 第二阶段：SQLAlchemy 外键解析失败

### 观察到的现象

重启 Celery Worker 后出现新错误：

```
sqlalchemy.exc.NoReferencedTableError: Foreign key associated with column 
'tasks.video_id' could not find table 'videos' with which to generate a 
foreign key to target column 'id'
```

完整堆栈显示错误发生在 `db.commit()` 时的 flush 阶段：

```
File "video_processor.py", line 63, in sync_update_task_status
    db.commit()
File "sqlalchemy/orm/session.py", line 2030, in commit
    trans.commit(_to_root=True)
...
File "sqlalchemy/orm/mapper.py", line 4073, in _sorted_tables
    sorted_ = sql_util.sort_tables(...)
...
sqlalchemy.exc.NoReferencedTableError: Foreign key associated with column 
'tasks.video_id' could not find table 'videos'
```

### 根因分析

SQLAlchemy ORM 在 flush 时需要解析所有外键关系，以确定表的写入顺序。`Task` 模型定义了外键：

```python
# models/task.py
class Task(Base):
    __tablename__ = "tasks"
    video_id = Column(String(36), ForeignKey("videos.id"), nullable=False)
```
{: file="app/models/task.py" }

当 SQLAlchemy 尝试 commit 时，它需要知道 `videos` 表的元数据来解析这个外键。但在 Celery worker 进程中，只导入了 `Task` 和 `Scene` 模型：

```python
# video_processor.py（问题代码）
from app.models.task import Task, TaskStatus
from app.models.scene import Scene
# Video 模型未导入 → videos 表未注册到 metadata
```
{: file="app/workers/video_processor.py" }

> FastAPI 应用启动时，通常会在某处（如 `main.py`{: .filepath} 或 `models/__init__.py`{: .filepath}）导入所有模型，确保它们都注册到 `Base.metadata`。但 Celery worker 是独立进程，只导入了 `video_processor.py`{: .filepath} 及其依赖。
{: .prompt-info }

### 解决方案

显式导入外键依赖的模型，即使代码中不直接使用：

```python
# video_processor.py
from app.models.scene import Scene
from app.models.task import Task, TaskStatus
from app.models.video import Video  # noqa: F401 - 必须导入，Task 外键依赖
```
{: file="app/workers/video_processor.py" }

`# noqa: F401` 注释告诉 linter 这个导入是有意为之，不是未使用的导入。

> 在使用 SQLAlchemy ORM 的多进程架构中，每个进程都需要确保所有相关模型被导入。可以在 `models/__init__.py`{: .filepath} 中统一导出所有模型，或在 worker 入口处导入 `from app.models import *`。
{: .prompt-tip }

## 第三阶段：VLM 分析的事件循环冲突

### 观察到的现象

视频切片任务正常完成后，VLM 分析任务失败：

```
状态: completed, 进度: 100%
切片完成!
[3/5] 启动控件检测...
响应: 控件检测任务已启动，请轮询状态接口获取进度
等待控件检测完成...
状态: processing, 进度: 0% (0/0)
状态: failed, 进度: 0% (0/0)
错误: Task <Task pending name='Task-150' coro=<_run_analysis_sync.<locals>._run_async()...> 
got Future <Future pending> attached to a different loop
```

完整异常堆栈：

```
RuntimeError: Task <Task pending name='Task-150' 
coro=<_run_analysis_sync.<locals>._run_async() running at vlm.py:90> 
cb=[_run_until_complete_cb() at asyncio/base_events.py:181]> 
got Future <Future pending> attached to a different loop

Traceback:
  File "vlm.py", line 90, in _run_async
    result = await service.analyze_scenes(...)
  File "vlm_service.py", line 284, in analyze_scenes
    result = await self.db.execute(query)
  File "sqlalchemy/ext/asyncio/session.py", line 449, in execute
    result = await greenlet_spawn(...)
  ...
  File "aiomysql/connection.py", line 494, in ping
    await self._read_ok_packet()
  ...
RuntimeError: ... got Future <Future pending> attached to a different loop
```

### 根因分析

VLM 分析使用 FastAPI 的 `BackgroundTasks`，当时的实现：

```python
# vlm.py
def _run_analysis_sync(task_id: str, detect_type: DetectType, scene_ids: list[int] | None):
    from app.db.database import AsyncSessionLocal
    
    async def _run_async():
        async with AsyncSessionLocal() as db:  # ← 问题所在
            service = VLMService(db)
            result = await service.analyze_scenes(task_id, detect_type, scene_ids, ...)
    
    asyncio.run(_run_async())  # ← 创建新事件循环

@router.post("/analyze")
async def analyze_scenes(request: VLMAnalyzeRequest, background_tasks: BackgroundTasks, ...):
    background_tasks.add_task(_run_analysis_sync, task_id, detect_type, request.scene_ids)
```

**问题链条**：

1. `AsyncSessionLocal` 是在 FastAPI 启动时创建的，其底层的 `async_engine` 绑定到 FastAPI 的主事件循环
2. `BackgroundTasks` 在后台线程中执行 `_run_analysis_sync`
3. `asyncio.run()` 在该线程中创建一个**新的**事件循环
4. 当 `AsyncSessionLocal()` 创建 session 时，它尝试复用已有的数据库连接
5. 这些连接的 Future 对象绑定在主事件循环上，但当前运行的是新循环
6. 抛出 `got Future attached to a different loop`

**曾经尝试的补丁方案**：

在 `asyncio.run()` 内部创建独立的数据库引擎：

```python
async def _run_async():
    # 在新的事件循环中创建独立的数据库引擎和会话
    engine = create_async_engine(settings.ASYNC_DATABASE_URL, pool_size=5, ...)
    async_session = async_sessionmaker(bind=engine, class_=AsyncSession, ...)
    
    async with async_session() as db:
        try:
            service = VLMService(db)
            result = await service.analyze_scenes(...)
        finally:
            await engine.dispose()  # 用完释放

asyncio.run(_run_async())
```

这个方案可以工作，但存在问题：
- 每次任务创建/销毁连接池，开销大
- 补丁式修复，不够优雅
- 如果多处使用 `BackgroundTasks`，需要重复这个模式

### 架构层面的反思

| 场景 | 当前实现 | 问题 |
|------|----------|------|
| 视频切片 | Celery worker | 已改为同步，正常工作 |
| VLM 分析 | FastAPI BackgroundTasks | 事件循环冲突 |

**`BackgroundTasks` 适合这个场景吗？**

`BackgroundTasks` 的设计初衷是轻量级后台操作：
- 发送邮件通知
- 写入日志
- 清理临时文件

VLM 分析的特点：
- 长时间运行（分钟级）
- IO 密集（调用外部 API）
- 需要进度追踪
- 可能需要重试机制

**结论**：VLM 分析应该迁移到 Celery，与视频切片保持一致的架构。

## 第四阶段：日志模块的跨进程兼容性评估

在将 VLM 分析迁移到 Celery 之前，需要评估现有日志模块是否支持跨进程场景。

### 当前日志架构

系统使用了一套基于 structlog + asyncio.Queue 的审计日志方案：

```mermaid
graph LR
    A[@audit_log 装饰器] --> B[asyncio.Queue<br/>进程内]
    B --> C[log_writer_worker<br/>FastAPI lifespan]
    C --> D[AsyncSessionLocal]
    D --> E[(MySQL)]
    
    style A fill:#e1f5ff
    style B fill:#fff4e6
    style C fill:#e8f5e9
    style D fill:#f3e5f5
    style E fill:#fce4ec
```

关键组件实现：

```python
# logger.py - 进程内队列
_log_queue: asyncio.Queue[dict[str, Any]] | None = None

def get_log_queue() -> asyncio.Queue[dict[str, Any]]:
    global _log_queue
    if _log_queue is None:
        _log_queue = asyncio.Queue(maxsize=settings.AUDIT_LOG_QUEUE_SIZE)
    return _log_queue

def _db_persistence_processor(logger, method_name, event_dict):
    """structlog processor：只有带 persist_db=True 标记的日志才进入队列"""
    persist_db = event_dict.pop("persist_db", False)
    if persist_db:
        audit_data = event_dict.get("audit_data")
        if audit_data:
            try:
                get_log_queue().put_nowait(audit_data)  # ← 需要事件循环
            except asyncio.QueueFull:
                pass  # 队列满时静默丢弃
    return event_dict
```
{: file="app/core/logger.py" }

```python
# audit.py - 异步装饰器
def audit_log(action: str):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):  # ← async def
            result = await func(*args, **kwargs)  # ← await
            log.info("audit_event", audit_data=..., persist_db=True)
            return result
        return wrapper
    return decorator
```
{: file="app/core/audit.py" }

### 核心问题分析

如果 VLM 分析迁移到 Celery，日志模块面临以下问题：

> ❌ `asyncio.Queue` 在 FastAPI 进程，Celery 无法访问  
> ❌ `@audit_log` 是 async def，无法装饰同步的 Celery task  
> ❌ `log_writer_worker` 只在 FastAPI lifespan 启动  
> ❌ `get_log_queue()` 需要事件循环，Celery prefork 没有
{: .prompt-danger }

| 组件 | 问题 |
|------|------|
| `asyncio.Queue` | **进程内队列**，Celery worker 是独立进程，无法访问 FastAPI 进程的队列 |
| `@audit_log` | 装饰器是 `async def wrapper`，返回协程，无法装饰同步函数 |
| `log_writer_worker` | 只在 FastAPI lifespan 启动，Celery 进程没有这个 worker |
| `get_log_queue()` | 内部调用 `asyncio.Queue()`，需要运行中的事件循环 |

尝试在 Celery worker 中使用 asyncio.Queue：

```python
# Celery worker 中
queue.put_nowait(item)  
# → RuntimeError: no running event loop
```

### 方案评估：Redis 替代 asyncio.Queue

目标架构：

```mermaid
graph TB
    subgraph FastAPI进程
        A1[@audit_log<br/>async]
    end
    
    subgraph Celery进程
        B1[Celery Task<br/>sync]
    end
    
    A1 --> C[Redis Queue<br/>LPUSH/BRPOP]
    B1 --> C
    C --> D[Log Consumer Worker<br/>批量写MySQL]
    D --> E[(MySQL)]
    
    style A1 fill:#e1f5ff
    style B1 fill:#fff4e6
    style C fill:#ffebee
    style D fill:#e8f5e9
    style E fill:#fce4ec
```

**Redis 队列能解决的问题**：

| 问题 | 解决？ | 说明 |
|------|--------|------|
| 跨进程日志收集 | ✅ | Redis 是进程间共享的 |
| Celery worker 审计日志 | ✅ | 同步 `redis.lpush()` 即可，不需要事件循环 |
| 日志不丢失 | ✅ | Redis 持久化 + 消费确认 |
| 批量写入优化 | ✅ | Consumer 可以 BRPOP 批量消费 |

**Redis 队列不能解决的问题**：

| 问题 | 解决？ | 说明 |
|------|--------|------|
| `@audit_log` 是 async | ❌ | 装饰器本身是 `async def wrapper`，无法装饰同步函数 |
| `structlog.contextvars` | ⚠️ | 同步代码中 contextvars 可用，但 Celery fork 后需要手动绑定 |
| trace_id 传递 | ⚠️ | 需要通过 Celery task 参数显式传递，不能依赖 contextvars 自动传播 |

**关键洞察**：即使改用 Redis，仍需要同步版装饰器 `@audit_log_sync`。

### 同步装饰器的风险评估

根据 `2025-12-22-async-python-log-persistence.md` 的设计原则，日志写入不应阻塞业务。评估同步版装饰器的风险：

| 环节 | 操作 | 耗时 | 阻塞风险 |
|------|------|------|----------|
| `log.info()` | structlog 格式化 | 微秒级 | ❌ 无 |
| `redis.lpush()` | 网络 IO | 1-5ms | ⚠️ 轻微 |
| MySQL 写入 | 由 Consumer Worker 执行 | - | ❌ 不在 Celery 进程 |

**结论**：Redis LPUSH 约 1-5ms，对于 Celery 长任务（秒级/分钟级）可以接受。如果需要进一步优化，可以使用 Redis pipeline 批量推送。

> 即使改用 Redis，仍需要同步版装饰器 `@audit_log_sync`。装饰器本身是 `async def wrapper`，无法装饰同步函数。
{: .prompt-info }

## 最终架构

### 日志模块重构

改造前后对比：

```python
# logger.py (旧)
_log_queue: asyncio.Queue | None = None

def _db_persistence_processor(logger, method_name, event_dict):
    if event_dict.pop("persist_db", False):
        get_log_queue().put_nowait(event_dict.get("audit_data"))
    return event_dict
```
{: file="app/core/logger.py (Before)" }

```python
# logger.py (新)
AUDIT_LOG_QUEUE_KEY = "audit_log_queue"
_redis_client = None

def _get_redis_client():
    global _redis_client
    if _redis_client is None:
        import redis
        _redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True,
        )
    return _redis_client

def push_audit_log(data: dict[str, Any]) -> bool:
    """推送审计日志到 Redis 队列，跨进程安全"""
    try:
        client = _get_redis_client()
        client.lpush(AUDIT_LOG_QUEUE_KEY, json.dumps(data, default=str))
        return True
    except Exception:
        return False  # 推送失败时静默处理，不影响业务

def _db_persistence_processor(logger, method_name, event_dict):
    if event_dict.pop("persist_db", False):
        audit_data = event_dict.get("audit_data")
        if audit_data:
            push_audit_log(audit_data)
    return event_dict
```
{: file="app/core/logger.py (After)" }

同步装饰器实现：

```python
# audit.py
def audit_log_sync(action: str):
    """同步审计日志装饰器（Celery 用）"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):  # 同步
            trace_id = kwargs.get("trace_id", "")  # 从参数获取
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                duration = time.perf_counter() - start
                push_audit_log({
                    "trace_id": trace_id,
                    "action": action,
                    "status": "success",
                    "duration": round(duration, 4),
                })
                return result
            except Exception as e:
                duration = time.perf_counter() - start
                push_audit_log({
                    "trace_id": trace_id,
                    "action": action,
                    "status": f"failed:{type(e).__name__}",
                    "duration": round(duration, 4),
                })
                raise
        return wrapper
    return decorator
```
{: file="app/core/audit.py" }

**Log Consumer Worker**：

```python
# log_worker.py
async def log_writer_worker():
    redis_client = await _get_async_redis()
    
    while True:
        batch = []
        # 使用 BRPOP 阻塞等待
        result = await redis_client.brpop(AUDIT_LOG_QUEUE_KEY, timeout=0)
        if result:
            _, data = result
            batch.append(json.loads(data))
        
        # 非阻塞获取更多日志凑批量
        while len(batch) < batch_size:
            data = await redis_client.rpop(AUDIT_LOG_QUEUE_KEY)
            if data is None:
                break
            batch.append(json.loads(data))
        
        # 批量写入 MySQL
        if batch:
            await _write_batch(batch)
```

**最终日志架构图**：

```
┌─────────────────────────────────────────────────────────────────────────┐
│  FastAPI 进程                          Celery Worker 进程               │
│  ┌─────────────┐                       ┌─────────────────┐             │
│  │ @audit_log  │                       │ @audit_log_sync │             │
│  │ (async)     │                       │ (sync)          │             │
│  └──────┬──────┘                       └────────┬────────┘             │
│         │                                       │                       │
│         ▼                                       ▼                       │
│  ┌─────────────┐                       ┌─────────────┐                 │
│  │ Processor   │                       │ push_audit  │                 │
│  │ persist_db  │                       │ _log()      │                 │
│  └──────┬──────┘                       └──────┬──────┘                 │
│         │                                     │                         │
│         └──────────────┬──────────────────────┘                         │
│                        ▼                                                │
│              ┌─────────────────────────┐                               │
│              │   Redis List (LPUSH)    │                               │
│              │   audit_log_queue       │                               │
│              └───────────┬─────────────┘                               │
│                          ▼                                              │
│              ┌─────────────────────────┐                               │
│              │   log_writer_worker     │  ← FastAPI lifespan 启动      │
│              │   (BRPOP + 批量写)       │                               │
│              └───────────┬─────────────┘                               │
│                          ▼                                              │
│                       MySQL                                             │
└─────────────────────────────────────────────────────────────────────────┘
```

### VLM 分析迁移到 Celery

**VLM Worker 实现**：

```python
# vlm_worker.py
from app.core.vlm_analyzer import VLMAnalyzer, DetectType
from app.db.database import SessionLocal
from app.models.scene import Scene
from app.models.task import Task  # noqa: F401 - Scene 外键依赖
from app.models.video import Video  # noqa: F401 - Task 外键依赖

@celery_app.task(bind=True, name="vlm_analyze_task")
def vlm_analyze_task(
    self,
    task_id: str,
    detect_type: DetectType,
    scene_ids: list[int] | None = None,
    trace_id: str = "",
) -> dict:
    db = SessionLocal()
    try:
        # 查询场景
        query = select(Scene).where(Scene.task_id == task_id).order_by(Scene.scene_num)
        scenes = db.execute(query).scalars().all()
        
        # 进度回调
        def progress_callback(processed: int, total: int):
            self.update_state(
                state="PROGRESS",
                meta={"current": processed, "total": total, "progress": int(processed/total*100)},
            )
        
        # 执行分析（同步版本）
        analyzer = VLMAnalyzer()
        results = analyzer.analyze_scenes_batch(
            scenes=[{"scene_num": s.scene_num, "original_path": s.original_path} for s in scenes],
            detect_type=detect_type,
            progress_callback=progress_callback,
        )
        
        # 保存结果
        result_path = VLMAnalyzer.save_results(task_id, detect_type, results)
        return {"task_id": task_id, "status": "completed", "total_scenes": len(results)}
    finally:
        db.close()
```

**API 层改造**：

```python
# vlm.py
from celery.result import AsyncResult
from app.workers.vlm_worker import vlm_analyze_task

_celery_task_map: dict[str, str] = {}  # {task_id_detect_type: celery_task_id}

@router.post("/analyze")
async def analyze_scenes(request: VLMAnalyzeRequest, ...):
    # 检查是否已有结果
    existing = VLMAnalyzer.load_results(task_id, detect_type)
    if existing:
        return VLMAnalyzeStartResponse(status="completed", ...)
    
    # 检查是否有正在运行的 Celery 任务
    status_key = f"{task_id}_{detect_type}"
    if status_key in _celery_task_map:
        celery_result = AsyncResult(_celery_task_map[status_key])
        if celery_result.state in ["PENDING", "STARTED", "PROGRESS"]:
            return VLMAnalyzeStartResponse(status="processing", ...)
    
    # 启动 Celery 任务
    ctx = structlog.contextvars.get_contextvars()
    trace_id = ctx.get("trace_id", "")
    
    celery_task = vlm_analyze_task.delay(
        task_id=task_id,
        detect_type=detect_type,
        scene_ids=request.scene_ids,
        trace_id=trace_id,  # 显式传递 trace_id
    )
    _celery_task_map[status_key] = celery_task.id
    
    return VLMAnalyzeStartResponse(status="processing", ...)

@router.get("/{task_id}/status")
async def get_status(task_id: str, detect_type: DetectType):
    # 先检查文件结果
    result = VLMAnalyzer.load_results(task_id, detect_type)
    if result:
        return VLMStatusResponse(status="completed", ...)
    
    # 检查 Celery 任务状态
    status_key = f"{task_id}_{detect_type}"
    if status_key in _celery_task_map:
        celery_result = AsyncResult(_celery_task_map[status_key])
        if celery_result.state == "PROGRESS":
            meta = celery_result.info or {}
            return VLMStatusResponse(
                status="processing",
                progress=meta.get("progress", 0),
                processed_scenes=meta.get("current", 0),
                total_scenes=meta.get("total", 0),
            )
        elif celery_result.state == "FAILURE":
            return VLMStatusResponse(status="failed", error=str(celery_result.result))
    
    return VLMStatusResponse(status="idle", ...)
```

**Celery 配置更新**：

```python
# celery_app.py
celery_app = Celery(
    "video_processor",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.video_processor",
        "app.workers.vlm_worker",  # 新增
    ],
)
```

**最终任务处理架构图**：

```
┌─────────────────────────────────────────────────────────────────────────┐
│  FastAPI 进程                                                           │
│  ┌─────────────────────┐                                               │
│  │ POST /vlm/analyze   │                                               │
│  └──────────┬──────────┘                                               │
│             │ vlm_analyze_task.delay()                                 │
│             ▼                                                           │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     Redis (Celery Broker)                        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                    │
│                                    ▼                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     Celery Worker 进程                           │   │
│  │  ┌─────────────────┐    ┌─────────────────┐                     │   │
│  │  │ video_processor │    │ vlm_worker      │                     │   │
│  │  │ (视频切片)       │    │ (VLM 分析)      │                     │   │
│  │  │ sync DB         │    │ sync DB         │                     │   │
│  │  └─────────────────┘    └────────┬────────┘                     │   │
│  │                                  ▼                               │   │
│  │                         ┌─────────────────┐                     │   │
│  │                         │ VLMAnalyzer     │                     │   │
│  │                         │ (同步 OpenAI)   │                     │   │
│  │                         │ ThreadPoolExec  │                     │   │
│  │                         └─────────────────┘                     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## 改动文件清单

| 文件 | 改动内容 | 改动原因 |
|------|----------|----------|
| `logger.py` | `asyncio.Queue` → `redis.lpush()`，新增 `push_audit_log()` | 支持跨进程日志收集 |
| `audit.py` | 新增 `@audit_log_sync` 同步装饰器 | 支持装饰 Celery task |
| `log_worker.py` | `asyncio.Queue.get()` → `redis.brpop()` | 从 Redis 消费日志 |
| `video_processor.py` | 使用同步数据库操作，导入外键依赖模型 | 解决协程未 await 和外键解析问题 |
| `vlm_worker.py` | **新建** VLM Celery task | 将 VLM 分析迁移到 Celery |
| `celery_app.py` | 注册 `vlm_worker` | 让 Celery 发现新 task |
| `vlm.py` | `BackgroundTasks` → Celery task 调用 | 解决事件循环冲突 |

## 核心洞察

1. **async/sync 边界必须清晰**：FastAPI API 层用 async，Celery Worker 用 sync，不要混用。混用会导致协程未 await、事件循环冲突等问题。

2. **asyncio.Queue 是进程内队列**：它需要运行中的事件循环，无法在 Celery prefork worker 中使用。跨进程通信必须使用 Redis 等外部存储。

3. **SQLAlchemy 外键解析需要完整模型**：ORM 在 flush 时需要解析所有外键关系。Celery Worker 需要显式导入所有外键依赖的模型，即使代码中不直接使用。

4. **BackgroundTasks 不适合长任务**：设计初衷是轻量级操作（发邮件、写日志）。长时间运行、需要进度追踪、可能需要重试的任务应使用 Celery。

5. **装饰器的 async/sync 属性决定了它能装饰什么函数**：`async def wrapper` 返回协程，无法装饰同步函数。需要为不同场景提供不同版本的装饰器。

6. **事件循环绑定问题**：`AsyncSessionLocal` 创建的连接绑定到创建时的事件循环。在新事件循环中使用这些连接会抛出 `got Future attached to a different loop`。

## 参考

- [SQLAlchemy 2.0 Async Session](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Celery Best Practices](https://docs.celeryq.dev/en/stable/userguide/tasks.html)
- [structlog Processors](https://www.structlog.org/en/stable/processors.html)
- 内部文档：`2025-12-22-async-python-log-persistence.md`
