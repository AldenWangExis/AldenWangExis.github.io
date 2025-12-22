---
title: 异步 Python 日志持久化：Structlog Processor 与 Service 层方案的工程权衡
description: 基于 SQLAlchemy AsyncSession 与 structlog 的日志写入方案对比，涵盖存储引擎选型、连接池管理、asyncio.Queue 缓冲机制、后台 Worker 实现与 Grafana Loki 集成
author: Alden
date: 2025-12-22 19:00:00 +0800
categories: [Coding Lab]
tags: [Best Practice, Architecture, Performance]
pin: false
mermaid: true
comments: true
---

在异步 Python 后端架构中，日志持久化（尤其是写入 MySQL）是一个权衡**系统解耦**与**事务一致性**的过程。本文基于 Python 3.10+、Pydantic 2.x、structlog、SQLAlchemy 和 MySQL 8.x 技术栈，从架构设计、性能影响、实现难度和可维护性四个维度对比两种主流方案。

## 两种方案概述

**方案 A：Structlog Processor 自动化处理器**

自定义一个 structlog 处理器，截获日志字典，利用 `asyncio.create_task` 或后台队列将数据通过 `AsyncSession` 写入数据库。

**方案 B：Service 层显式调用 `create_log()`**

在业务逻辑中手动注入 `LogService`，显式调用保存方法。

---

## 方案 A：Structlog Processor

### 优点

1. **极度解耦**：业务代码完全不需要感知"持久化日志"的存在。只需调用 `log.info("user_login", user_id=1)`，剩下的交给 Pipeline。
2. **强制一致性**：可以确保所有符合特定级别的日志都被记录，不会因为开发者忘记调用 `create_log()` 而遗漏。
3. **标准化**：日志格式（Pydantic Model）在处理器内部统一转化，维护成本低。

### 缺点与挑战

1. **生命周期管理陷阱**：`structlog` 的处理器通常是同步调用的。在处理器中执行异步数据库写入需要精细处理 `event_loop`。如果在处理器中 `await`，会阻塞日志流水线，甚至导致死锁。
2. **连接池压力**：高并发下，每一条 log 产生一个插入任务，容易瞬间耗尽 SQLAlchemy 的 `AsyncSession` 连接池。
3. **上下文丢失**：在异步任务中，如果不手动传递，可能会丢失 `Trace ID` 或 `Request ID`。

---

## 方案 B：Service 层显式调用

### 优点

1. **显式即清晰**：遵循 Python 之禅 "Explicit is better than implicit"。开发者能清楚看到哪些关键操作触发了审计日志。
2. **事务控制精准**：
   - 如果希望"业务成功才记录日志"，可以将其放入同一个 DB 事务。
   - 如果希望"无论业务成功与否都要记录"，可以手动开启一个 `begin_nested()` 或独立的 `AsyncSession`。
3. **类型安全**：`create_log()` 可以利用 Pydantic 定义严格的入参，避免 Processor 方案中 `event_dict` 字段缺失导致的运行时报错。

### 缺点

1. **代码侵入性强**：业务逻辑中充斥着大量的日志调用代码。
2. **容易遗漏**：新开发者可能会忘记在新的 Service 中调用该方法。
3. **性能同步**：如果不小心写成同步等待，会增加 API 的响应延迟。

---

## 深度对比

| 维度 | 方案 A (Structlog Processor) | 方案 B (Service 显式调用) |
| :--- | :--- | :--- |
| **关注点分离** | 极佳 (AOP 思想) | 一般 (业务与审计混合) |
| **性能影响** | 较小 (后台异步执行) | 中等 (取决于是否 await 写入) |
| **实现难度** | 较高 (涉及异步任务与 Session 生命周期) | 较低 (标准的 CRUD) |
| **数据可靠性** | 较低 (程序崩溃时内存队列中的日志易丢失) | 较高 (与业务逻辑强绑定) |
| **适用场景** | 全量日志、技术监控、全链路追踪 | 审计日志、财务变动日志、关键业务凭据 |

---

## 连接池压力差异分析

