---
title: Milvus 权限管理实战（三）：多租户与生产运维
description: 介绍 Milvus 多租户权限设计、资源组隔离、最佳实践及常见问题排查
author: Alden
date: 2025-08-17 10:00:00 +0800
categories: [LLM Engineering]
tags: [Milvus, RBAC, Vector Database, Python, Multi-Tenancy, Production]
pin: false
mermaid: false
comments: true
---

> 面向对象：已部署 Milvus Standalone (Docker Compose)、具备传统 RDBMS RBAC 经验的 Python 开发者
>
> 基于 Milvus 2.6+ / PyMilvus

## 3.1 多租户权限设计

### Database 级别隔离策略

在多租户场景下，Database 级别隔离是一种常见且有效的策略[^5]。该策略为每个租户分配独立的数据库，具有以下特点：

- **强逻辑隔离**：租户数据存储在独立的 Database 中，天然隔离
- **简化管理**：权限按 Database 粒度授予，管理清晰
- **增强安全性**：租户间无法跨 Database 访问数据

#### 典型架构

```
Milvus Instance
    ├── Database: tenant_a
    │       ├── Collection: products
    │       └── Collection: users
    ├── Database: tenant_b
    │       ├── Collection: products
    │       └── Collection: orders
    └── Database: tenant_c
            └── Collection: documents
```
{: .nolineno }


#### 权限配置示例

```python
from pymilvus import MilvusClient

client = MilvusClient(
    uri="http://localhost:19530",
    token="root:Milvus"
)

# 为租户 A 创建专属用户和角色
client.create_user(user_name="tenant_a_user", password="TenantA@123")
client.create_role(role_name="tenant_a_role")

# 授予租户 A 对其 Database 的完整权限
client.grant_privilege_v2(
    role_name="tenant_a_role",
    privilege="DatabaseAdmin",
    collection_name="*",
    db_name="tenant_a"
)

# 授予租户 A 对其 Database 下所有集合的读写权限
client.grant_privilege_v2(
    role_name="tenant_a_role",
    privilege="CollectionReadWrite",
    collection_name="*",
    db_name="tenant_a"
)

# 绑定角色到用户
client.grant_role(user_name="tenant_a_user", role_name="tenant_a_role")
```

此配置下，`tenant_a_user` 只能访问 `tenant_a` 数据库，无法访问其他租户的数据。

### 资源组（Resource Group）与物理隔离

对于处理关键或高度敏感数据的业务单元，可以在 Database 级别多租户结构之上实施物理隔离[^5]。

资源组（Resource Group）可以将逻辑组件（如 Database 和 Collection）映射到物理资源[^4]，确保关键操作不受其他租户影响。

#### 资源组层次结构

```
Physical Layer          Logical Layer
─────────────          ─────────────
Query Node  ◄────────►  Resource Group  ◄────────►  Database/Collection
```
{: .nolineno }

资源管理分为三层[^5]：

| 层级 | 说明 |
|------|------|
| Query Node | 处理查询任务的物理组件 |
| Resource Group | Query Node 的集合，作为逻辑与物理资源的桥梁 |
| Database | 逻辑数据库 |


#### 资源组配置示例

```python
from pymilvus import MilvusClient
from pymilvus.client.types import ResourceGroupConfig

client = MilvusClient(
    uri="http://localhost:19530",
    token="root:Milvus"
)

# 创建专用资源组
client.create_resource_group(
    name="tenant_a_rg",
    config=ResourceGroupConfig(
        requests={"node_num": 2},
        limits={"node_num": 2},
    )
)

# 加载集合到指定资源组
client.load_collection(
    collection_name="products",
    replica_number=1,
    _resource_groups=["tenant_a_rg"]
)
```

通过将关键数据库分配到专用资源组，可以保证其不受其他数据库工作负载的影响。

### 典型场景：一个 Database 一个租户

#### 场景描述

企业级知识库系统，多个业务部门共享同一 Milvus 实例，每个部门拥有独立的数据空间和访问权限。

#### 权限矩阵设计

| 角色 | Database 范围 | 权限级别 | 说明 |
|------|--------------|---------|------|
| dept_a_admin | dept_a | DB_Admin + COLL_ADMIN | 部门 A 管理员 |
| dept_a_developer | dept_a | COLL_RW | 部门 A 开发者 |
| dept_a_analyst | dept_a | COLL_RO | 部门 A 分析师 |
| dept_b_admin | dept_b | DB_Admin + COLL_ADMIN | 部门 B 管理员 |
| platform_admin | * | Cluster_Admin | 平台管理员 |


