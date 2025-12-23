---
title: Milvus 权限管理实战（一）：从 RDBMS RBAC 到 Milvus
description: 面向具备传统 RDBMS RBAC 经验的 Python 开发者，介绍 Milvus RBAC 基础概念、认证配置和用户角色管理
author: Alden
date: 2025-08-15 10:00:00 +0800
categories: [LLM Engineering, Milvus]
tags: [milvus, rbac, vector database, python, authentication]
pin: false
mermaid: false
comments: true
---

> 面向对象：已部署 Milvus Standalone (Docker Compose)、具备传统 RDBMS RBAC 经验的 Python 开发者
>
> 基于 Milvus 2.6+ / PyMilvus

## 1.1 概念映射：Milvus vs 传统数据库权限模型

### RBAC 模型对比

传统关系型数据库（如 MySQL、PostgreSQL）的 RBAC 模型通常围绕 Database → Schema → Table 三层结构展开。Milvus 作为向量数据库，采用了类似但有所区别的权限体系。

| 概念 | 传统 RDBMS | Milvus |
|------|-----------|--------|
| 最高层级 | Instance/Cluster | Instance (Cluster) |
| 中间层级 | Database | Database |
| 数据层级 | Table/View | Collection |
| 权限载体 | Role | Role |
| 权限单元 | Privilege | Privilege / Privilege Group |

Milvus RBAC 模型包含四个核心组件[^1]：

- **Resource（资源）**：可访问的资源实体，Milvus 中有三个级别——Instance、Database 和 Collection
- **Privilege（权限）**：对 Milvus 资源执行特定操作的许可（如创建集合、插入数据等）
- **Privilege Group（权限组）**：多个权限的组合
- **Role（角色）**：由权限和资源两部分组成，定义了角色可以执行的操作类型