从技术本质上看，两种方案都要占用数据库连接，但**触发频率**和**生命周期控制**存在显著差异。

### 触发频率

- **方案 B (Service 层)**：显式调用，通常只有"关键业务"才记入数据库（如：支付成功、权限变更）。一个请求可能只触发 1-2 次 `create_log()`。
- **方案 A (Processor)**：拦截式。如果配置不当，项目中所有的 `logger.info()`、`logger.error()` 甚至第三方库输出的日志都会触发 Processor。一个复杂的请求可能产生几十条日志，方案 A 产生的数据库写入请求可能是方案 B 的 10 倍甚至 100 倍。

### 并发失控（Fire-and-Forget 风险）

- **方案 B**：通常在 `AsyncSession` 的生命周期内执行，受 Web 框架的工作协程数量限制。
- **方案 A**：开发者为了不影响主业务响应速度，常在 Processor 里写 `asyncio.create_task(save_to_db(log))`。这是一个"发射后不管"的操作。高并发下，每一条日志都瞬间开启一个新任务去抢连接池，任务会迅速堆积，连接池瞬间溢出。

### 连接池的复用能力

- **方案 B**：可以复用当前 Request 已经开启的 `AsyncSession`。如果业务本来就要操作 DB，日志只是多执行一条 SQL，不增加额外连接负担。
- **方案 A**：Processor 运行在日志系统的上下文中，它拿不到当前 Request 的 Session 对象（除非通过 ContextVars 强行传递）。通常它需要从 `sessionmaker` 重新申请一个独立的连接。

---

## "显式"与"拦截"的本质区别

对比这两行代码在开发者眼中的语义：

```python
# 方案 B (Service)
await log_service.create_audit_log(user_id=1, action="delete")

# 方案 A (Structlog)
logger.info("user_delete", user_id=1)
```

**意图的显式 vs. 行为的隐式**：

- 在方案 B 中，写这行代码的唯一目的就是"向数据库写一条记录"。如果这行代码报错，业务逻辑通常应该感知。
- 在方案 A 中，调用 `logger.info` 的主要意图是"输出一段文本/结构化信息"（可能去控制台，可能去文件）。"写入数据库"这个行为是隐式发生的——它是被配置在 `structlog.configure` 里的 Processor 截获并执行的。

**范围的扩散**：

- 方案 B：只有手写了 `create_log()` 的地方才会写数据库。
- 方案 A (拦截式)：一旦配置了"数据库 Processor"，项目中所有地方调用的 `logger.info` 都会经过这个处理器。比如在循环里打了个 `logger.info("processing item")` 原本是为了调试，结果 Processor 也会拦截它，尝试把它存入 MySQL。后果是可能在不知不觉中把 MySQL 的连接池瞬间打满，或者让日志表体积爆炸。

---

## asyncio.Queue 的角色

`asyncio.Queue` 是 Python 标准库 `asyncio` 内部自带的模块，专门为异步编程设计的"生产者-消费者"队列，用于在不同的协程（Task）之间安全地传递数据。

### 与 Redis 的对比

| 特性 | asyncio.Queue | Redis |
| :--- | :--- | :--- |
| **存储位置** | 当前进程内存 | 独立中间件 |
| **进程崩溃** | 数据全部丢失 | 数据保留 |
| **适用场景** | 性能缓冲、削峰填谷 | 跨进程通信、高可靠性 |

### 在日志方案中的作用

在方案 A（Structlog Processor）中，如果在处理器里直接 `await session.execute(...)`，会阻塞整个日志流水线。如果使用 `asyncio.create_task` 猛冲数据库，会瞬间压垮连接池。

标准做法是：
1. Processor 只是简单地把日志丢进 `asyncio.Queue`（生产者，极快）。
2. 后台运行一个唯一的 Worker 协程，从 Queue 里取数据写入 DB（消费者，频率受控）。

这实现了**削峰填谷**：生产者快速把日志丢进队列（只需几微秒），消费者慢慢地、按自己的节奏从队列拿数据写 MySQL。

---

## 方案选型建议

### 业务审计日志（如：修改密码、删除订单）

