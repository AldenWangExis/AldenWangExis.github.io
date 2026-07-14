---
title: "一份让 GPT-5.6 Sol Ultra 挑战 50 年猜想的 Prompt，到底设计了什么？"
description: 拆解 OpenAI CDC prompt 的任务契约、路线组合、证据门禁、对抗审查与诚实退出，讨论复杂任务中的 LLM 驱动方式哪些值得借鉴，哪些不能直接搬进真实工程。
author: Alden
date: 2026-07-12 22:30:00 +0800
categories: [LLM Engineering, Agent]
tags: [Agent, LLM, AI Coding, Methodology, Evaluation]
pin: false
comments: true
---

7 月 11 日，Ethan Knight 在 [X 原贴](https://x.com/__eknight__/status/2075643583491965248)中称，OpenAI 新开放的 GPT-5.6 Sol Ultra 用 64 个 subagents，在不到一小时内生成了循环双覆盖猜想（Cycle Double Cover Conjecture）的证明，并公开了 [prompt](https://cdn.openai.com/pdf/04d1d1e4-bc75-476a-97cf-49055cd98d31/cdc_prompt.pdf) 和 [proof](https://cdn.openai.com/pdf/04d1d1e4-bc75-476a-97cf-49055cd98d31/cdc_proof.pdf)。

证明结果是否为真，在这里先放一边。数学证明最后要靠数学共同体、审稿和形式化检查，不靠一条 X。更值得拆的是 prompt 本身：它没有简单地催模型“给出证明”，而是在约束模型如何搜索、如何保留路线分歧、如何提交证据、如何接受反方检查。

这也让它看起来很矛盾。一方面，它确实给了一个高强度搜索流程；另一方面，它又要求模型假设完整证明存在，禁止回答问题仍 open，只允许返回完整 proof，要求至少 8 小时，最多 64 个并发 agent，还禁止搜索这个猜想是否仍是开放问题。放在能力展示或 benchmark 里，这些约束有一部分说得通，防泄漏、防拒答、防早停；搬到真实研究或工程任务里，就会压制事实校验和诚实失败。

这篇文章只看这层张力：这份公开 prompt 是否暗示了一种更适合复杂任务的 LLM 驱动方式，以及哪些部分不能直接照搬。

## 01 从答案请求到搜索流程：Prompt 开始规定模型怎么找答案

普通 prompt 关心的是一句话怎么写清楚：任务是什么，输入是什么，输出格式是什么，哪些限制不能破。这个层次当然有用，但它主要解决单轮执行问题。

CDC prompt 处理的是另一类问题：题目很难，反馈很少，搜索空间巨大，模型又很容易骗过自己。它要防的不是普通跑偏，而是这些更隐蔽的失败：

- 把特例证明当成完整证明；
- 把归约当成解决；
- 把一个和原问题同等难度的 lemma 包装成“小缺口”；
- 因为某条路线看起来漂亮，就让所有 agent 都围着它转；
- 把“routine”当成已经证明；
- 在没有事实校验的时候强行闭环。

所以这份 prompt 在做的事，已经不只是描述需求。它在组织搜索，分配注意力，设置证据门槛，安排反方审查，还规定什么时候不能停。

这个变化并不神秘。复杂任务里，提示词不只是“告诉模型做什么”，还要规定模型用什么方式推进：先分路线，再登记缺口，再审查证据，最后才允许收敛。

## 02 第一道防线：完成标准必须包含 Not-done 清单

CDC prompt 开头先把问题定义钉死：有限无环无向多重图，允许平行边；bridge 怎么定义；cycle 是连通 2-正则子多重图；两条平行边可以构成长度为 2 的 cycle；cycle double cover 要求每条边恰好出现两次，按重数计；断开图允许；空图的 cover 是空集。

紧接着，它列出哪些东西不算解决：特殊图类证明不算，覆盖次数不是 exactly two 不算，固定规模计算验证不算，归约到另一个未证明猜想不算，候选反例没有完整证书也不算。

这部分很工程。

很多复杂任务都有 done definition，却没有 not-done definition。大家知道大概要解决什么，但没写清哪些相邻结果不能交付。于是 bug 排查里只把报错压下去了，根因没找到；架构设计里只有组件图，没有迁移、回滚和失败态；PRD 里补了几个用户故事，权限、异常和数据口径都留给研发猜；代码审查只看风格和测试绿不绿，旧数据、并发和兼容性没人碰；research spike 做了 demo，核心风险没测。

“什么不算完成”是复杂任务的第一道防伪门。它听起来很土，但很管用。

工程里可以直接这么写：

```plaintext
目标：
  ...

完成必须满足：
  ...

以下不算完成：
  - 只覆盖 happy path
  - 只通过 mock
  - 只修 symptom
  - 只做 demo
  - 只把复杂度转移给另一个未验证模块
  - 只给出无法复现的口头判断
```
{: .nolineno }

这类清单不用漂亮。它的价值是让人和模型都没法把“差不多”塞进完成态。

## 03 多 Agent 搜索：64 个并发不重要，路线登记更重要

CDC prompt 要求一开始保留多种证明路线：代数观点、结构归纳、分解、流、嵌入、极值、计算 sanity check 等。它还要求不要过早把当前 favored approach 告诉大多数 agent，避免所有 agent 追随同一个看起来漂亮的 reduction。

这针对的是复杂搜索里的早熟收敛。

排查复杂 bug 时，危险往往不在缺少假设，而在某个假设太早变成“主线”。所有日志都被拿来解释它，所有反例都被当成噪声。架构评审也类似，一个方案因为图画得漂亮、术语用得新，很快占据讨论中心，其他更朴素但更可靠的路线被挤掉。

64 个 agent 很抓眼，approach registry 更值得看。它要求按数学想法给路线分组，而不是按措辞分组。如果多个 agent 都在做同一类 reduction，就把一部分重定向到欠探索方向。路线卡在等价强度的 missing lemma 上，就标记 blocked；只有出现新的机制、新 invariant 或新 construction，才值得重开。

这件事搬到工程里，可以变成一个路线登记表：

```plaintext
Route:
  核心假设：
  正在解释的问题：
  已有证据：
  反证或异常：
  当前缺口：
  状态：active / blocked / retired / certified
  重开条件：
```
{: .nolineno }

复杂 bug 可以用它管理根因假设。架构设计可以用它管理备选方案。research spike 可以用它管理技术路线。agent workflow 可以用它管理不同角色和搜索策略。

路线多不等于质量高。没有 registry，多样性会变成噪声；没有证据要求，registry 会变成项目管理表格。

## 04 证据门禁：状态报告不能进入完成判定

CDC prompt 要求 agent 返回 concrete lemmas、constructions、equations 或 counterexamples，拒绝 status reports、vague optimism，也拒绝把没证明的 global compatibility statement 说成 routine。

这条对工程任务很要命。

很多复杂任务卡住，通常不是没人做事；问题出在进展描述替代了证据。比如：

- “看起来快定位到了”；
- “基本就是这个原因”；
- “这个兼容性应该 routine”；
- “方案整体没问题，细节后面补”；
- “测试主要路径都过了”。

这些话不一定错，但不能进入完成判定。bug 排查要复现脚本、日志链路、最小失败样本、回归测试；架构设计要约束、取舍、故障推演、迁移路径；代码审查要具体文件、调用链、边界输入、失败场景；research spike 要实验方法、样例代码、benchmark、限制和决策建议。

CDC prompt 还提醒了一个高频陷阱：漂亮 reduction 不等于解决。数学里，把原问题归约到一个同等强度的 lemma，不算接近完成。工程里，把复杂度转移到平台层、配置中心、运营流程、后续模块，也不算解决。

这类任务可以加一个 obligation ledger：

```plaintext
Obligation:
  这个义务由哪个方案或抽象引入：
  谁负责承担：
  通过什么证据 discharge：
  是否只是把问题转移给另一个模块：
  如果不满足，会在哪些场景失败：
```
{: .nolineno }

这比“方案是否合理”更难糊弄。一个方案只要引入了新义务，就必须说清楚谁来承担，靠什么证明它已经被处理。

## 05 对抗审查：Verifier Agent 必须能阻断 Final Answer

CDC prompt 要求 adversarial agents 一直参与，每个候选证明都要检查 exact-two multiplicity、closed trail 冒充 cycle、平行边 2-cycle、断开图、割点、归约是否引入 bridge、是否循环使用等价 CDC statement。

这不是“再仔细检查一下”。它把审查角色单独拎出来，还把审查项绑定到已知失败模式。

工程里的 adversarial review 也该这么做。开会时问一句“大家有没有意见”不够，需要给反方明确任务：

- bug 修复：攻击根因假设，确认补丁不是 mask；
- 架构方案：攻击容量、故障恢复、数据一致性和迁移路径；
- PRD：攻击异常路径、权限边界、状态流和指标口径；
- 代码审查：攻击旧数据、旧客户端、并发、权限和 silent failure；
- agent workflow：攻击上下文污染、群体趋同、幻觉传播和无主决策。

更关键的是，反方要能阻断最终结论。否则审查很容易变成背书仪式：大家找几个小问题，修完以后方案看起来更稳，但核心风险没有被碰过。

如果审查发现 P0 问题，最终 claim 就不能发。很多 agent workflow 没做到这一点。它们让 verifier agent 总结风险，却没有让 verifier agent 拦住 final answer。

## 06 Benchmark 约束：防泄漏的写法，进生产会压制诚实失败

CDC prompt 里最危险的组合是：假设 proof exists，禁止回答 open，只允许返回完整 proof。

放在 benchmark 或能力展示里，这几条能解释。评测者可能想防止模型搜索答案，防止模型引用公开状态，防止模型一上来就说这是开放问题。但真实任务不能这么干。

真实工程需要事实校验。法律、API、产品规格、安全、财务、医疗、开源依赖、线上状态，这些都不能靠“别去查”来保持纯粹。真实研究也需要知道问题的公开状态，至少要标注“已验证”“未验证”“仍有争议”。

`Return only complete proof` 也不能原样迁移。它合理的一面是不要把半成品当 final；危险的一面是禁止失败报告。生产任务应该允许几种输出：

- certified complete，证据通过；
- partial but useful，有阶段性价值但不能当完成；
- blocked with exact gaps，明确卡点和下一步；
- failed with evidence，证明某路线不可行；
- needs human decision，需要人裁决范围、预算或风险。

`Spend at least 8 hours` 和 `Use up to 64 concurrent agents` 也只能当成 stress test 约束。真实工程要的是预算、checkpoint、trace 和产物，固定时长和固定并发数帮不上多少忙。没有 trace 的长时间推理，只是更长的叙事。

这里还有个小矛盾：X 上的说法是 64 个 subagents 不到一小时产出证明，prompt 原文却写着至少 8 小时后才考虑返回或放弃。这未必说明什么阴谋，但它提醒我们，这更像一个高强度 agentic search 的任务装置，不是生产协作手册。

还有一点要单独说：多 agent 共识离独立验证还很远。如果这些 agent 来自同一个模型、同一套系统提示、同一个目标压力，它们可能只是共享偏差的重复采样。真正的验证要引入工具、测试、形式化检查、人工复核或真实数据。

## 07 工程落地：问题契约、路线组合、证据门禁、诚实退出

不用把 CDC prompt 变成一个庞大的模板。复杂任务里引入五个轻量构件就够了。

问题契约，写清目标、边界、完成标准和非完成清单。复杂任务开始前，先把“哪些东西不能交付”写出来。

路线组合，保留几条实质不同的假设或方案，不让第一个漂亮解释占据全部注意力。路线要按机制分组，不按措辞分组。

证据门禁，状态报告不能算进展。每个 claim 都要绑定 artifact，比如复现、日志、测试、benchmark、设计约束、失败样本或审查记录。

反方审查，给审查者具体检查项和阻断权。不要让反方只做评论员。

诚实退出，明确什么时候可以说“没有完成”。高可靠系统必须允许模型和团队报告 gap、blocker、风险和未验证部分。

如果一定要压成一个小框架，可以叫 EPIC：Epistemic Portfolio with Independent Challenge，独立挑战式认知组合。

```plaintext
Problem Contract:
  目标、范围、边界、完成标准、非完成清单

Route Portfolio:
  路线族、核心假设、证据、缺口、状态、重开条件

Evidence Gate:
  接受哪些 artifact，拒绝哪些状态报告

Challenge Layer:
  反方检查项、阻断级风险、残余风险

Honest Exit:
  认证成功、精确阻塞、失败证据、人类决策点
```
{: .nolineno }

它适合复杂 bug、架构设计、技术方案评审、PRD 澄清、代码审查、research spike、agent workflow 设计和长周期项目管理。小改动、标准流程、低风险执行任务，用它会显得笨重。

判断要不要上这套东西，可以看三个问题：

- 这个任务是不是容易出现伪完成？
- 有没有多条相互竞争的解释或方案？
- 错误结论的代价是否明显高于多做一轮审查的成本？

如果答案都是 yes，就值得上。否则普通任务说明和测试就够了。

## 08 Prompt 只是入口：复杂任务要靠搜索、审计和退出条件驱动

这份 prompt 对资深工程师有用的地方，不在“写得详细”“用了多智能体”“要求严格”这些表层技巧，而在它把一个难题拆成了可运行的搜索流程。

到 2026 年，再把这类东西简单归到 prompt engineering 下面已经有点粗糙了。复杂任务需要 harness、上下文、工具、子任务、审查和循环。prompt 只是入口，但它仍然会决定这套系统怎么运转。

从这份 CDC prompt 里，能拆出五个朴素但很硬的设计原则。

1. 复杂任务的核心风险不是“模型不知道”，而是“模型以为自己知道”。因此 prompt 不能只鼓励生成，还必须设计审计、反例、证据和失败出口。

2. 搜索空间管理比单链推理更重要。极难问题通常不是一条 chain-of-thought 能解决的，而是需要路线组合、路线登记、路线淘汰、路线重开和延迟共识。

3. 完成标准必须包含非完成标准。很多工程失败都不是因为没有 done definition，而是因为没有 not-done definition。只要没有明确写出“不算完成”，人和模型都会把相邻成果包装成完成。

4. 对抗审查不能只是“再检查一下”。它要有检查表、独立性和否决权，能在发现硬伤时阻断 final。

5. 诚实失败是高可靠系统的一部分。CDC prompt 最大的危险正在这里：它构造了强大的搜索治理，却削弱了诚实退出。真实工程不能这样。一个成熟的 agent workflow 必须允许模型明确输出：没有证明，没有定位根因，证据不足，只完成了哪些义务，剩下的 gap 是什么。

资深工程师该带走的，不是一套可以复制的 prompt 格式，而是一种驱动复杂任务的结构：目标要钉住，路线要并行，证据要可查，反方要能阻断，失败要能说清楚。

好的流程不会强迫模型永远成功。它会让成功更可信，也让失败更早、更清楚、更便宜地暴露。

## 参考材料

- Ethan Knight 的 X 原贴：[查看原贴](https://x.com/__eknight__/status/2075643583491965248)
- OpenAI 公开的 prompt 全文：[cdc_prompt.pdf](https://cdn.openai.com/pdf/04d1d1e4-bc75-476a-97cf-49055cd98d31/cdc_prompt.pdf)
- OpenAI 公开的 proof 文本：[cdc_proof.pdf](https://cdn.openai.com/pdf/04d1d1e4-bc75-476a-97cf-49055cd98d31/cdc_proof.pdf)
- Lean 形式化仓库：[openai/cdc-lean](https://github.com/openai/cdc-lean)
