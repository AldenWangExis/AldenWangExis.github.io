---
title: 系统评测 Agent Skill 的工程起点
description: 从触发、运行证据、确定性检查到发布前比较，建立一套能解释回归的 Agent Skill 评测实践。
author: Alden
date: 2026-07-28 18:38:00 +0800
categories: [LLM Engineering]
tags: [Agent, Evaluation, LLM, Best Practice]
image:
  path: /assets/img/posts/skill-eval-systematically/skill-eval-01.jpg
  alt: Agent Skill 评测主题封面
media_subpath: /assets/img/posts/skill-eval-systematically
mermaid: true
comments: true
---

改完一版 Skill，最常听到的反馈是“这次感觉顺了”。这句话很难进入工程决策。它没有告诉我们 Skill 有没有被正确发现，是否读到了必要资料，是否按约定执行了命令，也没有告诉我们下一次改 description 时会不会把旧问题带回来。

OpenAI 的《Testing Agent Skills Systematically with Evals》给出了一条很适合起步的路线。先把成功写成可检查的条件，再用少量 prompt 把边界钉住，保存每次运行的证据，最后让真实失败留下可重复的测试。它不要求团队先搭一套评测平台，也不承诺一组分数可以解释全部问题。

![Agent Skill 评测主题封面](skill-eval-01.jpg)

这篇文章把演示中的二十页内容整理成一个可落地的技术实践。文中的过程、字段和示例来自随文讲稿与演示，并以 OpenAI 和 Anthropic 的原始资料为准。后半部分会专门说明，这套回归检查能够支持哪些结论，哪些结论仍需要对照实验。

![Skill 的目录结构与渐进式加载](skill-eval-02.jpg)

## 先把被测对象说清楚

Skill 通常不是一段孤立的提示词。Anthropic 对它的描述更接近一个按需加载的能力目录。metadata 负责让 Agent 发现它，`SKILL.md` 说明任务边界和步骤，references、resources、scripts 提供后续资料与确定性动作。运行时还会留下工具事件、文件产物和外部状态。

这决定了评测不能只读最终回答。一个答案看起来正确，可能来自模型临时补全，或者来自错误的 Skill 被调用后碰巧成功。对于会写文件、执行命令或访问外部系统的 Skill，这种偶然成功尤其危险。评测需要保留它何时被发现、读了什么、做了什么以及留下什么结果。

![Skill Eval 与 Agent Eval 的观察范围](skill-eval-03.jpg)

Agent Eval 和 Skill Eval 因此承担不同的问题。前者看用户任务是否完成、多个能力是否配合、安全约束是否成立。后者把镜头放到一个版本化 Skill 在特定环境中的行为，重点检查触发、步骤、工具、产物和副作用。两类评测应该互相接住。

一次端到端失败可以先定位到路由、Skill 执行、结果消费或编排中的某个位置。确认属于 Skill 后，把这个场景写入回归集。修复完成后，再回到端到端任务复验。这样既能找到局部变化的原因，也不会把局部通过误当成系统已经稳定。

![八步评测的依赖顺序](skill-eval-04.jpg)

## 从成功标准开始

真正有用的第一步很朴素。先写下必须通过的条件，再写 Skill。条件最好落在四类可观察的事情上。

- **结果** 任务是否完成，例如服务能否启动、目标文件是否生成
- **过程** 必需动作是否发生，例如依赖安装是否真的执行
- **风格** 产物是否符合项目约定，例如组件组织或样式策略
- **效率** 是否出现无意义的反复命令或异常的 token 消耗

这几类条件会决定之后要收集什么证据。文件和进程状态适合检查结果，运行记录适合检查过程，代码结构更适合交给 rubric，事件数和用量记录可以用于观察效率。只有“代码要优雅”一类描述时，后面的评分很难有稳定依据。

![从成功标准到初始回归集](skill-eval-05.jpg)

![四类成功标准](skill-eval-06.jpg)

演示里的 `setup-demo-app` 用例把约束写得足够具体。它明确技术栈、文件结构、执行顺序和完成条件，例如项目可启动、`package.json` 存在、`Header.tsx` 与 `Card.tsx` 已创建。这样的要求让检查者能看到要找什么，也让 Skill 作者能发现自己写得过于含糊的地方。

![可评测 Skill 的工作示例](skill-eval-07.jpg)

## 先手动跑，专门找默认前提

批量执行之前，先在真实仓库或临时目录显式触发一次。这个阶段要收集一串容易被文档省略的前提，分数可以稍后再看。

触发前提包括相邻请求会不会误触发，例如“给现有 app 加 Tailwind”不该等同于“创建一个新 demo app”。环境前提包括目录是否为空、包管理器是否存在、网络与权限是否可用。执行前提包括项目是否创建后才改配置、依赖是否在需要时安装。

![手动触发用来发现隐藏前提](skill-eval-08.jpg)

每发现并修复一个真实问题，就把它改写成一个简短、可重复的 case。开始时准备十到二十条 prompt 已足够用于早期回归，但这个数量不是泛化能力的证明。用例至少应覆盖显式调用、隐式召回、带上下文的表达和明确的负例。

```csv
id,should_trigger,prompt
explicit-create,true,用 setup-demo-app 创建一个 React 演示项目
implicit-create,true,创建一个带 TypeScript 和 Tailwind 的小型前端演示
contextual-create,true,为 API 原型做一个可运行的前端页面
existing-app-style,false,给已有项目补一套 Tailwind 样式
```

这里的负例很有价值。没有它，Skill 可能在所有正例上都表现良好，却在真实对话中频繁抢走不该属于它的任务。新出现的漏触发、误触发和产物漂移，都应该成为新的 case。数据集会跟着 Skill 的真实使用逐步长出来。

