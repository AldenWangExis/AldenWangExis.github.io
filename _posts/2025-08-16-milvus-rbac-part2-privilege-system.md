---
title: Milvus 权限管理实战（二）：RBAC 核心机制与权限授予
description: 深入介绍 Milvus RBAC 四要素模型、56 种细粒度权限、9 个内置权限组及 grant_privilege_v2() API 使用
author: Alden
date: 2025-08-16 10:00:00 +0800
categories: [LLM Engineering, Milvus]
tags: [Milvus, RBAC, Vector Database, Python, Privilege]
pin: false
mermaid: false
comments: true
---

> 面向对象：已部署 Milvus Standalone (Docker Compose)、具备传统 RDBMS RBAC 经验的 Python 开发者
>
> 基于 Milvus 2.6+ / PyMilvus

## 2.1 权限模型四要素

Milvus RBAC 模型由四个核心要素构成[^1]：

```
┌─────────────────────────────────────────────────────────┐
│                        User                             │
│                          │                              │
│                          ▼                              │
│                        Role                             │
│                       ╱    ╲                            │
│                      ▼      ▼                           │
│              Privilege    Resource                      │
│                  │                                      │
│                  ▼                                      │
│           Privilege Group                               │
└─────────────────────────────────────────────────────────┘
```
{: .nolineno }

### Resource（资源）

资源是权限控制的目标对象。Milvus 定义了三个资源级别：

| 级别 | 说明 | 示例 |
|------|------|------|
| Instance | 整个 Milvus 实例 | 集群级别操作 |
| Database | 特定数据库 | `db_name="default"` |
| Collection | 特定集合 | `collection_name="my_collection"` |


### Privilege（权限）

权限定义了对资源可执行的具体操作。Milvus 2.5+ 提供了 56 种细粒度权限，按功能分为以下类别：

#### Database 权限（5 种）

| 权限 | 说明 | 对应 API |
|------|------|----------|
| ListDatabases | 查看实例中所有数据库 | `list_databases()` |
| DescribeDatabase | 查看数据库详情 | `describe_database()` |
| CreateDatabase | 创建数据库 | `create_database()` |
| DropDatabase | 删除数据库 | `drop_database()` |
| AlterDatabase | 修改数据库属性 | `alter_database()` |

#### Collection 权限（18 种）

| 权限 | 说明 | 对应 API |
|------|------|----------|
| GetFlushState | 检查集合 flush 状态 | `get_flush_state()` |
| GetLoadState | 检查集合加载状态 | `get_load_state()` |
| GetLoadingProgress | 检查加载进度 | `get_loading_progress()` |
| ShowCollections | 查看所有集合 | `list_collections()` |
| ListAliases | 查看集合别名 | `list_aliases()` |
| DescribeCollection | 查看集合详情 | `describe_collection()` |
| DescribeAlias | 查看别名详情 | `describe_alias()` |
| GetStatistics | 获取集合统计信息 | `get_collection_statistics()` |
| CreateCollection | 创建集合 | `create_collection()` |
| DropCollection | 删除集合 | `drop_collection()` |
| Load | 加载集合 | `load_collection()` |
| Release | 释放集合 | `release_collection()` |
| Flush | 持久化数据 | `flush()` |
| Compaction | 手动触发压缩 | `compact()` |
| RenameCollection | 重命名集合 | `rename_collection()` |
| CreateAlias | 创建别名 | `create_alias()` |
| DropAlias | 删除别名 | `drop_alias()` |
| FlushAll | flush 数据库所有集合 | `flush_all()` |

#### Partition 权限（4 种）

| 权限 | 说明 | 对应 API |
|------|------|----------|
| HasPartition | 检查分区是否存在 | `has_partition()` |
| ShowPartitions | 查看所有分区 | `list_partitions()` |
| CreatePartition | 创建分区 | `create_partition()` |
| DropPartition | 删除分区 | `drop_partition()` |


#### Index 权限（3 种）

| 权限 | 说明 | 对应 API |
|------|------|----------|
| IndexDetail | 查看索引详情 | `describe_index()` |
| CreateIndex | 创建索引 | `create_index()` |
| DropIndex | 删除索引 | `drop_index()` |

#### Entity 权限（6 种）

| 权限 | 说明 | 对应 API |
|------|------|----------|
| Query | 执行查询 | `query()` |
| Search | 执行搜索 | `search()` |
| Insert | 插入数据 | `insert()` |
| Delete | 删除数据 | `delete()` |
| Upsert | 更新或插入数据 | `upsert()` |
| Import | 批量导入数据 | `bulk_insert()` |

#### Resource Management 权限（10 种）

