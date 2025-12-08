---
title: AI Coding：从 Vibe Coding 到规范驱动开发
author: Alden
date: 2025-11-20 12:00:00 +0900
categories: [LLM Engineering, System Cognition]
tags: [Methodology, SDD, AI Coding]
description: 软件开发的未来不再是编写更多的代码，而是指导 AI 编写更好的代码。本文深入探讨从 Vibe Coding 到规范驱动开发 (SDD) 的范式演变。
pin: false
math: false
mermaid: false
image:
  path: https://mmbiz.qpic.cn/sz_mmbiz_jpg/pTwMsl1ZlMBL54hHqtibgDn4nk8qumNlS3jJ8YkLvZevj4KGHYfNWks8tkEMd3gUNiaXOsSxmic5ZwZSibgqppPdiaw/640
  alt: AI Coding Concept
---

> **核心观点**：软件开发的未来不再是编写更多的代码，而是指导 AI 编写更好的代码。
{: .prompt-tip }

## 一、 背景与认知：AI 的本质与边界

在深入讨论如何使用 AI 编程之前，我们需要先祛魅。我们需要理解手中的工具到底是什么，以及它的极限在哪里。

### 1.1 基础概念对齐

大语言模型（LLM）本质上并非一个“理解者”，而是一个超大规模的概率预测机。无论是 GPT-5、Claude 4.5 还是国产的 DeepSeek，它们的工作原理都是预测下一个 Token（字/词）出现的概率。

*   **Token**：这是 AI 计费和处理的最小单位，约等于 0.75 个英文单词或 0.5 个汉字。
*   **Context（上下文）**：这是 AI 的“短期记忆”。它能读懂多少代码取决于 Context Window（如 128k tokens）。一旦超出这个窗口，它就会“遗忘”之前的逻辑。
*   **Hallucination（幻觉）**：当 AI 缺乏相关知识或逻辑推导失败时，它会一本正经地胡说八道，比如编造一个不存在的 Java 库。

### 1.2 AI 生效的前提

AI 不是魔法，它有明确的智力边界。通常情况下，AI 能发挥神效需要满足两个前提：

1.  **我们的需求，还无法碰到 LLM 的上限**
    软件工程中 99% 的工作是“工程实现”而非“科学发明”。数据清洗、API 胶水层、CRUD、前端组件、常规并发处理——这些是 AI 的绝对统治区。反之，如果你正在从头推导一种全新的后量子加密算法，AI 不仅帮不上忙，甚至会通过幻觉误导你。

2.  **我们的需求 99% 是通用的，无需造轮子**
    由于 LLM 是基于概率的预测机，它需要“见过”类似的代码模式。如果你的需求在 GitHub 或 StackOverflow 上出现过类似变体，AI 就是专家。
    
    > **结论**：AI 擅长解决“已知的未知”（你没写过，但世界上有人写过）；它无法解决“未知的未知”（完全孤立的业务逻辑或物理世界的新问题）。
    {: .prompt-info }

### 1.3 开发者角色的转变

随着工具的进化，开发者的核心技能树正在发生剧烈的变迁：

*   **从“实现者”变为“决策者”**：传统模式是“思考逻辑 -> 查文档 -> 敲键盘 -> 调试”；AI 模式则是“定义意图 -> AI 生成 -> **审查逻辑** -> **验证测试**”。
*   **技能价值重估**：**语法记忆（Syntactical Recall）**大幅贬值，你不再需要背诵 `datetime` 的格式化字符串。相对地，**系统设计（System Design）**与**测试验证（Verification）**的能力大幅升值——你需要知道如何拼装模块，并具备一眼看出 AI 在胡说八道的能力。

## 二、 没有银弹：AI 解决了什么？

Fred Brooks 在《人月神话》中的预言依然生效：软件开发存在根本困难（Essential Complexity）和次要困难（Accidental Complexity）。

AI 极大地消除了**次要困难**：语法细节、API 调用、样板代码、繁琐配置文件的编写。这是技术实现带来的附加复杂性，AI 对此是降维打击。

但 AI 无法解决**根本困难**：对复杂业务概念的构思、对模糊需求的界定、对系统边界的划分。这是问题域固有的复杂性。引入 AI 后，这对人的要求反而更高了——我们需要更清晰的问题定义能力。

### AI 的最佳场景：干脏活累活（Grunt Work）

不要试图让 AI 去卷算法创新，应该让它去处理那些我们讨厌的重复性工作：