推荐方案 B (Service 层) 或方案 B 的变体（装饰器）。审计日志属于业务逻辑的一部分，需要保证高可靠性。

进阶优化：编写一个 `@audit_log(action="delete_order")` 的装饰器挂在 Service 方法上，既保持了显式声明，又减少了代码侵入。

### 全量行为追踪（如：接口访问记录、慢查询记录）

推荐方案 A (Structlog Processor)。这类数据量大，不应干扰业务代码。

架构实践：不要在 Processor 中直接写 MySQL。

推荐链路：`structlog` -> `Processor` -> `Asyncio Queue` -> `Worker` -> `MySQL`

或者更专业的做法：`structlog` -> `Stdout` -> `Vector/Fluentd` -> `Kafka/Elasticsearch`

---

## 存储引擎深度对比：MySQL、MongoDB 与 Elasticsearch

从底层存储架构（Storage Engine）、索引模型（Indexing Theory）和分布式系统演进（Distributed Systems Evolution）三个维度，分析为什么在处理日志（尤其是海量日志）时，Elasticsearch 是首选，MySQL 是备选，而 MongoDB 是一个平衡后的中庸选择。

### MySQL 写入海量日志的瓶颈

MySQL 是为 OLTP（联机事务处理）设计的，它最核心的任务是确保 ACID（原子性、一致性、隔离性、持久性）。但日志系统的需求是 High Write Throughput（高写入吞吐）和 Complex Full-text Search（复杂的全文检索）。

**B+树索引的"写放大"效应**：

MySQL 默认使用 B+ 树索引。每插入一条日志，如果该表有多个索引（如 `level`, `user_id`, `timestamp`），数据库就必须实时更新所有相关的 B+ 树分支。随着数据量达到千万、亿级，B+ 树变得非常高。为了维持树的平衡，会频繁触发页分裂（Page Splitting），导致大量的随机 IO，写入性能呈断崖式下跌。

**Schema 的僵化**：

日志是随业务演进的。今天记录 `user_id`，明天想多记一个 `request_id`。在 MySQL 里，`ALTER TABLE` 对大表来说是噩梦，即使有在线修改工具（如 `gh-ost`），依然非常沉重。

**全文检索的无力**：

在 1 亿条日志里搜包含 `stacktrace` 关键字且 `status=500` 的记录，MySQL 即使有 `LIKE '%...%'` 也是全表扫描。虽然 MySQL 8.0 有全文索引，但在性能和灵活性上远不如专门的搜索引擎。

### Elasticsearch 的优势

Elasticsearch 的核心是 Lucene，它的设计哲学完全不同。

**倒排索引（Inverted Index）**：

这是 ES 的灵魂。它不按行存数据，而是将所有词语拆解，记录每个词出现在哪些文档里。无论有 10 亿条还是 100 亿条日志，通过倒排索引定位关键字的时间复杂度近乎 `O(1)` 或 `O(log N)`。

**LSM-Tree 类似的写入优化**：

ES 写入时先写内存中的 `Index Buffer` 和 `Translog`（顺序写），然后定期 `refresh` 成不可变的 `Segment`。这种追加写（Append-only）模式规避了 B+ 树的随机 IO 和页分裂问题，写入吞吐量极大。

**Schema-less 与动态映射**：

`structlog` 输出的 JSON，ES 收到后会自动解析字段并建立索引。不需要预先定义表结构，非常适合瞬息万变的业务日志。

**ILM（索引生命周期管理）**：

ES 官方支持"热-温-冷"架构。3 天内的日志在高性能 SSD 上（热），7 天前的日志自动滚动到普通机械硬盘上（温），30 天前的自动删除。MySQL 做这种"滑动窗口"管理需要极其复杂的物理分区维护。

### MongoDB 的定位

MongoDB 是一个 Document Store，它的位置非常微妙。

**写入性能优于 MySQL**：

MongoDB 默认使用 WiredTiger 引擎，支持文档级锁，且写入机制对高并发非常友好。它也支持分片（Sharding），横向扩展比 MySQL 简单得多。

**灵活度高**：

和 ES 一样，它是无模式的，Pydantic Model 转成的 JSON 直接塞进去就行。

