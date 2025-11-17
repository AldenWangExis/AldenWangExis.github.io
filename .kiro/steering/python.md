---
inclusion: fileMatch
fileMatchPattern: "*.md"
---
<!------------------------------------------------------------------------------------
   Add rules to this file or a short description and have Kiro refine them for you.
   
   Learn about inclusion modes: https://kiro.dev/docs/steering/#inclusion-modes
------------------------------------------------------------------------------------->
<?xml version="1.0" encoding="UTF-8"?>
<EngineeringSpecification theme="Python 工程规范文档（文件级）">
    <Module name="Python 文件级规范">
        <Category name="通用规则">
            <Section name="代码风格与检查">
                <Rule id="1.0">遵循 Google Python Style Guide, PEP8, PEP257 等规范。</Rule>
                <Rule id="1.0.1">代码风格使用 ruff 检查和格式化，类型检查使用 mypy --strict。</Rule>
                <Rule id="1.0.2">禁止出现任何 emoji。</Rule>
                <Rule id="1.0.3">
                    <Title>导入规范</Title>
                    <Detail>模块内的导入优先使用绝对导入(`from package.module import Class`)。</Detail>
                    <Detail>禁止使用相对导入 (`from .module import Class`)，避免混淆和可移植性问题。</Detail>
                </Rule>
            </Section>
        </Category>

        <Category name="文档规范">
            <Section name="模块文档字符串">
                <Requirement id="1.1">
                    <Title>模块文档级注释 (Module Docstrings)</Title>
                    <Detail>位于每个 `.py` 文件开头。</Detail>
                    <Detail>当前模块用途、核心类和方法、最小调用示例。</Detail>
                    <Detail>核心依赖库、设计模式（如适用）。</Detail>
                    <Detail>使用 `git blame` 命令查看文件历史，确保文档更新及时。</Detail>
                    <Detail>作者（默认 ZHWA）、创建时间（东八区，YYYY-MM-DD）、最新修改时间、参考规范文档目录列表（必须）。</Detail>
                    <Example>
                        ```python
                        """
                        user_service.py
                        
                        用户服务模块，提供用户管理的核心业务逻辑
                        
                        核心：
                        - UserService: CRUD + 认证
                        - authenticate_user(): 验证用户凭证
                        
                        最小调用：
                            service = UserService(db_session)
                            user = await service.create_user(username="john", email="john@example.com")
                        
                        技术依赖：SQLAlchemy, pydantic, loguru
                        
                        作者: ZHWA
                        创建: 2025-10-14
                        修改: 2025-10-14
                        规范: docs/01_SPEC_user_management.md, docs/01_PLAN_backend_architecture.md
                        """
                        ```
                    </Example>
                </Requirement>
            </Section>

            <Section name="函数与类文档字符串">
                <Requirement id="1.2">
                    <Title>函数/类文档注释 (Docstrings)</Title>
                    <Rule id="1.2.1">使用 Google Style Docstrings，始终使用 """triple double quotes"""。</Rule>
                    <Rule id="1.2.2">
                        <Title>类型提示与说明</Title>
                        <Detail>必须使用类型提示，Python 3.10+ 使用新语法（list[T], X | Y）。</Detail>
                        <Detail>公共 API 必须包含完整的 Args/Returns/Raises 说明。</Detail>
                        <Detail>内部函数可省略 Raises</Detail>
                        <Example>
                            ```python
                            async def get_user(user_id: int, include_deleted: bool = False) -> User | None:
                                """
                                获取用户信息
                                
                                Args:
                                    user_id: 用户ID
                                    include_deleted: 是否包含已删除用户
                                    
                                Returns:
                                    用户对象，不存在返回 None
                                    
                                Raises:
                                    ValidationError: user_id 无效
                                    DatabaseError: 数据库连接失败
                                """
                            ```
                        </Example>
                    </Rule>
                </Requirement>
            </Section>
        </Category>

        <Category name="项目级约定">
            <Section name="环境与依赖">
                <Convention id="1.3.1">
                    <Title>环境管理</Title>
                    <Tool>uv</Tool>
                    <Detail>使用 uv 管理依赖和虚拟环境（uv init, uv add, uv run）。</Detail>
                </Convention>
            </Section>

            <Section name="数据与验证">
                <Convention id="1.3.2">
                    <Title>数据模型</Title>
                    <Tool>pydantic 2.x</Tool>
                    <Detail>API 数据验证使用 Pydantic，配置管理使用 pydantic-settings。</Detail>
                </Convention>
            </Section>

            <Section name="日志与异常">
                <Convention id="1.3.3">
                    <Title>日志规范</Title>
                    <Tool>loguru</Tool>
                    <Detail>统一使用 loguru，禁止 print。关键操作记录 INFO 级别，异常使用 logger.exception。</Detail>
                </Convention>
                <Convention id="1.3.4">
                    <Title>异常处理</Title>
                    <Detail>自定义异常继承自业务基类，避免裸 except。异常链使用 raise ... from e。</Detail>
                </Convention>
            </Section>

            <Section name="测试">
                <Convention id="1.3.5">
                    <Title>测试</Title>
                    <Tool>pytest, pytest-asyncio</Tool>
                    <Detail>测试覆盖率目标 >= 80%，测试文件 test_*.py 放在 tests/, tests/unit/, tests/integration/ 目录。</Detail>
                    <Detail>Fixture 最佳实践，显式声明 @pytest.fixture scope 以优化集成测试性能。</Detail>
                </Convention>
            </Section>

            <Section name="异步与时区">
                <Convention id="1.3.6">
                    <Title>异步编程</Title>
                    <Detail>I/O 密集操作必须使用 async/await。阻塞调用使用 asyncio.to_thread 包装。</Detail>
                </Convention>
                <Convention id="1.3.7">
                    <Title>时区处理</Title>
                    <Tool>datetime.timezone</Tool>
                    <Detail>必须使用 UTC</Detail>
                    <Detail>必须使用 IANA 时区名称（如 Asia/Shanghai 或 UTC+8）进行本地化转换。</Detail>
                    <Detail>处理时间时必须导入 timezone，导入语句：from datetime import datetime, timezone。</Detail>
                </Convention>
            </Section>

            <Section name="数据库与迁移">
                <Convention id="1.3.8">
                    <Title>数据库连接</Title>
                    <Detail>生产环境必须使用连接池，避免连接泄漏和性能瓶颈。</Detail>
                </Convention>
                <Convention id="1.3.9">
                    <Title>ORM 与迁移工具</Title>
                    <Tool>SQLAlchemy + alembic | Tortoise ORM + aerich</Tool>
                    <Detail>SQLAlchemy 使用 alembic 管理 schema 变更，Tortoise ORM 使用 aerich。</Detail>
                </Convention>
                <Convention id="1.3.10">
                    <Title>数据库迁移命名</Title>
                    <Detail>migration message 必须清晰描述变更：序号_简要描述，例如 01_create_users_table, 02_add_avatar_column。</Detail>
                </Convention>
            </Section>

            <Section name="项目配置与构建">
                <Convention id="1.3.11">
                    <Title>统一项目配置</Title>
                    <Tool>pyproject.toml (PEP 518/621)</Tool>
                    <Detail>所有工具链配置（包括 ruff, uv 的配置、构建系统、项目元数据）必须统一集中在根目录的 `pyproject.toml` 文件中。</Detail>
                    <Detail>构建后端必须使用 setuptools，禁止使用 setup.py/setup.cfg。</Detail>
                    <Detail>项目元数据（名称、版本、作者等）应遵循 PEP 621 规范。</Detail>
                </Convention>
            </Section>
        </Category>

        <Category name="代码质量检查">
            <Section name="检查清单">
                <ChecklistItem id="1">模块文档字符串完整（功能、调用示例、技术依赖、元数据）</ChecklistItem>
                <ChecklistItem id="2">公共 API 包含完整 docstring（Args/Returns/Raises）</ChecklistItem>
                <ChecklistItem id="3">所有函数使用类型提示，通过 mypy --strict 检查</ChecklistItem>
                <ChecklistItem id="4">通过 ruff 格式化和 lint 检查</ChecklistItem>
                <ChecklistItem id="5">日志使用 loguru，无 print 语句</ChecklistItem>
                <ChecklistItem id="6">关键业务逻辑测试覆盖率 &gt; 80%</ChecklistItem>
                <ChecklistItem id="7">无硬编码敏感信息（使用 pydantic-settings）</ChecklistItem>
                <ChecklistItem id="8">
                    <Title>复杂度检查</Title>
                    <Detail>圈复杂度 (Cyclomatic Complexity) 必须低于阈值（推荐 ruff C901 默认值，Max=10）。</Detail>
                </ChecklistItem>
                <ChecklistItem id="9">pyproject.toml 完整性</ChecklistItem>
            </Section>
            <Section name="模块结构约束">
                <Rule id="1.4.1">
                    <Title>显式导出 (Public API)</Title>
                    <Detail>每个模块应明确定义 `__all__` 变量来控制外部可见的公共 API。未在 `__all__` 中声明的函数/类视为内部实现。</Detail>
                    <Detail>必须使用 `_` 前缀来标记内部函数、类或变量。</Detail>
                </Rule>
            </Section>
        </Category>
    </Module>
</EngineeringSpecification>
