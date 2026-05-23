---
title: "当缓存冒充事实来源：Milvus Rename 的一次复盘"
description: 复盘 Milvus hybrid embedding storage 中 rename_collection_embeddings 误信进程内缓存导致 no-op、partial cache 报错与潜在数据丢失的根因、修复和预防动作。
author: Alden
date: 2026-05-23 21:08:42 +0800
categories: [LLM Engineering, RAG]
tags: [Milvus, Vector Database, RAG, State Management, Data Quality, Best Practice]
pin: false
mermaid: true
comments: true
---

> 当系统同时有真实持久化存储和进程内缓存时，缓存可以加速读路径，但不能替代写路径的事实来源；partial cache 更不能伪装成完整实体。

---

PR #382 的目标是把 embedding 存储从单一 LanceDB 路径扩展成 hybrid storage：Milvus 承担向量检索和 embedding rows，LanceDB 继续保留 knowledge base 的 control-plane 数据。这个拆分能让向量层更接近生产形态，但也引入了一个新边界：业务操作不再只面对一个本地表，而是同时面对远端持久化向量库、LanceDB 元数据，以及当前进程里的 `_records` 缓存。

这份记录复盘的就是这个边界问题：当系统同时有真实持久化存储和进程内缓存时，哪些路径可以把缓存当加速层，哪些路径必须回到真实存储。

qin 抓到的问题落在 `rename_collection_embeddings()` 上。它不是普通的 cache miss，而是更危险的 partial cache 问题：缓存里看起来有 row，但这个 row 只有 metadata，没有后续 mutation 需要的 vector。

## 摘要

PR #382 引入 Milvus hybrid embedding storage。Milvus 负责 embedding plane，LanceDB 保留 control-plane 表。为了让单元测试和热路径更方便，`MilvusEmbeddingIndexStore` 里有一个 `_records` 字典，保存当前进程见过的 embedding row。

问题出在 rename：`rename_collection_embeddings()` 把 `_records` 当成了所有 Milvus rows 的完整镜像。

这在 hot cache 路径里可以通过：

```text
same process: upsert -> rename
```

因为 upsert 刚刚把完整 row 放进 `_records`，里面有 `vector`、`metadata`、`collection` 等字段。

真实服务不会一直处在这个状态。服务会重启，进程会丢缓存；也可能先执行 count/list 类操作，从 Milvus 查回只有 metadata 的 row，再把这个 partial row 回填到 `_records`。一旦 rename 后续相信了这个 partial cache，就会出现 no-op、异常，甚至删除旧 rows 后无法重建新 rows 的风险。

最终定位如下：

| 项目 | 结论 |
| --- | --- |
| 直接问题 | `rename_collection_embeddings()` 依赖进程内 `_records`，没有从 Milvus 查询真实 rows。 |
| 触发路径 1 | cache empty 后 rename，找不到 rows，rename 变成 no-op。 |
| 触发路径 2 | count/list 回填 metadata-only cache 后 rename，upsert 因缺少 vector 报错。 |
| 更坏风险 | 旧实现先 delete old ids 再 upsert new rows，partial-cache 路径可能先删旧 rows，再因为缺 vector 写新失败。 |
| 根因提交 | `409fc27 feat(kb): add Milvus hybrid embedding storage` 引入 rename 依赖 `_records` 的模型。 |
| 放大提交 | `60cee01 fix(milvus): harden embedding operations against cache loss` 修了多条 cache-loss 路径，但漏掉 rename，并引入 metadata-only cache refresh。 |
| 修复提交 | `4e66730 fix(milvus): make collection rename cache independent`。 |
| 回归测试 | 覆盖 empty cache rename 和 metadata-only cache refresh 后 rename。 |

## 影响面

影响范围集中在 Milvus hybrid backend 的 collection rename。

| 场景 | 旧行为 | 用户可见结果 | 风险 |
| --- | --- | --- | --- |
| `upsert -> rename`，同一进程热缓存 | 能成功 | 新 collection 有 embedding，旧 collection 被迁移 | 低 |
| `upsert -> clear _records -> rename` | rename 找不到 rows | 旧 collection 仍有 embedding，新 collection 没有 embedding | 中 |
| `upsert -> clear _records -> count -> rename` | count 回填 metadata-only row，rename 重用 partial row | rename 报 `Embedding records must include non-empty vector values` | 高 |
| metadata-only cache 后 rename，且旧实现已执行 delete | 旧 ids 先被删除，new rows 因缺 vector 写入失败 | 旧 embedding 可能丢失，新 collection 仍没有 embedding | 高 |

这个问题不影响默认 LanceDB-only 路径，也不影响 Milvus search/count/delete 已经切到 backend query 的路径。它影响的是 collection rename 这个低频但高风险管理操作。