**弱点在于复杂检索**：

MongoDB 的索引虽然比 MySQL 灵活，但它本质上还是传统的正排索引 + B树（或其变种）。如果只是根据 `user_id` 查日志，Mongo 极快；但如果要做模糊搜索、语义分析、复杂聚合（比如：统计过去 1 小时 500 错误按接口分布的比例），ES 的 `Aggregations` 引擎能甩 Mongo 几条街。

### 存储引擎选型矩阵

| 维度 | MySQL 8.x | MongoDB | Elasticsearch (ELK) |
| :--- | :--- | :--- | :--- |
| **数据量级** | < 5000 万条 | 5000 万 ~ 10 亿条 | 10 亿条 ~ 无上限 |
| **查询需求** | 简单精确查询 (`where id=...`) | 复杂条件过滤，无全文检索 | 任意关键字搜寻、统计图表分析 |
| **存储成本** | 高（索引占用大） | 中 | 较高（为了性能需要较多内存） |
| **运维难度** | 极低（已有基础设施） | 中（需要维护副本集） | 高（需要调优 JVM、Shard 分片等） |

### 阶段性选型建议

**初期阶段**：如果日志只是为了"备查"（比如偶尔查查谁改了配置），且每天日志量在万级别，留在 MySQL 是理性的。不要为了引入而引入，增加运维负担。优化手段：定期把旧日志 dump 到对象存储（S3/OSS），保持数据库表轻量。

**中期阶段（业务爆发）**：当发现 `SELECT count(*) FROM logs` 开始变慢，或者想要做一套仪表盘看错误率走势时，跳过 MongoDB，直接上 Elasticsearch（或者云厂商提供的日志服务，如 AWS CloudWatch, 阿里云 SLS）。

**专业级选择**：如果追求极致的存储效能（存储成本只有 ES 的 1/10），可以关注 Grafana Loki。它不索引日志内容，只索引标签（Label），是目前云原生环境下替代 ES 处理纯日志的最火方案。

使用 `structlog` + `Pydantic` 已经是非常正确的路径，因为这保证了数据的结构化。只要数据是结构化的，未来无论从 MySQL 迁移到 MongoDB 还是 Elasticsearch，都只是换一个 Worker 的写入逻辑而已。这就是解耦的魅力。

---

## 方案 A 的避坑指南

如果决定采用方案 A（自动化写入），需注意以下技术细节：

### Session 隔离

不要使用与当前 Web 请求相同的 `AsyncSession`。日志写入必须使用 `sessionmaker` 创建新的 session，否则会干扰业务事务。

### 异常捕获

在 Processor 中必须包裹 `try...except`，绝对不能因为日志写入失败（如数据库断开）导致业务流程中断。

### 性能缓冲实现

```python
class MySQLProcessor:
    def __init__(self, session_factory):
        self.queue = asyncio.Queue(maxsize=1000)
        self.session_factory = session_factory
        asyncio.create_task(self._worker())

    async def _worker(self):
        while True:
            log_data = await self.queue.get()
            async with self.session_factory() as session:
                # 批量写入逻辑...
                pass

    def __call__(self, logger, method_name, event_dict):
        try:
            self.queue.put_nowait(event_dict)
        except asyncio.QueueFull:
            pass
        return event_dict
```

### 必须限流

只处理 `level == "AUDIT"` 或 `level >= ERROR` 的日志，过滤掉普通的 `INFO`。

### 必须异步批处理

不要一条日志开一个连接。使用 `asyncio.Queue` 收集日志，后台 Worker 每隔 1 秒或凑齐 50 条日志，用一个连接执行一次批量插入。

```python
def mysql_log_processor(logger, method_name, event_dict):
    # 只有显式带有 to_db=True 标记的日志才写数据库
    if event_dict.pop("to_db", False):
        log_queue.put_nowait(event_dict)
    return event_dict

# 调用时：
logger.info("important_event", user_id=1, to_db=True)  # 显式触发拦截
logger.debug("temp_debug")  # 不会进数据库
```

---

## 进阶方案：Processor + 标记装饰器