#### 完整配置代码

```python
from pymilvus import MilvusClient

client = MilvusClient(
    uri="http://localhost:19530",
    token="root:Milvus"
)

def setup_tenant(tenant_name: str):
    """为租户配置完整的权限体系"""
    
    # 创建数据库
    client.create_database(db_name=tenant_name)
    
    # 创建角色
    admin_role = f"{tenant_name}_admin"
    dev_role = f"{tenant_name}_developer"
    analyst_role = f"{tenant_name}_analyst"
    
    client.create_role(role_name=admin_role)
    client.create_role(role_name=dev_role)
    client.create_role(role_name=analyst_role)
    
    # 管理员角色：数据库管理 + 集合管理
    client.grant_privilege_v2(
        role_name=admin_role,
        privilege="DatabaseAdmin",
        collection_name="*",
        db_name=tenant_name
    )
    client.grant_privilege_v2(
        role_name=admin_role,
        privilege="CollectionAdmin",
        collection_name="*",
        db_name=tenant_name
    )
    
    # 开发者角色：集合读写
    client.grant_privilege_v2(
        role_name=dev_role,
        privilege="CollectionReadWrite",
        collection_name="*",
        db_name=tenant_name
    )
    
    # 分析师角色：集合只读
    client.grant_privilege_v2(
        role_name=analyst_role,
        privilege="CollectionReadOnly",
        collection_name="*",
        db_name=tenant_name
    )
    
    return admin_role, dev_role, analyst_role

# 配置租户
setup_tenant("dept_a")
setup_tenant("dept_b")
```

## 3.2 最佳实践

### 最小权限原则落地

最小权限原则（Principle of Least Privilege）要求用户仅获得完成工作所需的最小权限集合。

#### 实施要点

| 原则 | 实施方式 |
|------|---------|
| 按需授权 | 仅授予用户实际需要的权限，避免使用 `*` 通配符 |
| 角色分离 | 区分管理员、开发者、分析师等角色，权限不交叉 |
| 定期审计 | 使用 `describe_role()` 定期检查角色权限 |
| 及时回收 | 用户职责变更时及时撤销不再需要的权限 |


#### 反模式示例

```python
# ❌ 反模式：授予过大权限
client.grant_privilege_v2(
    role_name="app_role",
    privilege="ClusterAdmin",  # 过度授权
    collection_name="*",
    db_name="*"
)

# ✔️ 正确做法：精确授权
client.grant_privilege_v2(
    role_name="app_role",
    privilege="Search",
    collection_name="products",
    db_name="ecommerce"
)
client.grant_privilege_v2(
    role_name="app_role",
    privilege="Query",
    collection_name="products",
    db_name="ecommerce"
)
```

### 权限变更流程

标准的权限变更流程遵循以下步骤：

```
创建角色 → 定义权限 → 授予权限 → 绑定用户 → 验证生效
```
{: .nolineno }

#### 完整流程示例

```python
from pymilvus import MilvusClient

client = MilvusClient(
    uri="http://localhost:19530",
    token="root:Milvus"
)

def grant_access(user_name: str, password: str, role_name: str, 
                 privileges: list, collection_name: str, db_name: str):
    """标准权限授予流程"""
    
    # Step 1: 创建用户（如不存在）
    try:
        client.create_user(user_name=user_name, password=password)
        print(f"用户 {user_name} 创建成功")
    except Exception as e:
        print(f"用户已存在或创建失败: {e}")
    
    # Step 2: 创建角色（如不存在）
    try:
        client.create_role(role_name=role_name)
        print(f"角色 {role_name} 创建成功")
    except Exception as e:
        print(f"角色已存在或创建失败: {e}")
    
    # Step 3: 授予权限
    for privilege in privileges:
        client.grant_privilege_v2(
            role_name=role_name,
            privilege=privilege,
            collection_name=collection_name,
            db_name=db_name
        )
        print(f"权限 {privilege} 授予成功")
    
    # Step 4: 绑定角色到用户
    client.grant_role(user_name=user_name, role_name=role_name)
    print(f"角色 {role_name} 绑定到用户 {user_name}")
    
    # Step 5: 验证
    user_info = client.describe_user(user_name=user_name)
    role_info = client.describe_role(role_name=role_name)
    print(f"用户信息: {user_info}")
    print(f"角色权限: {role_info}")

# 使用示例
grant_access(
    user_name="search_service",
    password="SearchSvc@123",
    role_name="search_role",
    privileges=["Search", "Query", "DescribeCollection"],
    collection_name="products",
    db_name="default"
)
```