低频不等于低风险。rename 会批量改变持久化 row 的 identity label；这里 stable id 还包含 collection，所以 rename 不是简单改 display name，而是一次 identity 迁移。

## 触发序列

qin 的 review comment 给出的关键序列是：

```text
upsert
clear _records
count_embeddings_by_collection
rename_collection_embeddings
```

这条序列说明 bug 不只发生在“缓存为空”的瞬间，也发生在“缓存被重新填充，但填进去的是不完整数据”的状态。

空缓存容易想到，partial cache 更容易骗人。它看起来有数据，但不是 mutation 所需要的完整实体。

## 事实链

### 1. rename 和相邻方法的数据来源不一致

修复前，count、delete、iter 这类操作已经回到 Milvus：

```text
list tables -> query rows from Milvus -> apply access/filter -> operate
```

rename 仍然停留在旧姿态：

```text
iterate self._records -> change collection -> re-upsert
```

这些方法都在做 embedding management，都面对同一个事实：Milvus 里的 row 才是事实来源。既然 count/delete 已经不信 `_records`，rename 继续信 `_records` 就是同类行为里的异类。

### 2. `_query_rows_for_table()` 会制造 metadata-only cache

`_query_rows_for_table()` 查询 Milvus 时默认只要 `id` 和 `metadata`。这对 count/delete 合理：

- count 只需要知道 row 属于哪个 collection/user。
- delete 只需要知道 ids。
- iter 的部分场景只需要 metadata 字段。

问题是，它还会把查回来的 row 写回 `_records`。

因此 `_records` 里会出现两种 row shape：

| 来源 | shape | 是否能用于 rename re-upsert |
| --- | --- | --- |
| upsert 写入 | full row，含 `vector` | 可以 |
| backend query 回填 | metadata-only row，不含 `vector` | 不可以 |

这对只读路径无所谓，但对 rename 是致命的。rename 会把 row 改名后交给 `upsert_embeddings()`，而 upsert 明确要求非空 vector。

### 3. 最小复现证明 reviewer 的路径成立

最小复现结果：

```text
case1_rename_result= {}
case1_old_count= 1
case1_new_count= 0
case2_exception= ValueError Embedding records must include non-empty vector values.
```

这几个事实把问题钉住了：

- cache empty 时，rename 什么都没改。
- 旧 collection 仍然存在，新 collection 没有数据。
- 先让 count 回填 metadata-only cache 后，rename 会因为缺 vector 报错。

这已经不是“代码看起来有风险”，而是 reviewer 的复现路径成立。

### 4. 旧写入顺序扩大了风险

`60cee01` 时期的 rename 逻辑是：

```text
collect matching rows from _records
delete old ids
upsert rows with new collection
```

在 metadata-only cache 场景里，`old_ids` 来自 Milvus query 回填，是真实存在的旧 ids；但 `matching_rows` 缺少 vector。这样执行顺序会变成：

```text
delete old ids succeeds
upsert new rows fails because vector is missing
```

所以这个问题不只是 rename 失败。失败点如果发生在 delete 之后，会留下更坏的结果：旧 rows 已删，新 rows 没写成功。

## 根因分层

### 直接原因

`rename_collection_embeddings()` 从 `_records` 枚举待迁移 rows，并假设这些 rows 是完整 embedding rows。

这个假设不成立。`_records` 只是当前进程见过的 best-effort cache，不是 Milvus 的完整镜像，也不保证 row shape 完整。

### 设计原因

`_records` 同时承担了两种角色：

- full-row cache：upsert 后保存完整 row，包含 vector。
- metadata cache：backend query 后保存 metadata-only row。

这两个角色共用同一个 dict，但没有类型、命名或访问边界来区分。结果是一个方法写入 partial shape，另一个方法按 full shape 读取。

### 测试缺口

原有测试主要覆盖 hot cache 路径：

```text
upsert -> immediate operation
```

`60cee01` 后已有一批 cache-loss 测试，证明 search/count/delete/iter 在 cache empty 时能工作，但缺少状态转换测试：

```text
cache empty -> backend query -> metadata-only cache -> mutation
```

rename 正好漏在这层。

### 流程原因

当时修复更像是按 review comment 和失败路径逐项处理：search、count、delete、batch upsert。每一项局部看都修了，但没有把问题抽象成 storage invariant 后重新扫所有 mutation。

更高层的不变量应该是：

> 所有修改 Milvus 持久化 rows 的方法，都不能依赖进程内 cache 作为事实来源。

用这个不变量重新扫一遍，rename 会自然浮出来。

## 时间线

### `409fc27`：初始实现把 cache 当 working set