将方案 A（Processor）与装饰器结合，把"标记进入数据库的动作"（显式）与"真正的数据库写入逻辑"（解耦）完美结合。

### 核心思路

1. **定义 Pydantic Model**：规定入库日志的严格格式。
2. **定义装饰器**：它的作用不是写数据库，而是调用 `logger.info()` 并打上一个特殊标记（如 `persist_db=True`）。
3. **定义 Structlog Processor**：它在拦截到 `persist_db=True` 的日志时，将其放入 `asyncio.Queue`。
4. **定义后台 Worker**：从 Queue 中批量读取并写入 MySQL。

### 数据模型与队列

```python
from pydantic import BaseModel
import asyncio

class AuditLogSchema(BaseModel):
    user_id: int
    action: str
    status: str
    extra_info: dict | None = None

log_queue = asyncio.Queue()
```

### 装饰器实现

```python
import functools
import structlog

logger = structlog.get_logger()

def audit_log(action: str):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            user_id = getattr(args[0], "user_id", 0)

            try:
                result = await func(*args, **kwargs)
                await logger.ainfo("audit_event",
                                 audit_data=AuditLogSchema(
                                     user_id=user_id,
                                     action=action,
                                     status="success"
                                 ).model_dump(),
                                 persist_db=True)
                return result
            except Exception as e:
                await logger.aerror("audit_event",
                                  audit_data=AuditLogSchema(
                                      user_id=user_id,
                                      action=action,
                                      status=f"failed: {str(e)}"
                                  ).model_dump(),
                                  persist_db=True)
                raise e
        return wrapper
    return decorator
```

### Processor 实现

```python
def db_persistence_processor(logger, method_name, event_dict):
    persist_db = event_dict.pop("persist_db", False)
    if persist_db:
        audit_data = event_dict.get("audit_data")
        try:
            log_queue.put_nowait(audit_data)
        except asyncio.QueueFull:
            pass
    return event_dict
```

### 批量写入 Worker

```python
async def log_writer_worker(session_factory):
    while True:
        logs = []
        log = await log_queue.get()
        logs.append(log)

        while len(logs) < 50 and not log_queue.empty():
            logs.append(log_queue.get_nowait())

        async with session_factory() as session:
            # session.execute(insert(LogModel), logs)
            await session.commit()

        for _ in range(len(logs)):
            log_queue.task_done()
```

### 组合方案的优势

1. **业务层极简**：只需要在 Service 方法上加一行 `@audit_log("删除用户")`。业务代码完全不需要知道 `AsyncSession` 或 `Queue` 的存在。
2. **精准控制**：虽然 Processor 是全局的，但只有被装饰器标记（或手动传参 `persist_db=True`）的日志才会进数据库。
3. **连接池友好**：通过 `log_writer_worker` 和 `asyncio.Queue`，把原本分散的、高并发的写入请求，变成了可控的、批量的顺序写入。
4. **高性能**：`log_queue.put_nowait` 是微秒级的内存操作。用户的 API 请求完全不需要等待数据库写入完成即可返回。

---

## Worker 的定义与扩展

在异步 Python (FastAPI/SQLAlchemy) 环境下，Worker 的本质是一个在后台永不停止运行的协程 (Coroutine)，独立于处理 HTTP 请求的协程，专门负责从内存队列中取数据并执行耗时操作。

### Worker 的本质

在当前技术栈中，Worker 并不是一个独立的进程（不像 Celery），它通常是 Event Loop 中的一个 Task。

- **生产者**：Web 接口协程（把日志塞进 `Queue`）
- **消费者 (Worker)**：后台协程（从 `Queue` 拿日志写 DB）

### 显式定义 Worker

在 FastAPI 等现代框架中，最标准的做法是利用 Lifespan (生命周期管理) 来启动和关闭 Worker。

