---
title: "Milvus 3.0 与 Snowflake 的共识：数据引力正在重写检索架构"
author: Alden
date: 2026-08-04 08:08:00 +0800
categories: [LLM Engineering]
tags: [Architecture, Milvus, Vector Database, Vector Lakebase, Data Gravity, Data Lake]
description: 从数据引力出发，拆解 Milvus 3.0 的 Vector Lakebase 如何通过外部集合、Loon、快照、Spark 和引擎下推，把向量检索放回数据所在的位置。
image:
  path: https://mmbiz.qpic.cn/mmbiz_jpg/7p2YcxeRCWchFeOv9NZB7BxIoHNJzJbyVXWFJmDyaXCTcjp1xO1dE1bWbowrrgAvOmuo1bRUZHFdsmAJfscyolNffbqApy9r8JwJ2iavHxqQ/0?wx_fmt=jpeg
  alt: "Milvus 3.0 与 Snowflake 的共识：数据引力正在重写检索架构"
pin: false
math: false
mermaid: false
comments: true
---

Milvus 3.0 发布，Vector Lakebase 把向量检索的底座换了一种组织方式：湖原生数据、向量索引和检索计算服务同一份数据源。数据仍留在开放表格式和对象存储中，Milvus 则在数据所在的位置建立和服务检索。

`Data Gravity` 是 Snowflake 企业 AI 架构里的一个核心判断：数据规模、治理规则、血缘和权限一旦形成重心，系统拓扑就会向数据收拢。Milvus 3.0 把这一约束带到向量检索，处理的是 Embedding 已经在湖里后，ANN、回表、批处理和模型迭代如何不再围绕副本运转。Vector Lakebase 将答案拆到数据归属、对象存储随机读取、版本一致性和候选集计算位置四层。