`409fc27 feat(kb): add Milvus hybrid embedding storage` 是 Milvus hybrid storage 的初始提交。这个提交里，`_records` 承担了很多责任：它既是缓存，又像一个工作集。

当时 rename 的模型是：

```text
从 _records 找 old collection rows
把 collection 改成 new
删旧 ids
重新 upsert
```

如果只看单进程单测，这个设计显得简洁。fake store 在内存里，`_records` 也在内存里；刚 upsert 后马上 rename，数据当然完整。

问题是，代码把“当前进程刚见过的 rows”当成了“Milvus 中所有 rows”。这是两个概念。

### `60cee01`：修掉多条 cache-loss 路径，但漏掉 rename

`60cee01 fix(milvus): harden embedding operations against cache loss` 的方向是对的。它已经意识到 `_records` 不可靠，于是把很多路径挪到了 Milvus backend query：

- search 能在 cache empty 时工作。
- count 能在 cache empty 时工作。
- delete 能在 cache empty 时工作。
- iter batches 能在 cache empty 时工作。
- supported filters 开始 pushdown 到 vector store。
- upsert delete/add 做了 batch。

但这次覆盖面更像按已知失败路径修，不是按 mutation invariant 扫描。rename 被漏掉了。

更微妙的是，`60cee01` 新增的 backend query helper 只查 metadata，并把结果回填 `_records`。这让 `_records` 从“可能为空”变成“可能有 partial row”。空缓存问题容易暴露，partial row 更隐蔽。

### `498a4e2` 和 `f6b2c9c`：修的是其他边界

`498a4e2 fix(storage): align hybrid Milvus adapter with vector contract` 主要让 `HybridVectorIndexStore` 显式满足 `VectorIndexStore` contract，并修 async upsert blocking。

`f6b2c9c fix(storage): unblock Python pre-commit checks for Milvus branch` 主要处理 mypy/ruff/pre-commit 相关问题。

这些提交提升了代码质量，但没有触碰 `rename_collection_embeddings()` 的事实来源问题。

### `4e66730`：rename 回到 durable source

`4e66730 fix(milvus): make collection rename cache independent` 把 rename 改成从 Milvus 查询真实 rows，并请求 `id/metadata/vector`。

新模型是：

```text
query old rows with vector
build new rows with new collection
upsert new rows, generating new stable ids
delete old ids
```

rename 不再相信 `_records`，而是回到 Milvus 查询 mutation 需要的完整事实数据。

## 修复设计和取舍

一开始容易想到轻量方案：Milvus 支持 upsert/partial update，能不能只把 metadata 里的 collection 改掉？

没有采用这个方案。原因是当前 stable id 包含 collection：

```text
collection + doc_id + chunk_id + parse_hash + model + user_id
```

如果只改 metadata，不改 id，row 的 id 仍然是 old collection 算出来的。后续同一 chunk 在 new collection 下 upsert 会生成新 id，旧 id 可能残留，幂等语义会被破坏。

所以修复选择了更重但更一致的路径：

```text
read full old rows
rewrite rows under new collection
generate new stable ids through normal upsert
delete old ids after new rows are written
```

这个顺序的取舍是：

| 失败点 | 结果 | 可接受性 |
| --- | --- | --- |
| query full rows 失败 | 旧 rows 未动 | 可接受，rename 失败但没有破坏旧数据。 |
| upsert new rows 失败 | 旧 rows 未删 | 可接受，可重试。 |
| delete old ids 失败 | 新旧 rows 可能短暂共存 | 需要后续重试或清理，但比先删旧 rows 后写新失败更安全。 |

这次修复选择优先避免数据丢失。最坏情况从“旧 rows 可能先被删掉”变成“新旧 rows 可能同时存在”。后者更容易通过重试和巡检恢复。

## 另一个顺手发现的问题

排查调用链时还发现一个 qin 没提到的边界：API 和 storage contract 已经要求 `rename_collection_data()` 接收 `user_id/is_admin`，但 `HybridVectorIndexStore` 还停留在旧签名。

这意味着即使 Milvus rename 本身修了，API rename 路径在 hybrid backend 下也可能先因为签名不匹配失败。

最终修复里补齐了这个签名，并把 tenant scope 传给 LanceDB 和 Milvus rename。

## 最终修复

最终提交：

```text
4e66730 fix(milvus): make collection rename cache independent
```

具体变更：

- `_query_rows_for_table()` 支持请求额外字段。
- `MilvusVectorStore.query_rows()` 不再丢弃 requested fields。
- rename 查询 `id/metadata/vector`，确保 re-upsert 有完整 vector。
- rename 先写新 rows，再删旧 ids。
- `HybridVectorIndexStore.rename_collection_data()` 补齐 `user_id/is_admin`。
- 新增 empty cache rename 回归测试。
- 新增 metadata-only cache refresh 后 rename 回归测试。