```python
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

log_queue = asyncio.Queue(maxsize=1000)

async def log_writer_worker(session_factory: async_sessionmaker):
    """后台守护协程：不断消耗队列中的日志"""
    print("Log Worker 启动...")
    try:
        while True:
            log_item = await log_queue.get()

            try:
                async with session_factory() as session:
                    # new_log = LogModel(**log_item)
                    # session.add(new_log)
                    # await session.commit()
                    await asyncio.sleep(0.1)  # 模拟 IO 操作
                    print(f"Worker 已写入一条日志: {log_item}")
            except Exception as e:
                print(f"Worker 写入数据库失败: {e}")
            finally:
                log_queue.task_done()

    except asyncio.CancelledError:
        print("Worker 收到停止信号，正在清理...")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # session_factory = async_sessionmaker(bind=engine)
    worker_task = asyncio.create_task(log_writer_worker(None))

    yield

    worker_task.cancel()
    await asyncio.gather(worker_task, return_exceptions=True)
    print("Worker 已彻底关闭")

app = FastAPI(lifespan=lifespan)
```

### Worker 扩展策略

#### 增加并行度（同进程内多 Worker）

如果发现一条一条写 MySQL 还是太慢，队列积压了，可以在 `lifespan` 中启动多个 Task 副本。

```python
worker_tasks = [
    asyncio.create_task(log_writer_worker(session_factory))
    for _ in range(5)
]

yield

for t in worker_tasks:
    t.cancel()
```

#### 增加批量处理

不要来一个写一个，而是攒够 100 个或者每隔 1 秒执行一次批量插入（SQLAlchemy 的 multiline insert），这能减少 90% 的数据库网络开销。

```python
async def batch_log_worker(session_factory):
    while True:
        batch = []
        item = await log_queue.get()
        batch.append(item)

        while len(batch) < 50 and not log_queue.empty():
            batch.append(log_queue.get_nowait())
            log_queue.task_done()

        async with session_factory() as session:
            # await session.execute(insert(LogModel), batch)
            # await session.commit()
            pass

        log_queue.task_done()
```

#### 跨进程扩展

如果单台服务器压力实在太大，或者日志不能丢失（内存队列重启会丢），需要将 `asyncio.Queue` 替换为 Redis，并将 Worker 移动到独立的 Python 进程中。

工具推荐：Taskiq (FastAPI 时代的异步任务队列) 或 SAQ (基于 Redis 的轻量异步任务队列)。它们支持 `asyncio`，能无缝对接 `AsyncSession`。

### Worker 扩展总结

| 负载级别 | 策略 |
| :--- | :--- |
| 低负载 | 单 Worker，逐条写 |
| 中负载 | 单 Worker，批量写 (Batching) |
| 高负载 | 多 Worker 并行 + 批量写 |
| 极高负载/金融级可靠 | 引入 Redis，Worker 独立进程运行 |

---

## 总结

| 方案 | 形式 | 耦合度 | 性能 | 适用场景 |
| :--- | :--- | :--- | :--- | :--- |
| **方案 B (简单版)** | `await create_log()` | 强耦合 | 一般 | 小规模系统，对日志实时性要求极高 |
| **方案 A + 装饰器** | `@audit_log(...)` | 极低 | 极佳 | 中大型系统，追求高性能和代码整洁 |

对于大多数基于 MySQL 的系统，方案 B (显式调用) 是更稳健的选择。因为 MySQL 并不是日志存储的最佳引擎，既然选择写进 MySQL，说明这些日志具有很高的业务价值（审计属性），显式的 Service 调用能提供更好的事务一致性和代码可读性。

如果项目追求高质量架构，**方案 A + 标记位装饰器 + 后台 Queue Worker** 是最佳实践。它利用了装饰器的显式声明，同时发挥了 Processor 的异步解耦能力。

- 业务审计（Audit Log）：选方案 B（通过 Service 写入）
- 全量行为追踪（Event Tracking）：选方案 A（但不要直接写 MySQL，建议写到 Stdout 让 Vector/Filebeat 搬运到日志中心）

---

## 进阶架构：引入 Grafana Loki

与 ELK 相比，Loki 被称为"像 Prometheus 一样的日志系统"。它的核心哲学是：不索引日志内容，只索引标签（Labels）。这使得它极其轻量、存储成本极低，且与 Grafana 完美集成。