| 权限 | 说明 |
|------|------|
| LoadBalance | 负载均衡 |
| CreateResourceGroup | 创建资源组 |
| DropResourceGroup | 删除资源组 |
| UpdateResourceGroups | 更新资源组 |
| DescribeResourceGroup | 查看资源组详情 |
| ListResourceGroups | 列出所有资源组 |
| TransferNode | 在资源组间转移节点 |
| TransferReplica | 在资源组间转移副本 |
| BackupRBAC | 备份 RBAC 配置 |
| RestoreRBAC | 恢复 RBAC 配置 |

#### RBAC 权限（10 种）

| 权限 | 说明 | 对应 API |
|------|------|----------|
| CreateOwnership | 创建用户或角色 | `create_user()` / `create_role()` |
| UpdateUser | 更新用户密码 | `update_password()` |
| DropOwnership | 删除用户或角色 | `drop_user()` / `drop_role()` |
| SelectOwnership | 查看角色授权 | `describe_role()` |
| ManageOwnership | 管理用户/角色/授权 | `grant_role()` / `grant_privilege()` |
| SelectUser | 查看用户角色 | `describe_user()` |
| CreatePrivilegeGroup | 创建权限组 | `create_privilege_group()` |
| DropPrivilegeGroup | 删除权限组 | `drop_privilege_group()` |
| ListPrivilegeGroups | 列出所有权限组 | `list_privilege_groups()` |
| OperatePrivilegeGroup | 操作权限组 | `add_privileges_to_group()` |


### Privilege Group（权限组）

权限组是多个权限的集合，用于简化批量授权操作[^3]。

**不使用权限组时**：授予 3 个权限需要执行 3 次授权操作。

**使用权限组时**：创建 1 个权限组，添加 3 个权限，然后 1 次授权即可。