![四类 prompt 用例](skill-eval-09.jpg)

## 把一次运行变成可以查的证据

当 prompt 集稳定下来，下一步是保存每次运行，而非只保留最后回复。OpenAI 的示例使用 `codex exec --json` 输出 JSONL。命令执行、事件顺序、完成状态和最终消息都能进入 trace，生成的文件则和 trace 一起保存。

![从运行到评分的证据路径](skill-eval-10.jpg)

一个最小 runner 可以只做四件事。

1. 对每条 prompt 启动一次运行
2. 将标准输出保存为该 case 的 JSONL trace
3. 解析关键事件及其顺序
4. 把 trace、工作区产物和状态交给检查程序

这份记录的价值出现在失败时。`npm install` 没有发生，还是发生后失败了，目录中是否已出现 `package.json`，Agent 在哪一步停止，都可以回到证据中确认。团队不必根据一段最终回复重新猜过程。

![JSONL trace 的最小 runner](skill-eval-11.jpg)

## 规则先守住确定事实

第一批 grader 应尽量简单。存在性、退出码、事件类型和顺序都可以由程序直接判断。对 `setup-demo-app` 而言，可以先检查 `command_execution` 中有没有 `npm install`，再检查工作区里的 `package.json`，最后按需要补 build 或服务探测。

```json
{
  "ranNpmInstall": true,
  "hasPackageJson": true,
  "exitCode": 0
}
```

这些检查不需要显得聪明。它们失败时应该能直接指向 trace 或工作区中的一项事实。规则的可解释性会让修复速度更快，也能防止团队为了一个本可精确判断的问题过早引入模型评分。

![确定性检查守住命令、产物和状态](skill-eval-12.jpg)

## Rubric 处理实现方式

文件存在并不能说明实现符合约定。Tailwind 是否使用官方 Vite plugin，组件是否按团队约定组织，样式是否混入 CSS modules，这些问题需要阅读代码和配置。它们适合放在 rubric 中，由只读检查运行逐项给出证据和判断。

重点在于证据和 grader 的匹配。`package.json` 用文件系统检查即可。命令是否执行应该查 JSONL。配置和组件风格才需要 rubric。把所有问题都交给同一种评分方式，通常会损失可解释性。

![要求、证据与 grader 的对应关系](skill-eval-13.jpg)

生成与评分也应分开。第一轮可以创建项目并保留产物。第二轮只读取仓库，按 rubric 返回结构化结果。这样评分过程不会顺手改动被测项目，后续汇总和版本比较也能依赖稳定字段。

```json
{
  "overall_pass": true,
  "score": 92,
  "checks": [
    {"id": "tailwind", "pass": true, "notes": "官方插件已配置"}
  ]
}
```

`output schema` 只保证结果可解析。它不会自动校准评分标准。对于会阻断发布的高影响 rubric，仍应准备金标样本、盲化比较、低置信度处理和人工复核。

![只读 rubric 与结构化输出](skill-eval-14.jpg)

## 成熟后再增加更重的检查

快速检查适合跟着日常改动运行。build、runtime、权限、工作区清洁度和成本检查则应依据风险加入。服务确实能启动才需要 runtime smoke，涉及写入和自动执行时才应把权限记录列入检查重点。

每新增一项检查前，可以先问一个具体问题。它在防哪种已经见过或高度可能出现的失败。如果答案不清楚，先保留较小的回归集和可解释的规则，通常更有利于日常迭代。

![按风险选择扩展检查](skill-eval-15.jpg)

真实失败带来的价值，在于它能把抽象担忧改写成一个能复现的 case。打开 trace，确认失败位置，修复 Skill，补一条用例，再重跑受影响的集合。这种节奏会让测试集越来越接近真实任务，而不是一直重复同一批最初的 happy path。

![将真实失败写回回归集](skill-eval-16.jpg)

![从本地检查到 CI 的执行节奏](skill-eval-17.jpg)

## 回归通过能说明什么

这一点需要收得很紧。Skill 的局部回归通过，只能证明它在给定模型、工具、环境与用例下，经过的检查没有发现退化。它可以帮助解释一次修改影响了什么，却不能自动证明新版本有普遍增益。

若要比较版本价值，需要在相同 case 和 fixture 下运行 old、new，并按问题加入 no-skill 或等信息量的强提示基线。模型、工具版本、环境、判定器和用例都应记录下来。存在随机性时要重复运行，报告每条 case 的差异，不要将两批不同任务的总分直接相减。

同样地，Skill Eval 的局部通过也不代表端到端 Agent 已经稳定。路由、编排、结果消费和最终业务动作仍需回到完整任务中验证。局部评测与端到端评测各自回答一部分问题，不能互相替代。

![回归检查与增益主张之间的证据边界](skill-eval-18.jpg)

## 下周就能开始的最小实践

选择一个正在修改、任务边界又相对明确的 Skill。先写四到八条必须通过的条件。手动跑一遍，将触发、环境和执行中的默认前提整理成十到二十条 prompt。之后保存 JSONL，用规则检查确定事实，再给需要语义判断的部分建立只读 rubric。

这样做以后，每次修改至少可以回答两个问题。哪条用例变了，证据在哪里。把这次变化放回真实 Agent 任务后，用户结果是否仍然成立。前一个问题帮助定位修改，后一个问题保护最终交付。

![从一个 Skill 开始的实践清单](skill-eval-19.jpg)

![演示的参考资料页](skill-eval-20.jpg)

## 参考资料

- [OpenAI Testing Agent Skills Systematically with Evals](https://developers.openai.com/blog/eval-skills)
- [Anthropic Equipping agents for the real world with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- [Anthropic Introducing Agent Skills](https://www.anthropic.com/news/skills)