![Vector Lakebase 架构概览](https://mmbiz.qpic.cn/sz_mmbiz_png/7p2YcxeRCWf5TX9prbtDYVyQ6BLLKWgpJrBKUWPCq3f5JHcuacYVFkia7mMt1HQKvXXP555aaNpSqcTCn2vkqZpkNmG1QVCYmF51QyMdJNtk/640?wx_fmt=png&from=appmsg#imgIndex=0)

| 架构问题 | Milvus 3.0 的回答 | Vector Lakebase 的含义 |
| --- | --- | --- |
| 数据归谁管理 | External Collections 直接链接湖表 | 数据源保持统一，不再以检索副本为中心 |
| 对象存储如何服务检索 | Loon 按点查路径组织数据 | 湖原生存储可以承担 ANN 后的回表 |
| 离线任务如何读到稳定数据 | Snapshot 和 Spark Connector | 训练、评估与线上检索共享版本边界 |
| 检索后的处理放在哪里 | 排序、聚合、分面与结构化多向量进入引擎 | 候选集不用反复离开数据路径 |

这四层按顺序连在一起。数据留在湖中是起点，读路径、时间边界和计算位置共同决定它能否成为生产级检索底座。

![数据引力与向量检索](https://mmbiz.qpic.cn/sz_mmbiz_png/BDbj75fnJWeIoodYAaLsroY3rF7c1XjiaarfTZNmoicEwlEFhWiaGicicjTWuACQ7FyibQDPwsa23MicliapqBeyLIcX86zluXZE4mhicKRTciaIyVtIs/640?wx_fmt=png&from=appmsg&tp=webp&wxfrom=5&wx_lazy=1#imgIndex=13)

## 数据归属：Vector Lakebase 的第一性原理

向量检索进入生产后，最难维护的常常不是索引本身，而是副本。湖表有自己的快照、保留策略、数据质量流程和权限标签，向量库又有导入批次、索引状态与删除语义。复制一份数据，就意味着要长期维护两套演化单元之间的同步协议。文档更新、权限撤回、重新生成 Embedding 或 Schema 调整时，任何一个同步细节处理不好，检索结果都会偏离权威数据。

External Collections 把 Iceberg、Lance、Parquet 等外部数据集映射为 Milvus Collection。文件不移动，Milvus 在原处建立向量索引、BM25 倒排索引、JSON 索引和标量索引；外部数据更新后，Milvus 读取存储 Manifest，只为新增分片建立索引。调用方仍通过 Milvus API 检索，数据平台仍保有数据文件的生命周期和管理权。

这里的重点在于数据拓扑。传统路径把数据湖和向量库变成两个需要持续对齐的中心，Vector Lakebase 让湖表保留权威性，向量检索成为叠加在其上的能力。开放格式也让这条路径不依赖单一存储形态，索引机制可以面对 Lance、Parquet、Iceberg、Vortex 等格式。数据引力不再被误解为“把所有东西收进一个封闭系统”，而是让计算在不夺取数据所有权的前提下靠近数据。

不过，数据归属与服务负载仍需分开判断。External Collections 面向数据源已在外部、需要长期保存，并且希望同时服务分析、训练和检索的场景。高频写入、对尾延迟极度敏感的在线业务，原生 Milvus Collection 仍更合适。

| 负载特征 | 更合适的路径 |
| --- | --- |
| 数据已经是湖表或对象存储数据集，需长期复用 | External Collections |
| 高频写入、极低尾延迟、实时在线服务 | 原生 Milvus Collection |

统一了数据归属，检索并不会自动成立。ANN 召回到候选 ID 后，系统仍要从对象存储取回向量和元数据，能否控制这段回表 I/O 才是湖原生检索的第一道考验。

## 访问路径：ANN 的对象存储回表

ANN 搜索通常分成两段：索引返回候选 ID，再按 ID 读取向量、标量字段或原文元数据。对象存储擅长低成本保存海量数据和顺序扫描，却不擅长大量细粒度随机点查。若底层格式仍按分析型扫描布局，即使只需要少量候选记录，也可能读出大量物理数据。数据没有搬动，延迟和带宽账单仍会把检索拖回不可用区间。

Loon，也就是 Storage v3，是 Milvus 3.0 为这段路径准备的存储层。它以不可变 Manifest 管理数据版本，把字段组织为由 Row ID 对齐的多个 ColumnGroup：标量字段按过滤与扫描需求布局，向量和高频点查字段采用更适合小粒度读取的布局。新增字段可以追加新的 ColumnGroup，删除或增加字段主要修改元数据，不必重写历史列；索引也不再与单一物理格式绑定。

| 检索阶段 | 常见问题 | Loon 对应的设计 |
| --- | --- | --- |
| ANN 召回候选 | 索引和数据格式绑定，格式演进牵动重建 | 索引与数据格式解耦，由 Manifest 记录版本 |
| 按 ID 回表 | 分析型文件为少量记录触发大范围读取 | 向量和点查字段采用小粒度读取布局 |
| Schema 演进 | 增删字段需要重写历史数据 | 追加或调整 ColumnGroup，历史列保持不动 |

Milvus 官方发布文章给出的内部测试口径是 300 万行、128 维向量、S3 对象存储和 256 个并发读取器：Parquet 单次点查约读取 9.4 MB，Loon 加 Vortex 约为 0.07 MB，读取量相差约 135 倍。这个数字不能外推为所有数据集的延迟承诺，但它指出了湖原生检索应当优先量化的指标：ANN 召回之后，候选集物化带来了多少读放大。只看 ANN 的 QPS 或召回率，会遗漏整条服务路径里最脆弱的一段。

数仓里的元数据剪枝和这里的 ColumnGroup 都在做同一件事，尽可能短地走完数据到计算的路径。前者减少扫描，后者控制随机读取。读路径成立之后，问题从空间转向时间，离线任务究竟在读取哪一版数据。

![对象存储读取路径](https://mmbiz.qpic.cn/sz_mmbiz_png/BDbj75fnJWfNNuPRUnD6v6Hr082wa8bf8MTFSS8eIWbGeAsf0bUekPBnqAQkP2TFJTgPQjic1XHibcvuxqHalt3lYnxG3oiaXQLjSfNiboib4Ob8/640?wx_fmt=png&from=appmsg&tp=webp&wxfrom=5&wx_lazy=1#imgIndex=2)

## 版本边界：反馈闭环的共同输入

Embedding 模型会换，切分策略会改，标签和权限会变，线上召回还会不断积累反馈。离线去重、聚类、评估或回填若直接读取一个持续写入的 Collection，输入可能横跨多个数据时刻。结果即使能够产出，也难以解释和复现，更无法稳妥地回流到线上检索。

Milvus Snapshot 提供了这一层版本边界。它是某个时间点的只读视图，记录已有数据、索引和元数据文件的引用，不物理复制整份 Collection。模型切换、重新生成 Embedding、Schema 修改、回填校验和隔离测试都可以从同一个快照开始；恢复时也可以复用对象存储中的已有文件。Snapshot 不等于备份，快照与生产任务仍可能共享对象存储、网络带宽和底层文件，长期灾备依然需要独立的物理副本。

稳定的输入让 Spark Connector 有了完整的职责。Spark DataSource V2 让 Spark、Databricks 和 EMR 可以读写 Milvus，离线任务由 Snapshot 提供一致输入，完成去重、异常检测、聚类或评估后再写回检索系统。线上 Collection 继续服务请求，离线计算不必反复导出整库。检索反馈由此有机会成为稳定的优化信号，而不只是散落在应用日志中的行为数据。

在线 Schema 变更和 Backfill 把这条路径延伸到模型迭代。增加或删除字段主要修改 Collection Manifest；内置回填可以根据文本列生成 BM25 稀疏向量；规划中的外部回填则沿着 Snapshot、Spark 计算、写回 Milvus、增量更新索引的顺序运行。模型升级不再必然要求新建一条全量旁路和一次切流，评估和回填策略成为更需要认真治理的对象。

共享了数据版本，在线与离线负载才有可能形成闭环。候选集若仍在每次查询后被送到应用层排序、过滤和拼装，系统会在最后一步重新制造副本和语义分叉。

## 执行位置：候选集内的引擎计算

许多 RAG 系统把 ANN 当作终点：取回较大的候选集，交给应用层完成排序、过滤、聚合、分面统计与权限后处理，再截断给模型或用户。候选越多，网络传输、序列化、服务内存和重复业务逻辑越多；不同服务对同一份候选采用不同的语义，也会让结果变得难以统一。

Milvus 3.0 将一部分后处理留在引擎内。Query 路径中，各 Segment 先局部排序，再由 Query Node 合并有序流；Search 路径中，ORDER BY 只在 ANN 已召回的候选上按标量字段二次排序。聚合和分面搜索也有同样的语义边界：Search 侧统计的是候选集的分布，适合品牌、价格带、租户或文档类型等结果集展示；需要全量精确统计时，应走 Query 侧聚合。

| 能力 | 数据停留的位置 | 需要保留的边界 |
| --- | --- | --- |
| ORDER BY | Milvus 内部的 ANN 候选集 | 不扩大 ANN 召回范围 |
| 分面与 Search 聚合 | 已召回候选集 | 统计结果不是全量精确值 |
| Query 聚合 | 满足过滤条件的完整查询结果 | 适合全量精确统计 |

StructArray 处理的是更隐蔽的数据离心。长文档分块、视频帧、多角度商品图，以及 ColBERT、ColPali 生成的多 Token 或多 Patch 向量，常被拆成孤立记录。这样便于索引，却让实体 ID、权限和标签在每个片段重复，应用还要在召回后把片段拼回完整文档或商品。StructArray 允许一行保存变长的结构化数组和多个向量，让实体重新成为存储与搜索的基本单位，减少跨层重组时的元数据漂移。

稀疏检索也被纳入同一条执行路径。新版稀疏索引通过压缩 Posting List、SIMD 解码和量化，将索引体积降至 Milvus 2.6 的约三分之一；SINDI 面向 SPLADE 一类高密度学习型稀疏向量，以紧凑窗口和 SIMD 友好的得分累加处理倒排列表，并支持 BM25。稠密向量负责语义召回，稀疏检索保留实体和关键词的精确匹配，排序和聚合留在引擎内执行，混合检索不必退化成应用层拼接两个 API 结果。

数据、索引和计算已经被放到一条更短的路径上，最后仍有一个不能由系统替代的前提：这些对象携带的语义和治理信息必须正确。

## 语义控制：数据引力的完整性

数据引力不会自动带来正确性。企业数据从存储走向检索和推理时，Schema、血缘、权限与业务定义必须随路径一起被保留，否则更短的链路只会更快地放大错误。错误字段定义、污染文本、过期权限标签和不完整血缘，任何一个都足以让看似高召回的系统失去业务上的语义保真度。

Milvus 3.0 的价值，在于减少语义在系统边界间分叉的机会。External Collections 保留原始数据集的归属，Manifest 和 Snapshot 明确版本边界，StructArray 将实体与元数据重新绑定，服务端过滤、排序和聚合减少应用层各自解释候选集的空间。这些能力不替代数据治理，却让治理规则更容易沿着数据、索引与检索结果一起传播。

Vector Lakebase 的辨识度也在这里。它把湖原生存储、高性能向量检索和向量数据的离线演进放到同一份数据源上考虑，目标并不是给数据湖增加一个查询入口，而是缩短数据、索引、计算与反馈之间的拓扑距离。评估 RAG 或 Agent 的数据底座时，问题不该从“选哪个向量数据库”开始。先确认数据在哪里、谁拥有它的生命周期、在线与离线负载如何共享版本，以及哪些计算必须留在数据路径内。答案未必总是湖原生，也未必总是原生 Collection；但当数据规模、治理和反馈闭环进入系统主路径，围绕副本堆叠服务的架构会越来越难维护。Milvus 3.0 提供了一种值得认真评估的向量检索底座形态。

![数据引力正在重写检索架构](https://mmbiz.qpic.cn/sz_mmbiz_png/7p2YcxeRCWenHPu9aHOR6mcls5CicfezD1koQa065Lo7tuTPcODNx2yKvebzrKlvUnofgsYAViafGm3zxiblqjMZVOzGicFZDY4p0DNmWpwsyQM/640?from=appmsg#imgIndex=3)

## 参考

- [Snowflake 的架构革命：数据引力时代的企业级 AI 重构](/posts/snowflake-architecture-revolution/)
- [官宣开源｜Milvus 3.0 正式发布](https://mp.weixin.qq.com/s/MQvZRsT6vq1MfToEKIt6ag)