### 权限备份与恢复

Milvus 提供 `BackupRBAC` 和 `RestoreRBAC` 权限，用于备份和恢复 RBAC 配置[^2]。

#### 备份 RBAC 配置

具有 `BackupRBAC` 权限的用户可以导出当前实例的所有 RBAC 配置，包括：

- 所有用户
- 所有角色
- 角色的权限配置
- 用户与角色的绑定关系

#### 恢复 RBAC 配置

具有 `RestoreRBAC` 权限的用户可以从备份中恢复 RBAC 配置。

#### 权限要求

```python
# 授予备份恢复权限
client.grant_privilege_v2(
    role_name="backup_admin",
    privilege="BackupRBAC",
    collection_name="*",
    db_name="*"
)

client.grant_privilege_v2(
    role_name="backup_admin",
    privilege="RestoreRBAC",
    collection_name="*",
    db_name="*"
)
```

> `BackupRBAC` 和 `RestoreRBAC` 属于 Cluster 级别权限，包含在 `ClusterAdmin` 权限组中。
{: .prompt-info }

## 3.3 常见问题

### 权限不生效排查

当权限配置后未按预期生效时，可按以下步骤排查：

#### 排查清单

| 检查项 | 排查方法 |
|--------|---------|
| 认证是否启用 | 检查 `authorizationEnabled: true` 配置 |
| 用户是否存在 | `client.list_users()` |
| 角色是否存在 | `client.list_roles()` |
| 角色是否绑定用户 | `client.describe_user(user_name="xxx")` |
| 角色是否有权限 | `client.describe_role(role_name="xxx")` |
| 权限粒度是否匹配 | 检查 collection_name 和 db_name 是否正确 |


#### 排查脚本

```python
def diagnose_permission(user_name: str, target_collection: str, target_db: str):
    """权限问题诊断"""
    
    print(f"=== 诊断用户 {user_name} 的权限 ===\n")
    
    # 1. 检查用户是否存在
    users = client.list_users()
    if user_name not in users:
        print(f"❌ 用户 {user_name} 不存在")
        return
    print(f"✔️ 用户 {user_name} 存在")
    
    # 2. 检查用户绑定的角色
    user_info = client.describe_user(user_name=user_name)
    roles = user_info.get("roles", ())
    if not roles:
        print(f"❌ 用户 {user_name} 未绑定任何角色")
        return
    print(f"✔️ 用户绑定角色: {roles}")
    
    # 3. 检查每个角色的权限
    for role in roles:
        role_info = client.describe_role(role_name=role)
        privileges = role_info.get("privileges", [])
        print(f"\n角色 {role} 的权限:")
        
        for priv in privileges:
            coll = priv.get("collection_name", "")
            db = priv.get("db_name", "")
            privilege = priv.get("privilege", "")
            
            # 检查是否覆盖目标资源
            coll_match = (coll == "*" or coll == target_collection)
            db_match = (db == "*" or db == target_db)
            
            status = "✔️" if (coll_match and db_match) else "  "
            print(f"  {status} {privilege} on {db}.{coll}")

# 使用示例
diagnose_permission("app_user", "products", "default")
```

### root 权限自定义（2.4.21+）

从 Milvus 2.4.21 版本开始，root 用户的权限可以自定义[^6]。

#### 背景

默认情况下，`root` 用户拥有 `admin` 角色，具有所有资源的完整访问权限。在某些安全合规场景下，可能需要限制 root 用户的权限范围。

#### 配置方式

在 Milvus 配置文件中设置 `rootShouldBindRole`：

```yaml
common:
  security:
    authorizationEnabled: true
    rootShouldBindRole: true  # 启用后 root 需要显式绑定角色
```
{: file="user.yaml" }

启用此配置后：

- root 用户不再自动拥有所有权限
- 需要显式为 root 用户绑定角色
- 可以精确控制 root 用户的权限范围

> 此功能适用于高安全要求的生产环境。配置前需确保有其他管理员账户可用，避免锁定。建议在测试环境验证后再应用到生产环境。
{: .prompt-warning }