## 验证

本地关键验证：

```text
related storage tests: 35 passed
full pre-commit: passed
```

最关键的是两个新测试：

```text
test_rename_collection_embeddings_works_when_local_cache_is_empty
test_rename_collection_embeddings_survives_metadata_only_cache_refresh
```

它们分别覆盖两个旧实现会漏掉的状态：

- cache empty 后 rename 不能 no-op，必须从 Milvus 查询旧 rows。
- metadata-only cache refresh 后 rename 不能复用 partial row，必须重新取回 vector。

全量 pytest 也跑过，但本地不是干净信号：有本地 Milvus 不可连、PostgreSQL driver 缺失、pptx/Langfuse/workspace durable storage 等未触及区域失败。因此这次判断以相关 storage tests 和 pre-commit 为准。

如果要把验证再做硬，可以补一个反事实记录：在 `60cee01` 上运行这两个测试应失败，在 `4e66730` 上应通过。这样能证明测试不是只覆盖修复后的实现细节，而是确实能抓住旧 bug。

## 为什么当时没发现

### 1. 测试处在 hot cache 路径

原测试大多是：

```text
upsert -> immediate operation
```

这种路径下 `_records` 是热的，而且 row 是完整的。rename 自然会通过。

真实服务更像：

```text
process A upsert
process restarts
process B rename
```

或者：

```text
upsert
clear local cache
count refreshes metadata-only cache
rename
```

测试没有覆盖这些生命周期。

### 2. 修复时抓住了 empty cache，没有抓住 partial cache

`60cee01` 的 cache-loss 测试已经有价值，但主要证明“缓存空了也能读/删/迭代”。真正漏掉的是下一层：

```text
缓存空了 -> backend query -> cache 被 partial row 填上 -> 后续 mutation 误信它
```

这类 bug 很难靠 happy path 测试发现。它需要测试状态转换，而不是单个方法的输入输出。

### 3. review comment 容易变成 checklist

review 里点了 search、count、delete、batch upsert，于是修复就围绕这些函数展开。局部看每一项都完成了，但更高层的不变量没有落到所有 mutation 上。

这次漏掉 rename，本质上是没有把 review comment 提炼成 durable rule。

### 4. rename 是低频路径

rename 不像 search 那样天天被打，也不像 delete 那样天然让人警觉。它是低频管理操作。

但它改的是持久化 identity，风险不低。尤其 stable id 包含 collection，rename 的正确性必须按数据迁移看，而不是按普通字段更新看。

## Reviewer 的有效审查模式

下面是对 qin 审查路径的推测，不作为事实证据，只作为 review 方法沉淀。

他可能是沿着之前对 `_records` 的批评继续扫。看到 `_records` 后，没有只问“还有没有用”，而是把每个使用点放到语义类别里：

```text
search/count/delete/iter: 已经走 Milvus query
rename: 还在走 _records
```

然后继续看 `_query_rows_for_table()` 的数据形状，发现它只回填 metadata。再看 rename 后续会调用 `upsert_embeddings()`，而 upsert 必须有 vector。于是自然构造出复现：

```text
clear cache
count 回填 metadata-only row
rename 读 partial row
upsert 缺 vector 报错
```

这个审查方式值得保留：不要停在“这个字段不可靠”，继续追问“谁会写这个字段，写进去的数据是不是另一个 reader 期待的 shape”。

很多深层 bug 都藏在这里：A 方法写入 partial shape，B 方法按 full shape 读取。

## 后续预防动作

这次教训可以压成一句话：

> cache 可以加速读路径，但不能替代写路径的事实来源；partial cache 不能伪装成完整实体。

建议沉淀成几条工程动作：

1. 所有 storage mutation 都必须明确 durable source，不能从 process-local cache 推导待修改全集。
2. `_records` 这类缓存如果会存不同 shape，要在命名、类型或结构上区分 full row cache 和 metadata-only cache。
3. 每个 mutation 至少覆盖三类 cache lifecycle：hot cache、empty cache、partial cache。
4. review storage 变更时，不只看被点名函数，还要按 invariant 扫同类 mutation。
5. 对“先删后写”的迁移逻辑增加失败点检查，优先选择先写后删，除非有事务或补偿机制。

以后遇到类似 storage 层改动，优先画状态流：

```text
服务重启 -> cache empty
管理查询 -> metadata-only cache
mutation -> needs full row
```

真正的线上 bug 很多不发生在单个函数入口，而发生在两个函数之间互相误解数据形态的时候。