1.  **逆向文档生成**：扔给 AI 一堆祖传代码，让它生成功能规格说明书（FDS）和数据库设计文档。
2.  **补充测试用例**：为 Service 层编写全覆盖的单元测试，包含边界条件和异常处理。
3.  **繁琐配置生成**：根据 Java 实体类，一键生成 SQL DDL、MyBatis XML 和前端 TypeScript 接口定义。
4.  **辅助 Code Review**：让 AI 扫描代码中的空指针风险或资源未关闭问题。

这能把资深开发从重复劳动中解放出来，去思考架构和业务。

## 三、 核心范式：从 Vibe Coding 到 SDD

随着 AI 编程的普及，我们的开发模式经历了从“直觉探索”到“工程落地”的演进。

### 3.1 起点：Vibe Coding（氛围编程）

这是一种目前非常流行的、以结果验证为核心的交互式开发模式。

*   **核心逻辑**：由人类提供意图（Intent），AI 黑盒执行（Execution），并在项目环境中验证边界（Boundary）。
*   **工作流**：抛弃逐行编写，直接下达指令 -> 观察运行结果 -> 感觉不对（Bad Vibe）则调整指令 -> 感觉跑通了（Good Vibe）则提交。

**Vibe Coding 的局限性**

虽然它极速启动，能带来心流体验，非常适合原型开发（Prototyping）。但它有“三大诅咒”，导致其无法构建生产级系统：

1.  **非确定性**：同样的 Prompt，下次生成的代码结构可能完全不同。
2.  **上下文遗忘**：项目一旦变大，AI 记不住之前的逻辑，开始胡乱修改已有功能（Regression）。
3.  **隐性债务**：为了快速获得“Good Vibe”，AI 可能会引入极其拙劣的实现方式，而在不做深度 Review 时很难发现。

> **原子化提交 (Atomic Commits)**
>
> AI 就像一个醉酒的高级工程师，随时可能写出惊艳代码，也随时可能**悄无声息地删除你昨晚的核心逻辑**。
>
> 在使用 Cursor、Windsurf 或 Copilot 时，请务必遵守：
> **每完成一个 Prompt（对话）并验证通过后，立即 Git Commit。**
>
> 把 Git 当作游戏的“存档点（Save Point）”。**绝对不要**在未提交的状态下连续进行多次大幅度的 AI 生成，否则一旦出现幻觉（Hallucination），将失去回滚的“救生索”。
{: .prompt-danger }

### 3.2 解法：SDD（规范驱动开发）

为了解决 Vibe Coding 的不可维护性，**Spec-Driven Development (SDD)** 应运而生。

*   **核心定义**：用形式化、详尽的文档（Spec）作为**唯一事实来源 (Single Source of Truth)**，驱动 AI 生成代码。
*   **思维转变**：在传统思维中，文档是代码的注释；而在 SDD 思维中，**文档 (Spec) 是源代码**，具体的代码 (Python/Java) 只是 Spec 经过 AI 编译后的产物。

**SDD 的价值**：
*   **锁定上下文**：Claude 3.5 或 Gemini 等模型能完美理解几十页的 Spec，保证逻辑一致性。
*   **前置质量把关**：修改文档的成本远低于重构代码。
*   **可协作**：Spec 是人类可读的显性知识，解决了“只有 AI 和上帝知道这代码怎么跑的”问题。

### 3.3 SDD 的标准流水线 (The Pipeline)

如何指挥 AI 干大活？标准的 SDD 流程如下：

1.  **Spec（定义规范）**：编写 Markdown。定义目标、API 接口、数据结构，以及最重要的**测试标准**（告诉 AI 如何才算“做完了”）。
2.  **Plan（生成计划）**：AI 根据 Spec 生成技术方案，例如：先建表 -> 再写 Service -> 最后写接口。
3.  **Tasks（拆解任务）**：将计划拆解为原子的、可执行的 Task 列表。
4.  **Implementation（执行与验证）**：AI 逐个 Task 执行代码编写，并自动运行测试用例，**测试通过即任务完成**。

---

## 四、 工具生态与落地实战

### 4.1 SDD 工具选型