在 Python (structlog + uv) 环境中接入 Loki，有三种主流方案。

### 方案一：直接推送（Direct Push）

使用 Loki 的 HTTP API，由 Python 异步任务直接发送日志。

工具：`python-logging-loki` 或自定义异步 Client。

原理：在 Worker 逻辑中，除了写 MySQL，多加一个步骤把日志推送到 Loki。

```python
# 使用 uv add python-logging-loki 后
import logging
import logging_loki

handler = logging_loki.LokiHandler(
    url="http://loki-server:3100/loki/api/v1/push",
    tags={"application": "my-api", "env": "prod"},  # 这些是 Labels（索引）
    version="1",
)

# 在 structlog 配置中使用这个 handler
```

- **优点**：不需要安装额外的采集器（Agent）。
- **缺点**：如果 Loki 挂了，可能会丢日志或影响业务（虽然有异步队列缓冲）。

### 方案二：标准容器化采集（Stdout + Promtail）

这是云原生（Docker/K8s）下的标准做法。

1. **Python 部分**：通过 `structlog` 把日志以 JSON 格式打印到 `stdout`（标准输出）。
2. **采集部分**：部署一个 Promtail（Loki 的官方采集器）容器。
3. **链路**：`Python -> Stdout -> Docker Logs -> Promtail -> Loki`。

**为什么推荐这个？**

- **解耦**：Python 程序不需要知道 Loki 的地址，只需要管打印。
- **性能**：打印到 Stdout 是极快的，IO 压力交给了专门的 Promtail。
- **自动元数据**：Promtail 会自动给日志加上 Docker 容器名、镜像 ID 等标签。

### 方案三：双写模式（MySQL 审计 + Loki 追踪）

由于已经建立了 MySQL 日志表，可以采用动静分离的架构：

1. **MySQL**：只存"审计日志"（如：资金变动、权限修改）。数据量小，要求绝对可靠。
2. **Loki**：存"系统运行日志"（如：请求响应、调试信息、错误堆栈）。数据量大，要求查询快。

#### 实现步骤

**步骤 1：配置 structlog 输出 JSON**

```python
import structlog

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()  # 必须是 JSON，Loki 处理 JSON 极强
    ],
    logger_factory=structlog.PrintLoggerFactory(),  # 直接打印到 stdout
)

logger = structlog.get_logger()
```

**步骤 2：启动 Loki 和 Grafana**

使用 `docker-compose` 快速部署：

```yaml
services:
  loki:
    image: grafana/loki:latest
    ports:
      - "3100:3100"

  promtail:
    image: grafana/promtail:latest
    volumes:
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
    configs:
      - source: promtail-config.yaml

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
```

**步骤 3：在 Grafana 中查看**

1. 打开 Grafana (localhost:3000)。
2. 添加 Datasource，选择 Loki，地址填 `http://loki:3100`。
3. 进入 Explore 页面，输入查询语句：`{container_name="my_python_app"} | json`。

### Loki 的标签（Labels）设计

在 Loki 中，Labels 决定了查询效率。

- **好的 Labels (索引)**：`env` (prod/dev), `service` (order-api), `level` (error/info)。
- **坏的 Labels (不要索引)**：`user_id`, `request_id`, `message`。

为什么？如果把 `user_id` 放在 Label 里，Loki 会产生无数个小的索引文件（High Cardinality 问题），直接卡死。

正确做法：把 `user_id` 放在 JSON 消息体里。Loki 可以在查询时实时过滤 JSON 字段。

### Loki 集成建议

1. **继续保留 MySQL 日志表**：用于存放那些"绝对不能丢、且需要和业务数据做 Join 查询"的关键审计数据。
2. **引入 Loki 处理全量日志**：
   - 修改 `structlog` 配置，确保输出的是单行 JSON。
   - 让 Worker 只管写 MySQL 关键日志。
   - 全量日志直接通过 `print()` 输出，交给 Promtail 送往 Loki。
3. **利用 Grafana**：在一个面板里，可以同时展示 MySQL 里的订单统计图表和 Loki 里的错误日志流，这才是顶级工程师的监控面板。