![RBAC 模型示意图](https://milvus.io/docs/v2.6.x/assets/users-roles-privileges.png)
_Milvus RBAC 模型示意图_

### 四层资源体系

Milvus 的资源层次结构为：

```
Instance (Cluster)
    └── Database
            └── Collection
                    └── Partition
```
{: .nolineno }

#### 各层级含义

| 层级 | 说明 | 限制 |
|------|------|------|
| **Instance (Cluster)** | 整个 Milvus 部署实例，包含所有 Database | 顶层资源，权限作用于全局 |
| **Database** | 数据库，包含多个 Collection，通过 `db_name` 参数指定 | 逻辑隔离单元 |
| **Collection** | 集合，类似关系型数据库中的表，由固定列数和可变行数的二维表组成 | 每个 Collection 最多支持 64 个 Partition |
| **Partition** | 分区，Collection 的子集，与父 Collection 共享相同的数据结构 | 每个 Collection 最多 1,024 个 Partition |

Collection 中每列对应一个字段（Field），每行代表一个实体（Entity）。创建 Collection 时，Milvus 会自动创建名为 `_default` 的默认分区。

这种层级结构的设计目的：

- **数据隔离**：通过 Database 和 Collection 实现逻辑隔离
- **搜索优化**：通过 Partition 缩小搜索范围，提高查询效率

#### 权限粒度选择

| 级别 | 资源范围 | 典型场景 |
|------|---------|---------|
| Instance | 整个 Milvus 实例 | 集群管理员、DBA |
| Database | 特定数据库 | 业务线负责人 |
| Collection | 特定集合 | 应用开发者 |

### 无级联设计：关键差异点

与部分传统数据库不同，**Milvus 的三个级别内置权限组之间没有级联关系**[^5]。

这意味着：

- 在 Instance 级别设置权限组**不会**自动为该实例下的所有 Database 和 Collection 设置权限
- Database 和 Collection 级别的权限需要**手动设置**

这种设计的考量包括：

1. **精细化控制**：允许管理员在不同层级独立设置权限，避免过度授权
2. **安全性**：防止高层级权限自动传播到低层级资源
3. **灵活性**：支持针对特定资源的权限管理，而不影响其他层级

**示例场景**：

假设需要授予用户 `analyst` 对 `db_prod` 数据库的只读权限，同时对 `db_prod.collection_sensitive` 集合完全禁止访问。在级联模型下，这种需求难以实现；而 Milvus 的无级联设计可以精确控制每个层级的权限。

## 1.2 启用认证（Docker Standalone）

### 配置文件修改

Milvus 默认不启用认证。对于 Docker Compose 部署的 Standalone 模式，需要在配置文件中显式开启。

在当前目录创建或编辑 `user.yaml` 文件[^2]：

```yaml
common:
  security:
    authorizationEnabled: true
```
{: file="user.yaml" }

### 容器重启

配置修改后，重启 Milvus 服务使配置生效：

```bash
bash standalone_embed.sh restart
```
{: .nolineno }

或使用 Docker Compose：

```bash
docker-compose down
docker-compose up -d
```
{: .nolineno }

### root 用户首次连接

启用认证后，Milvus 会自动创建默认的 `root` 用户[^2]：

- **用户名**：`root`
- **默认密码**：`Milvus`

使用 PyMilvus MilvusClient 进行认证连接：

```python
from pymilvus import MilvusClient

client = MilvusClient(
    uri='http://localhost:19530',
    token="root:Milvus"
)
```

`token` 参数格式为 `username:password`。

> 生产环境中应立即修改 root 用户密码，避免使用默认凭据。
{: .prompt-warning }

### 认证失败处理

如果连接时未提供有效的 token，或者 token 格式错误，Milvus 会返回 gRPC 错误。

## 1.3 用户与角色基础操作

### 创建用户

用户名和密码需遵循以下规则[^3]：

- **用户名**：必须以字母开头，只能包含大小写字母、数字和下划线
- **密码**：长度 8-64 字符，必须包含以下四类中的三类：大写字母、小写字母、数字、特殊字符

```python
from pymilvus import MilvusClient

client = MilvusClient(
    uri="http://localhost:19530",
    token="root:Milvus"
)

# 创建新用户
client.create_user(
    user_name="user_1",
    password="P@ssw0rd"
)

# 验证用户创建成功
print(client.describe_user("user_1"))
# 输出: {'user_name': 'user_1', 'roles': ()}
```

### 创建角色

角色名称规则[^3]：

- 必须以字母开头，只能包含大小写字母、数字和下划线

```python
# 创建自定义角色
client.create_role(role_name="role_a")

# 查看所有角色
print(client.list_roles())
# 输出: ['admin', 'role_a']
```

Milvus 内置了 `admin` 角色，该角色拥有所有资源的访问权限。

### 角色绑定用户

将角色授予用户，使用户获得该角色定义的权限：

```python
# 将 role_a 授予 user_1
client.grant_role(
    user_name="user_1",
    role_name="role_a"
)

# 验证角色绑定
print(client.describe_user(user_name="user_1"))
# 输出: {'user_name': 'user_1', 'roles': ('role_a',)}
```

一个用户可以被授予多个角色，用户的最终权限是所有角色权限的并集。

### 撤销角色绑定

```python
# 撤销 user_1 的 role_a 角色
client.revoke_role(
    user_name='user_1',
    role_name='role_a'
)
```

### 密码管理

#### 修改密码

```python
client.update_password(
    user_name="user_1",
    old_password="P@ssw0rd",
    new_password="NewP@ssw0rd123"
)
```

新密码同样需要满足 8-64 字符长度，且包含三类字符的要求。

#### 超级用户配置

如果忘记旧密码，可以通过配置超级用户来重置密码[^2]。在 Milvus 配置文件中添加：

```yaml
common:
  security:
    superUsers: root, admin_backup
```
{: file="user.yaml" }

超级用户在重置密码时无需提供旧密码。默认情况下，`common.security.superUsers` 字段为空，所有用户重置密码时都必须提供旧密码。

### 删除用户

```python
client.drop_user(user_name="user_1")
```

> 不能删除当前登录的用户，否则会返回错误。
{: .prompt-danger }

### 查看所有用户

```python
print(client.list_users())
# 输出: ['root', 'user_1', 'user_2']
```

### 用户名限制

用户名长度限制[^2]：

- 不能为空
- 最大长度 32 字符
- 必须以字母开头
- 只能包含下划线、字母或数字

## 小结

本文介绍了 Milvus RBAC 的基础概念和入门操作：

| 操作 | API |
|------|-----|
| 创建用户 | `client.create_user()` |
| 创建角色 | `client.create_role()` |
| 角色绑定用户 | `client.grant_role()` |
| 撤销角色 | `client.revoke_role()` |
| 修改密码 | `client.update_password()` |
| 删除用户 | `client.drop_user()` |
| 查看用户 | `client.list_users()` / `client.describe_user()` |
| 查看角色 | `client.list_roles()` |

此时创建的角色尚未关联任何权限，仅是一个空的权限容器。下一篇将深入介绍 Milvus 的 56 种细粒度权限、9 个内置权限组，以及如何使用 `grant_privilege_v2()` API 进行权限授予。

## 参考来源

[^1]: [Milvus RBAC Explained](https://milvus.io/docs/rbac.md)
[^2]: [Authenticate User Access](https://milvus.io/docs/authenticate.md)
[^3]: [Create Users & Roles](https://milvus.io/docs/users_and_roles.md)
[^4]: [Grant Roles to Users](https://milvus.io/docs/grant_roles.md)
[^5]: [Create Privilege Group](https://milvus.io/docs/privilege_group.md)