*   **Spec Kit (GitHub 官方)**：提供了 `/specify` (想法转PRD)、`/plan` (PRD转计划)、`/tasks` (计划转任务) 的完整工具链。核心思想是“规范即通用语言”。
*   **BMAD-METHOD**：强调文档分片和多 Agent 协同（市场、产品、设计、开发 Agent 互相传递上下文）。
*   **OpenSpec**：专为 AI Coding 设计，支持草拟变更、审查对齐、任务实现的完整工作流。
*   **IDE 与 终端工具**：
    *   **Cursor/Windsurf**：目前体验最好的 AI 原生 IDE，擅长上下文理解。
    *   **Claude Code/Aider**：强大的命令行工具，支持长上下文和 Git 集成，甚至能自动化处理 CI/CD。

![AI Tools](https://mmbiz.qpic.cn/sz_mmbiz_png/pTwMsl1ZlMBL54hHqtibgDn4nk8qumNlSUAJyicuMTia5h1OcfTs6NJEozTVibvUGdsPOrHdzgkPFjldexiczroqA5A/640){: .shadow }

### 4.2 现实的引力：面对“遗留复杂度”

现实往往是骨感的。我们 90% 的工作是在维护 **Brownfield Projects（棕地项目/遗留系统）**。这些系统业务逻辑盘根错节，缺乏文档，且牵一发而动全身。

> **SDD 在老项目中的策略**
>
> **SDD 是一种光谱，而不是开关。** 不要试图对老系统进行全量 SDD，那是自寻死路。
> *   **读懂它**：选中一段晦涩的逻辑，问 AI：“这段代码在算什么？用自然语言解释给我听。”
> *   **小步重构**：让 AI 把 500 行的函数拆分成 3 个子函数，保持逻辑和变量名不变。
> *   **防御性编程**：让 AI 加强日志和 Try-Catch，确保出错时能看到现场。
{: .prompt-warning }

### 4.3 核心防线：业务逻辑与人的价值

AI 懂 Python 语法，但它不懂**“为什么周二的订单折扣是 8% 而不是 9%”**。业务逻辑包含大量未形成文档的隐性知识、历史妥协和人情世故。

正如在 [Vibe coding：LLM 时代的"没有银弹"回响](https://aldenwangexis.github.io/posts/Vibe-coding-LLM/) 中所深度剖析的，《人月神话》的预言在今天依然振聋发聩：

> **“必要的是构思概念上的结构，次要指它的实现过程。”**
>
> “没有银弹”不是悲观的宿命论，而是对本质问题的清醒认知。在任何复杂系统中，真正的挑战都在于概念结构的构思，而非实现技术的选择。
{: .prompt-info }

这就是**人的护城河**。

以前我们 80% 的时间在做 Translator（把业务意图翻译成代码），处理的是“次要困难”；现在 AI 负责 Translation，我们必须回归 **Architect** 和 **Product Owner** 的角色，去解决“本质困难”。

AI 无法取代人，因为 AI 无法维护系统的**概念完整性**，无法对结果负责，也无法理解业务深处的语境。
---

## 五、 总结与建议

### 给团队的实用建议

1.  **不要追求 100% SDD**：如果只是改个样式或修个空指针，直接用 Cursor `Cmd+K` 解决，写 Spec 是浪费时间。
2.  **文档即资产**：从**今天**开始，重要的新功能请尝试留下一个 Markdown 格式的 Spec。半年后维护这堆代码时，你会感谢今天的自己。
3.  **保持怀疑**：在复杂老项目中，Code Review 的标准要比以前更严，AI 极易产生引用不存在方法的幻觉。

### 结语

编程范式正在经历从 **Coding 1.0 (手写)** 到 **Coding 2.0 (Vibe Coding)** 再到 **Coding 3.0 (SDD)** 的演进。

不要焦虑。AI 是你的外骨骼，不是你的竞争对手。你的核心竞争力在于对业务的深刻理解、工程架构经验以及对 AI 产出的鉴赏力。

从明天开始，把那些不想写的单元测试、不想看的旧代码文档交给 AI。从“手搓代码”的工匠，进化为“指挥 AI”的架构师。

---

## 更多阅读

*   [GitHub Spec Kit](https://github.com/github/spec-kit) - Toolkit to help you get started with Spec-Driven Development
*   [OpenSpec](https://github.com/Fission-AI/OpenSpec) - Spec-driven development for AI coding assistants
*   [BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) - Breakthrough Method for Agile Ai Driven Development
*   [Anthropic Skills](https://github.com/anthropics/skills) - Public repository for Skills
*   [Context Engineering](https://github.com/davidkimai/Context-Engineering)
*   [How To Ask Questions The Smart Way](https://github.com/ryanhanwu/How-To-Ask-Questions-The-Smart-Way)