![权限组示意图](https://milvus.io/docs/v2.6.x/assets/privilege-group-illustrated.png)
_权限组简化授权操作示意图_

### Role（角色）

角色是权限和资源的组合体，定义了可执行的操作类型及其作用范围。角色是连接用户与权限的桥梁。

## 2.2 内置权限组

Milvus 提供 9 个内置权限组，覆盖 Collection、Database、Cluster 三个级别[^3]。

### Collection 级别权限组

#### CollectionReadOnly (COLL_RO)

只读权限，适用于数据分析师等只需查询数据的角色。

| 权限 | 包含 |
|------|------|
| Query | ✔️ |
| Search | ✔️ |
| IndexDetail | ✔️ |
| GetFlushState | ✔️ |
| GetLoadState | ✔️ |
| GetLoadingProgress | ✔️ |
| HasPartition | ✔️ |
| ShowPartitions | ✔️ |
| ListAliases | ✔️ |
| DescribeCollection | ✔️ |
| DescribeAlias | ✔️ |
| GetStatistics | ✔️ |


#### CollectionReadWrite (COLL_RW)

读写权限，适用于应用开发者等需要读写数据的角色。

在 COLL_RO 基础上增加：

| 权限 | 包含 |
|------|------|
| CreateIndex | ✔️ |
| DropIndex | ✔️ |
| CreatePartition | ✔️ |
| DropPartition | ✔️ |
| Load | ✔️ |
| Release | ✔️ |
| Insert | ✔️ |
| Delete | ✔️ |
| Upsert | ✔️ |
| Import | ✔️ |
| Flush | ✔️ |
| Compaction | ✔️ |
| LoadBalance | ✔️ |

#### CollectionAdmin (COLL_ADMIN)

管理权限，适用于集合管理员。

在 COLL_RW 基础上增加：

| 权限 | 包含 |
|------|------|
| CreateAlias | ✔️ |
| DropAlias | ✔️ |

### Database 级别权限组

#### DatabaseReadOnly (DB_RO)

| 权限 | 包含 |
|------|------|
| ShowCollections | ✔️ |
| DescribeDatabase | ✔️ |
| CreateCollection | ✔️ |

#### DatabaseReadWrite (DB_RW)

在 DB_RO 基础上增加：

| 权限 | 包含 |
|------|------|
| AlterDatabase | ✔️ |

#### DatabaseAdmin (DB_Admin)

在 DB_RW 基础上增加：

| 权限 | 包含 |
|------|------|
| DropCollection | ✔️ |


### Cluster 级别权限组

#### ClusterReadOnly (Cluster_RO)

| 权限 | 包含 |
|------|------|
| ListDatabases | ✔️ |
| SelectOwnership | ✔️ |
| SelectUser | ✔️ |
| DescribeResourceGroup | ✔️ |
| ListResourceGroups | ✔️ |

#### ClusterReadWrite (Cluster_RW)

在 Cluster_RO 基础上增加：

| 权限 | 包含 |
|------|------|
| UpdateResourceGroups | ✔️ |
| TransferNode | ✔️ |
| TransferReplica | ✔️ |
| FlushAll | ✔️ |

#### ClusterAdmin (Cluster_Admin)

在 Cluster_RW 基础上增加：

| 权限 | 包含 |
|------|------|
| RenameCollection | ✔️ |
| CreateOwnership | ✔️ |
| UpdateUser | ✔️ |
| DropOwnership | ✔️ |
| ManageOwnership | ✔️ |
| BackupRBAC | ✔️ |
| RestoreRBAC | ✔️ |
| CreateResourceGroup | ✔️ |
| DropResourceGroup | ✔️ |
| CreateDatabase | ✔️ |
| DropDatabase | ✔️ |
| CreatePrivilegeGroup | ✔️ |
| DropPrivilegeGroup | ✔️ |
| ListPrivilegeGroups | ✔️ |
| OperatePrivilegeGroup | ✔️ |

### 内置权限组速查表

| 权限组 | 简称 | 级别 | 定位 |
|--------|------|------|------|
| CollectionReadOnly | COLL_RO | Collection | 只读查询 |
| CollectionReadWrite | COLL_RW | Collection | 读写操作 |
| CollectionAdmin | COLL_ADMIN | Collection | 集合管理 |
| DatabaseReadOnly | DB_RO | Database | 数据库只读 |
| DatabaseReadWrite | DB_RW | Database | 数据库读写 |
| DatabaseAdmin | DB_Admin | Database | 数据库管理 |
| ClusterReadOnly | Cluster_RO | Cluster | 集群只读 |
| ClusterReadWrite | Cluster_RW | Cluster | 集群读写 |
| ClusterAdmin | Cluster_Admin | Cluster | 集群管理 |


## 2.3 权限授予实战

### grant_privilege_v2() API

Milvus 2.5 引入了 `grant_privilege_v2()` API，简化了授权操作，无需再查找 object type[^2]。

API 参数说明：

| 参数 | 说明 |
|------|------|
| role_name | 目标角色名称 |
| privilege | 权限名称或权限组名称 |
| collection_name | 目标集合名称，`*` 表示所有集合 |
| db_name | 目标数据库名称，`*` 表示所有数据库 |

### 资源粒度控制

#### 授予特定集合权限

```python
from pymilvus import MilvusClient

client = MilvusClient(
    uri="http://localhost:19530",
    token="root:Milvus"
)

# 授予 role_a 对 default 数据库中 collection_01 的 Search 权限
client.grant_privilege_v2(
    role_name="role_a",
    privilege="Search",
    collection_name="collection_01",
    db_name="default"
)
```

#### 授予特定数据库下所有集合权限

```python
# 授予 role_a 对 default 数据库中所有集合的 Search 权限
client.grant_privilege_v2(
    role_name="role_a",
    privilege="Search",
    collection_name="*",
    db_name="default"
)
```

#### 授予所有数据库所有集合权限

```python
# 授予 role_a 对所有数据库所有集合的 Search 权限
client.grant_privilege_v2(
    role_name="role_a",
    privilege="Search",
    collection_name="*",
    db_name="*"
)
```

#### 授予内置权限组

```python
# 授予 role_a 集群只读权限组
client.grant_privilege_v2(
    role_name="role_a",
    privilege="ClusterReadOnly",
    collection_name="*",
    db_name="*"
)
```


### 资源粒度对照表

| 级别 | collection_name | db_name | 说明 |
|------|-----------------|---------|------|
| Collection | `"collection_01"` | `"default"` | 特定数据库的特定集合 |
| Database 下所有集合 | `"*"` | `"default"` | 特定数据库的所有集合 |
| Instance | `"*"` | `"*"` | 所有数据库的所有集合 |

### 自定义权限组

当内置权限组无法满足需求时，可以创建自定义权限组。

#### 创建权限组

```python
# 创建名为 search_and_query 的权限组
client.create_privilege_group(group_name="search_and_query")
```

#### 添加权限到权限组

```python
# 向权限组添加 Search 和 Query 权限
client.add_privileges_to_group(
    group_name="search_and_query",
    privileges=["Search", "Query"]
)
```

#### 查看权限组列表

```python
print(client.list_privilege_groups())
# 输出示例:
# PrivilegeGroupItem: <privilege_group:search_and_query>, <privileges:('Search', 'Query')>
```

#### 从权限组移除权限

```python
# 从权限组移除 Query 权限
client.remove_privileges_from_group(
    group_name="search_and_query",
    privileges=["Query"]
)
```

#### 授予自定义权限组

```python
# 将自定义权限组授予角色
client.grant_privilege_v2(
    role_name="role_a",
    privilege="search_and_query",
    collection_name="collection_01",
    db_name="default"
)
```

#### 删除权限组

```python
client.drop_privilege_group(group_name="search_and_query")
```


### 权限审计

#### 查看角色权限

```python
# 查看 role_a 的所有权限
result = client.describe_role(role_name="role_a")
print(result)
```

输出示例：

```python
{
    "role": "role_a",
    "privileges": [
        {
            "collection_name": "collection_01",
            "db_name": "default",
            "role_name": "role_a",
            "privilege": "Search",
            "grantor_name": "root"
        },
        {
            "collection_name": "*",
            "db_name": "*",
            "role_name": "role_a",
            "privilege": "ClusterReadOnly",
            "grantor_name": "root"
        }
    ]
}
```

输出字段说明：

| 字段 | 说明 |
|------|------|
| collection_name | 权限作用的集合 |
| db_name | 权限作用的数据库 |
| role_name | 角色名称 |
| privilege | 权限或权限组名称 |
| grantor_name | 授权者 |

## 2.4 权限撤销与角色管理

### 撤销权限

使用 `revoke_privilege_v2()` 撤销已授予的权限：

```python
# 撤销 role_a 对 collection_01 的 Search 权限
client.revoke_privilege_v2(
    role_name="role_a",
    privilege="Search",
    collection_name="collection_01",
    db_name="default"
)

# 撤销 role_a 的 ClusterReadOnly 权限组
client.revoke_privilege_v2(
    role_name="role_a",
    privilege="ClusterReadOnly",
    collection_name="*",
    db_name="*"
)
```

> 撤销权限时，参数必须与授予时完全匹配（role_name、privilege、collection_name、db_name）。
{: .prompt-info }


### 撤销用户角色

```python
# 撤销 user_1 的 role_a 角色
client.revoke_role(
    user_name="user_1",
    role_name="role_a"
)

# 验证撤销结果
print(client.describe_user(user_name="user_1"))
# 输出: {'user_name': 'user_1', 'roles': ()}
```

### 角色删除

删除角色前，需要先清理该角色的所有权限和用户绑定关系。

#### 完整的角色删除流程

```python
role_name = "role_to_delete"

# 1. 查看角色当前权限
role_info = client.describe_role(role_name=role_name)
print(f"当前权限: {role_info}")

# 2. 撤销所有权限
for priv in role_info.get("privileges", []):
    client.revoke_privilege_v2(
        role_name=role_name,
        privilege=priv["privilege"],
        collection_name=priv["collection_name"],
        db_name=priv["db_name"]
    )

# 3. 查看绑定该角色的用户
users = client.list_users()
for user in users:
    user_info = client.describe_user(user_name=user)
    if role_name in user_info.get("roles", ()):
        # 4. 撤销用户的角色绑定
        client.revoke_role(user_name=user, role_name=role_name)

# 5. 删除角色
client.drop_role(role_name=role_name)
```

### 权限操作对照表

| 操作 | API | 说明 |
|------|-----|------|
| 授予权限 | `grant_privilege_v2()` | 向角色授予权限或权限组 |
| 撤销权限 | `revoke_privilege_v2()` | 撤销角色的权限或权限组 |
| 授予角色 | `grant_role()` | 将角色绑定到用户 |
| 撤销角色 | `revoke_role()` | 解除用户与角色的绑定 |
| 查看角色权限 | `describe_role()` | 审计角色的所有权限 |
| 删除角色 | `drop_role()` | 删除角色（需先清理权限） |

## 小结

本文介绍了 Milvus RBAC 的核心机制：

1. **四要素模型**：Resource、Privilege、Privilege Group、Role 构成完整的权限控制体系
2. **56 种细粒度权限**：覆盖 Database、Collection、Partition、Index、Entity、RBAC 六大类操作
3. **9 个内置权限组**：COLL_RO/RW/ADMIN、DB_RO/RW/Admin、Cluster_RO/RW/Admin 满足常见场景
4. **grant_privilege_v2() API**：Milvus 2.5+ 推荐的授权方式，支持灵活的资源粒度控制
5. **自定义权限组**：当内置权限组不满足需求时，可组合任意权限

下一篇将介绍生产环境中的多租户权限设计、资源组隔离策略，以及权限备份恢复等运维实践。

## 参考来源

[^1]: [Milvus RBAC Explained](https://milvus.io/docs/rbac.md)
[^2]: [Grant Privilege or Privilege Group to Roles](https://milvus.io/docs/grant_privileges.md)
[^3]: [Create Privilege Group](https://milvus.io/docs/privilege_group.md)
[^4]: [Grant Roles to Users](https://milvus.io/docs/grant_roles.md)
[^5]: [Create Users & Roles](https://milvus.io/docs/users_and_roles.md)