## 附录

### A. 权限完整列表速查

| 类别 | 权限数量 | 权限列表 |
|------|---------|---------|
| Database | 5 | ListDatabases, DescribeDatabase, CreateDatabase, DropDatabase, AlterDatabase |
| Collection | 18 | GetFlushState, GetLoadState, GetLoadingProgress, ShowCollections, ListAliases, DescribeCollection, DescribeAlias, GetStatistics, CreateCollection, DropCollection, Load, Release, Flush, Compaction, RenameCollection, CreateAlias, DropAlias, FlushAll |
| Partition | 4 | HasPartition, ShowPartitions, CreatePartition, DropPartition |
| Index | 3 | IndexDetail, CreateIndex, DropIndex |
| Entity | 6 | Query, Search, Insert, Delete, Upsert, Import |
| Resource Management | 10 | LoadBalance, CreateResourceGroup, DropResourceGroup, UpdateResourceGroups, DescribeResourceGroup, ListResourceGroups, TransferNode, TransferReplica, BackupRBAC, RestoreRBAC |
| RBAC | 10 | CreateOwnership, UpdateUser, DropOwnership, SelectOwnership, ManageOwnership, SelectUser, CreatePrivilegeGroup, DropPrivilegeGroup, ListPrivilegeGroups, OperatePrivilegeGroup |


### B. 内置权限组对照表

| 权限组 | 级别 | 包含权限数 | 典型用途 |
|--------|------|-----------|---------|
| COLL_RO | Collection | 12 | 数据分析、报表查询 |
| COLL_RW | Collection | 25 | 应用开发、数据写入 |
| COLL_ADMIN | Collection | 27 | 集合管理、别名管理 |
| DB_RO | Database | 3 | 数据库浏览 |
| DB_RW | Database | 4 | 数据库配置修改 |
| DB_Admin | Database | 5 | 数据库完整管理 |
| Cluster_RO | Cluster | 5 | 集群状态查看 |
| Cluster_RW | Cluster | 9 | 集群资源调整 |
| Cluster_Admin | Cluster | 24 | 集群完整管理 |

### C. PyMilvus 代码片段索引

| 操作 | API | 章节 |
|------|-----|------|
| 启用认证连接 | `MilvusClient(token="user:pass")` | 1.2 |
| 创建用户 | `create_user()` | 1.3 |
| 创建角色 | `create_role()` | 1.3 |
| 绑定角色 | `grant_role()` | 1.3 |
| 授予权限 | `grant_privilege_v2()` | 2.3 |
| 撤销权限 | `revoke_privilege_v2()` | 2.4 |
| 查看角色权限 | `describe_role()` | 2.3 |
| 创建权限组 | `create_privilege_group()` | 2.3 |
| 添加权限到组 | `add_privileges_to_group()` | 2.3 |
| 创建资源组 | `create_resource_group()` | 3.1 |

## 小结

本文介绍了 Milvus RBAC 在生产环境中的实践：

1. **多租户设计**：Database 级别隔离提供逻辑隔离，资源组提供物理隔离
2. **最小权限原则**：按需授权、角色分离、定期审计、及时回收
3. **标准变更流程**：创建角色 → 定义权限 → 授予权限 → 绑定用户 → 验证生效
4. **权限备份恢复**：`BackupRBAC` / `RestoreRBAC` 支持 RBAC 配置的导出和恢复
5. **版本兼容性**：2.5+ 推荐使用 `grant_privilege_v2()` API

结合前两篇文章，完整的 Milvus RBAC 知识体系已经建立。在实际应用中，根据业务需求选择合适的隔离策略和权限粒度，遵循最小权限原则，可以构建安全、可控的向量数据库访问体系。

## 参考来源

[^1]: [Milvus RBAC Explained](https://milvus.io/docs/rbac.md)
[^2]: [Grant Privilege or Privilege Group to Roles](https://milvus.io/docs/grant_privileges.md)
[^3]: [Create Privilege Group](https://milvus.io/docs/privilege_group.md)
[^4]: [Manage Resource Groups](https://milvus.io/docs/resource_group.md)
[^5]: [Build Multi-tenancy RAG with Milvus](https://milvus.io/blog/build-multi-tenancy-rag-with-milvus-best-practices-part-one.md)
[^6]: [Milvus v2.4.x Release Notes](https://mio/docs/v2.4.x/release_notes.md)
