---
title: 来自微软的自进化 SkillOpt 深度解读与反思：自进化 Agent 技能的“反向传播”
description: 从整体 Self-Evo 视角看，Skills、Harness 与 Model 三者同时受到人类先验知识、工程验证指标、模型执行反馈等多重优化机制影响。当前阶段，Skill 或许会率先成为突破 Model 与 Harness 交互的“界面层”候选。
author: Alden
date: 2026-05-28 19:32:00 +0800
categories: [LLM Engineering, Agent]
tags: [Agent, LLM, AI Coding, Methodology, Evaluation]
image:
  path: https://mmbiz.qpic.cn/sz_mmbiz_jpg/Jric6EjH3918rj7CUgFVOyokLiacWalemlroHsQHQRx3DlJSiaBNZRqatathbRhibohkbtmcSBOL8a1H2kKgbCuBQ2TmibTAmIyHr6ZkuYGH7gdQ/0?wx_fmt=jpeg
  alt: SkillOpt 自进化 Agent 技能文章题图
pin: false
comments: true
---

> 来源链接：[塔罗烩《来自微软的自进化 SkillOpt 深度解读与反思：自进化 Agent 技能的“反向传播”》](https://mp.weixin.qq.com/s/s__fdyXQG932SavQeeugcw)  
> 原作者：吕明  
> 发布时间：2026 年 5 月 28 日 19:32
{: .prompt-info }

在阅读这篇文章笔记前，推荐小伙伴们回顾阅读一下我之前写的一篇关于Harness体系的技术思考文章《[从AutoHarness到Heuristic Learning，探析未来Model与Harness间隐含的关系演进与统一视角下的新研究方向](https://mp.weixin.qq.com/s?__biz=MzkxOTY2MjE3Nw==&mid=2247488892&idx=1&sn=4282e1347c79f334fb3903f8fddb79c5&scene=21#wechat_redirect)》，其中对Model与Harness的关系演进有比较系统的讨论，也许会为今天的主题内容提供一些有益的视角补充。

接下来跟大家分享这篇「来自微软的自进化SkillOpt深度解读与反思：自进化Agent技能的“反向传播”，从文本空间优化到Harness体系的工程化Continued Evolve」

全文约 1.2 万字。

## 引子：当“Skill 文件”拥有了自己的“反向传播”

最近几个月，各类Agent或Harness框架生态体系中比较热闹且高度受到关注的方向之一，无疑是“Self-Evolution”。从早期Google DeepMind AlphaEvolve提出的原始自进化思想到Karpathy所尝试的Auto Research这种更贴合裸模型自求解模式，从Claude官方的Skill-Creator，到开源社区涌现的各类Self-Evolve工具：包括EvoSkill、SkillClaw、AutoSkill、XSKILL、Memento-Skills、EvolveR等进化流，MetaClaw的持续元学习框架，再到CODESKILL技能维护策略，大家都困惑于一系列问题：Self-Evo到底在长推理任务中进化的是什么？为什么能work？哪种进化模式是最优、可控、可预测且经济的？Self-Evo是否需要在工程上进一步去约束或规范？以及进化后的Agent能为当下和未来带来什么？...

但坦率说，持续观察并实践了一圈下来，总感觉哪里差了些什么，这些方法要么依赖固定的提示词模板和启发式更新规则，要么将自进化等同于松散的自我修订（Self-Revision），要么回归于依赖强大的裸模型进化式原始求解，没有一个类似像DNN学习范式或LLMs scaling law那样类似的理论可观测通道，或SWE领域的benchmark去约束控制指引，如DL反馈信号下可靠且可复现地改进其起点..模模糊糊的..

直到几天前读到微软团队的这篇SkillOpt论文，促使我重新进行了一些阶段性的反思..

![图片](https://mmbiz.qpic.cn/mmbiz_jpg/Jric6EjH3919dDibFAPmIPB2rDFDZU7dmBgbnAzm0q5QuwHpC1icgYWjWkBVJiaOgujZ9zlHQ2Bul9tCMug5Hc0Z04CjLiboPVkTBbdS61NrwhA8/640?wx_fmt=jpeg#imgIndex=0)

说实话，看到摘要里那句“We argue the skill should instead be trained as the external state of a frozen agent, with the same discipline that makes weight-space optimization reproducible”时，有一种“这层窗户纸就要被捅破了”的感觉。（当然还有更多路径去探析未来Self-Evo下的很多有意思的点，回头有机会跟大家逐个讨论）

SkillOpt做的事情，本质上很简单且另辟蹊径，但细想感觉也许为未来Self-Evo发生在Skills或Harness乃至Model上带来深刻的意义与洞察。简单的说，它类似给Agent的Skill文件设计了一个“文本符号化空间的梯度下降optimizer” ，就像DL中优化器在权重空间中对参数进行梯度更新，SkillOpt在文本空间中对技能文档施加结构化的编辑操作（增加/删除/替换），严格基于验证集分数的提升来决定是否接受每次编辑。

![图片](https://mmbiz.qpic.cn/mmbiz_jpg/Jric6EjH391ib2XosgQiaJbbyEfukKrh0lW72vkgf2pvgavcZH4ckmcU6ps7iaAwmjGgNdYPs3Hvg1N1jjMQRgoiclak4VUK7wjFvZcS3HLSHrIY/640?wx_fmt=jpeg#imgIndex=1)

这看似是一个比喻，但也许这背后也隐含了底层方法论层面的深层内涵。

在接下来跟大家针对SkillOpt展开具体技术细节与内涵洞察讨论之前，我想先带着大家先稍微停下来，做一点提前的看似不是那么成熟的思辨，也请大家轻拍：

## 一、表层同构与深层分野：文本符号空间优化与参数空间梯度下降的内涵差异

坦率说，在看到SkillOpt架构到早期类似提示词优化、Skills进化或者早期类似文本梯度（Textual Gradient）的思想，脑海里会自然直观地浮现出这个类比直觉：即对离散的符号文本做梯度下降迭代更新，但细想背后的内涵与不同呢？

### 1.1 表层同构：一个看似优雅的类比框架

不可否认，在抽象“表层方法论”层面，二者的确存在一定的同构性：

![图片](https://mmbiz.qpic.cn/sz_mmbiz_jpg/Jric6EjH3918vO4TcKuoWTHrQib1XqHEtMIvgEpiby4tuc8CZayy0nHiaOc721yHSib5672skfCySaiaUMyicqPvB6fLNdKzOFjJYFtcJfdb3j9cbU/640?wx_fmt=jpeg#imgIndex=2)

这种类比并非SkillOpt独创，早先的TextGrad（曾被SkillOpt作为基线对比）等“文本梯度”方法就已经试图将梯度下降的理念迁移到提示词或文本优化中。在《Symbolic learning enables self-evolving agents》这篇工作更是明确提出“模仿连接主义学习中的反向传播和梯度下降”来进行智能体的符号化自优化。

但仅作为将SkillOpt不过是又一轮“文本梯度”的包装后又没有后续，感觉又不是那么的确切和完备↓

### 1.2 深层本质上的分野：连续与离散空间的不同动力学演进与迭代模式

这种深层分野在于：连续空间的梯度下降，与离散文本空间的符号化优化，在底层的“优化动力学”上存在本质的不同。

#### （1）梯度本质：一阶局部方向 vs. 语义全局推理

在DNN参数空间中，gradient具备清晰明确的操作性定义：loss function在当前参数取值处的一阶导数即偏微分向量，严格指向loss增长“最快”的局部方向，权重参数的更新沿着其负方向行走便可保证loss的下降。它依赖于两个核心前提：参数的连续性（允许无限小的微扰）和loss function（如MSE、Cross-Entropy等）的可微性（允许计算解析梯度）。

而在文本符号空间的Skill优化中，SkillOpt面临的是一个完全不同的局面。Skill文档由离散的Token序列构成，编辑操作天然就是离散跳变的，即无法像调整一个浮点权重那样在“多一步上下文过滤”和“少一步上下文过滤”之间做连续插值。因此所谓的“Textual Gradient·文本梯度”对rollout失败原因的分析文本，本质上是一种基于优化器模型（一个frozen的frontier model）对任务执行语义的全局推理和理解，而非基于局部一阶近似的梯度信标。可以简单理解为它不是基于当前Skill的局部微扰，而是对“Agent在当前Skill指引下发生了什么”的完整因果分析。

用我曾经在谈论CoT底层机制时的一个思路来类比：如果说连续梯度下降是在隐状态空间中沿着曲面上最陡峭方向做局部探索，那SkillOpt的文本优化则更像是外部优化器模型对“当前Skill引导下的Agent行为模式”进行全局因果推理，然后给出“在符号层面应该如何调整指令”的决策。前者是局部的、连续的、基于微分的；后者是全局的、离散的、基于语言理解与显式因果链路的。

#### （2）验证机制：梯度链的解析严谨性 vs. 经验性”hold-out”验证

在参数空间梯度下降中，BP算法提供了一套数学上严密的链式法则，确保梯度信号能够从输出端逐层传递到网络的每个可训练参数。梯度下降更新方向与梯度信号之间的关联是解析的、确定的，即使由于非凸优化存在陷入局部最优的可能，但每一次参数更新确实是沿着梯度所定义的方向进行的。

而在SkillOpt中，优化器模型基于rollout分析生成的编辑建议，与最终的验证集分数提升之间，不存在类似的解析保证。或者说SkillOpt采用了一种更为“经验主义”的方法：编辑必须经过独立验证集的严格测试，只有真正提升了验证分数的编辑才会被接受。这种“提议-验证-接受/拒绝”的闭环，更像是一种基于黑箱评估的试错-筛选过程（生成式探索与验证式经验主义的结合），而非基于连续信号梯度链的解析驱动过程。

在参数空间DL中，梯度链是确定的、解析的；而在文本空间中，编辑的因果效果也许是非确定的、不稳定的且从优化器模型的生成结果来看是一种统计性的。因此，基于编辑提议的验证筛选结果，它离真正在离散文本空间中构建出一套解析或严格确定性的优化路径还是有着本质的不同的。

#### （3）语义空间结构：向量空间度量 vs. 语义拓扑度量

这里有一个更深刻但容易被忽视的不同：连续参数空间具备天然的连续化度量特性（如欧氏距离、余弦相似度），而离散文本空间缺乏这样的简单直观统一度量。

在参数空间中，两个权重向量之间的“距离”可以通过标准的向量空间度量来精确定义，梯度更新的大小和方向在参数空间中具有清晰可解释的几何意义；但是在文本空间中，Skill文档的两个版本之间的“距离”是什么？是编辑的Token数量？是编辑操作的次数？还是语义上的漂移程度？语义距离如何符号化量化？...等等这些问题可能现阶段不太容易得到一个好的答案。

所以，我们看到SkillOpt规避了这一难题，它将编辑操作限定为增/删/改三种有限形态，并通过类比深度学习中的“Learning Rate（η）” 为“文本学习率预算”来控制每轮编辑的Token变更量，以一种类似Trust Region的方法在不具备度量结构的文本空间中实现对演化步长的约束。但这更像是一种实用的工程约束，而非对文本空间度量结构问题的解析求解。

### 1.3 小结一下：从”类比”走向”启示”

因此，我更愿意将SkillOpt与梯度下降之间的关系定位为“启示性的类比”而非“结构性的同构” 。SkillOpt从梯度下降中汲取了方法论精神：迭代、基于信号、验证驱动、稳定可控，但在具体实现上，它面对的是一个完全不同质地的优化空间与策略方法。

这种不同，恰恰为自进化Agent体系打开了全新的想象力空间。正因为文本空间不具备连续空间的分析性质（梯度、链式法则、Hessian矩阵等），SkillOpt所采用的“优化器提议 + 验证集筛选”范式，实际上是一种利用LLM的语义推理能力来弥补离散空间缺乏解析梯度信号的优雅方案，甚至能带来某种全局上的优化方向。

更进一步，这也让我感受到这里透着两条非常迷人的哲学隐喻：不列颠经验主义（British Empiricism）vs. 大陆理性学派（Continental Rationalism）

在深度学习的参数空间优化中，模型参数化知识（权重矩阵）本身是在“流形分布空间”中被动地被Loss梯度拉扯、塑形，优化过程是解析约束下随机的、局部的、完全由真实经验数据信号驱动的。参数不知道自己“为何”被这样调整，它只是沿着负梯度方向滑落，是连续且内在的。

而在SkillOpt的文本空间优化中，优化器模型实际上是先于参数空间“理性”的理解Agent失败的原因、“演绎”的思考应该如何调整指令才能让Agent做得更好，优化过程是有意图的、全局演绎推理的、因果导向的，是由内到外驱动下所呈现的符号结构化的。

即前者是某种预设的经验主义物理动力学过程；后者是形式化的理性认知过程。

带着这层思辨，我们再来看SkillOpt的具体技术架构，或许会有更深的体会。

## 二、SkillOpt的方法论内核：文本空间的受控优化器

### 2.1 核心架构：冻结Agent + 独立Optimizer + 受控编辑机制

SkillOpt的整体架构可以概括为一个优雅的三层解耦设计：

![图片](https://mmbiz.qpic.cn/mmbiz_jpg/Jric6EjH3918db1ssQ1eCic9iaM2AkAeMSpDia2sBic0KsibVeKK6jCD4Vsd3WViaZlXnKxtDtgaqZRK7qM2C5dWNDpu9sNrTUuEzWOuv3N6GcyzdI/640?wx_fmt=jpeg#imgIndex=3)

- **冻结的Agent层**：整体Agent在Harness框架及模型层在优化过程中保持完全冻结，不做任何权重更新。Skill优化文档作为上下文注入给Agent，Agent在任务上执行并产生带评分的rollout轨迹。

- **独立的Optimizer层**：一个专门的优化器模型（通常是能力较强的frontier model）负责分析rollout中的成功和失败pattern，并基于分析提出对skill文档的结构化编辑建议。这里的编辑被限定为三种基本操作：增加（add）、删除（delete）和替换（replace），构成了一个离散且可控的编辑空间。

- **可验证的受控接受/拒绝机制**：编辑重写提议必须经过独立验证集的严格检验，只有当验证分数获得严格提升时，编辑才会被接受并合并到skill文档中。这种”保守主义”的接受策略，从根本上区别于此前那些”放手让模型自我修订”的松耦合方法。

![图片](https://mmbiz.qpic.cn/mmbiz_jpg/Jric6EjH391ibur2zS7MfeYibSLWrSDR6XzSVxmHPTHwgT3tIo3u9ibXUibibDrZdt63ibCvmoOicFiauVMuKNicy6qMDPEJv7TzDIBI54pRb8bQsKhibY/640?wx_fmt=jpeg#imgIndex=4)

这三层设计的巧妙之处在于：Agent负责框架执行（不变）、Optimizer负责分析/决策/优化（思考与决策）、验证集负责评判（接受/拒绝），形成了一个清晰的责任分离和信息闭环。

### 2.2 稳定性设计考量：文本学习率、拒绝缓冲区和元更新

SkillOpt最令我个人印象深刻的设计，是其对”优化稳定性”的精细考量，这种考量在传统的文本优化方法中是比较罕见的：

- **文本学习率预算（Textual Learning-Rate Budget）**：每一次优化的编辑Token数量被严格限制，类似于深度学习中学习率对参数更新步长的约束。

- **拒绝编辑缓冲区（Rejected-Edit Buffer）**：被验证集拒绝的编辑不会被简单地丢弃，而是被保留在缓冲区中，作为后续优化轮次的历史参考，防止优化器重复提出已经验证无效的编辑方向。

- **轮次级慢速/元更新机制（Epoch-wise Slow/Meta Update）**：优化不是连续持续的，而是在每个epoch结束时进行受控的聚合更新，类似于深度学习中的元学习或梯度累积策略。

这些设计综合来看，使得SkillOpt在训练阶段保持了类似深度学习的优化稳定性，而在部署阶段则实现了零额外推理开销，优化后的Skill文档就是一个纯文本文件，直接注入上下文即可。

不过上述这一系列“稳定性”设计考量是否能与DL中的梯度优化过程中的学习率、初始化、激活函数、残差架构、批归一化、梯度裁剪、优化器选择等有关稳定性因素等效类比还有待进一步探索及理论验证，毕竟在上一章节中我们看到其两种优化机制内涵的根本不同，不过我们可以初步从论文中的消融实验分析中一窥其表现：

![图片](https://mmbiz.qpic.cn/sz_mmbiz_jpg/Jric6EjH391icwoWen2orja3KLiaEAiaFXbrMF10BhoHnh17u6QdVNsZxHvADesvqiaYTu4J2ytEEGwgFgp07jnicU8WjbLibwSiaJxSSYT2pzoD1M0/640?wx_fmt=jpeg#imgIndex=5)

- **学习率限制的必要性**：取消单次编辑预算限制（Without lr，即无约束地重写技能）后，SpreadsheetBench的表现下降了1.8%，LiveMath表现下降了4.0%。这定量地证明了限制单次更新步长（学习率控制）能有效维护技能的语义连贯性，防止严重的更新振荡。

- **拒绝编辑缓冲区的作用**：移除拒绝缓冲区（Without rejected buffer）不向优化器反馈失败历史时，SpreadsheetBench的表现从77.5%跌落至 72.9%（下跌 4.6%）。这证明了保留负反馈信息能极大地辅助优化器规避无效编辑路径，提升优化效率。

- **慢速元更新的全局沉淀作用**：同时剥离慢速更新与元知识（Without meta skill and slow update）会导致SpreadsheetBench的成绩暴跌22.5个百分点。这充分证实了局部微小编辑容易陷入局部最优，跨周期的全局经验沉淀对于复杂工具链调用的智能体技能演化至关重要。

### 2.3 主实验验证结果

在实验结果上，SkillOpt展现了令人印象深刻的全面优势：（详细实验结果可参考原论文）

![图片](https://mmbiz.qpic.cn/mmbiz_jpg/Jric6EjH391ic1NtTZJq6uE9TFEVQO3zrECOcwh5UkGbYpM2BMlo2abbC7hHm0sLuriakSLicK2JNLLVPCYy64YOCFxEicNUW8wOhgzogvWZbrWM/640?wx_fmt=jpeg#imgIndex=6)

- **52个评估cell全部最佳或并列第一**：跨6个benchmark、7个目标模型、3种执行环境（直接对话、Codex、Claude Code）的全面测试中，SkillOpt在所有52个评估组合上都表现最佳或并列最佳。

- **显著的平均提升**：在GPT-5.5上，SkillOpt将无Skill的平均准确率在直接对话中提升了23.5个百分点，在Codex Agent循环内提升了24.8个百分点，在Claude Code内提升了19.1个百分点。

- **跨环境迁移能力**：优化后的Skill工件在跨模型规模、跨执行环境（Codex与Claude Code之间）以及跨邻近数学benchmark迁移时，无需进一步优化即可保持价值。

![图片](https://mmbiz.qpic.cn/sz_mmbiz_jpg/Jric6EjH3919ibTNankNIn11zvW3IRyFU8fwIr8FFekKTibJS4O8RQae25t9fByv8eBFxBa7Br6rtANia9l09ShZWVlyeDnHUDcCt4Cu5qlHTBc/640?wx_fmt=jpeg#imgIndex=7)

这种跨环境迁移的特性特别值得关注，它暗示了Skill文档作为一种“声明性知识的外化状态”，捕获了任务域的结构化信息，而非特定模型或执行环境的过拟合噪声。

## 三、回到Agent，SkillOpt作为在Model-Harness协同演进中的信标

在这篇论文的启示下，冥冥之中让我感到了未来Harness与Model体系的另一条进化路径。

### 3.1 从”Skill文档”到”可训练的外部状态”

SkillOpt最核心的思想贡献，我想在于它明确提出了一个范式转变：Skill不应被看作Agent的“外部插件”，而应被更彻底的视为可联动Harness与Model于一体的“外部可训练状态” 。

在传统的Harness体系中，Skill更多的是一种工程层面的配置，人类工程师编写、版本管理、手动调优。但在SkillOpt的框架下，Skill变成了一种可以通过优化过程自动进化的“模型外状态”，而Harness则从单纯的“运行时支撑层”，升维为承载这种“外状态训练”的工程基础设施。

这种视角转变与我之前在《[从AutoHarness到Heuristic Learning，探析未来Model与Harness间隐含的关系演进与统一视角下的新研究方向](https://mp.weixin.qq.com/s?__biz=MzkxOTY2MjE3Nw==&mid=2247488892&idx=1&sn=4282e1347c79f334fb3903f8fddb79c5&scene=21#wechat_redirect)》一文中讨论的Model与Harness关系演进有深刻的共振。我在那篇文章中写道：

“Model与Harness间的全新边界甚至其之间在完整任务推理与持续学习上的深层关系也在发生着更多超乎想象的根本性演进，比如策略算法与工程约束之间那层越来越模糊的边界与定义。”

现在回想起来，SkillOpt从另一个角度恰好为那层“模糊的边界”提供了一种可动态演进的具体实现：当Skill从静态的工程配置演变为动态的可优化外状态时，Harness不再仅仅是Agent的运行外壳，而是成为承载Agent持续进化的“外参数空间训练场”。

### 3.2 Harness Engineering的未来方向

那么，在SkillOpt所揭示的洞察下，Harness Engineering应该如何演进？

#### （1）从单Skill优化到多Skill协同进化

如SkillMOO已经展示了多目标优化在Skill进化中的可能性，通过LLM提议编辑和NSGA-II幸存者选择，自动进化Skill捆绑包以平衡成功率、成本和运行时间。这提示我们，未来的Harness可能需要支持多个关联Skill之间的协同优化，而非单Skill的独立进化。

在实践中，一个企业级Agent系统可能同时部署数十个Skill（分别处理不同的子任务类型），这些Skill之间可能存在依赖、冲突或协同关系。如何设计Harness层面的编排机制，使得这些Skill可以在统一的优化框架下协同进化，是一个值得深入探索的方向。

#### （2）从Offline优化到Online持续进化

MetaClaw的工作提供了一个有趣的参照：通过技能驱动的快速适应（零停机）和机会主义的策略优化（利用用户非活跃窗口进行LoRA微调和RL）的双循环机制。这种思路如果与SkillOpt的受控优化框架结合，有望实现生产环境中Agent的在线持续自进化，在业务不中断的前提下，Skill文档和Agent策略能够随着使用数据的积累而持续改进。

#### （3）从被动反馈到主动探索式技能发现

当前SkillOpt依赖于任务执行后的评分反馈来驱动优化，这本质上是一种被动的、反应式的进化模式。但一个更深远的问题是：Agent能否主动探索未知的任务空间，自主发现并构建新的Skill？

SOLAR的工作提供了一些启示，它利用参数级元学习，将模型权重视为探索的环境，自主发现适应策略。如果将这种主动探索的范式融入Harness体系，Agent或许可以在业务低峰期主动生成和验证新的Skill变体，实现从“被动优化”到“主动进化”的范式跃迁。

#### （4）从文本Skill到多模态执行知识的外化

当前SkillOpt专注于文本形式的Skill文档优化。但在更复杂的企业场景中，Agent的技能可能还包含结构化的API调用模板、环境配置脚本、决策流程图、Ontology知识结构等多种形态的“先验知识”。Harness体系需要支持这些异构知识的外化和协同优化，构建一个统一的“可训练外状态空间”。

## 四、回到Model层：自进化Harness体系如何反哺模型能力的持续提升

在讨论完SkillOpt和Harness体系之后，我们必须面对一个更深层的问题：这种”外部状态”的自进化，与”内部权重”的持续学习（Continued Learning）之间，未来是否以及应该建立怎样的协同关系？

这一问题的实质，我想是SkillOpt框架为模型层能力提升提供了哪些新的可能性和所谓的飞轮效应。

### 4.1 外部进化作为内部训练的”数据飞轮”

先说宏大一点的也许也是最直接的启示是：SkillOpt驱动的高质量Skill演化轨迹，为构造模型微调和强化学习的高质量训练数据源提供潜在更优且更具效率的价值。

在传统的模型训练流程中，高质量的训练数据（尤其是带有明确过程性反馈信号的Agent交互轨迹）的获取是一个巨大瓶颈。而在SkillOpt框架下，Agent在执行任务过程中产生的大量带评分rollout、优化器模型产生的因果分析和编辑决策、以及自进化过程中验证集筛选的“最优Skill文档”，这些都可以被系统性收集和标注。

具体而言，SkillOpt框架在运行过程中自然产生的以下数据，我想对模型层的持续学习具有极高的训练价值：

- **优化器模型产生的因果分析**：分析Agent失败/成功的原因，这些分析文本蕴含了丰富的”推理过程性知识”，可以作为过程奖励模型（PRM）的训练数据；

- **最优Skill文档的演化轨迹**：展示了从初始Skill到高表现Skill的”进化路径”，为模型学习”如何改进持续学习策略”或”分阶段训练策略”提供了示范；

- **验证集评判的编辑决策**：记录了哪些类型的Skill调整真正带来了性能提升，这些偏好数据可以被用于对齐训练。

以MetaClaw为例，其双循环机制中的Opportunistic Policy Optimization正是利用Skill进化过程中产生的更高质量的轨迹数据进行RL-PRM训练，使得“更好的Skill → 更好的轨迹 → 更强的模型”形成正向反馈循环。

甚至在搭建了完整且成熟的Self-Evolve Harness体系后，是否可以想我上一篇文章笔记《[从Eric Jang对AlphaGo重构、优化、破解的感悟，探析AlphaGo对未来AI的启示](https://mp.weixin.qq.com/s?__biz=MzkxOTY2MjE3Nw==&mid=2247488937&idx=1&sn=08a258d58bf3a15004cdc557337463e1&scene=21#wechat_redirect)》中，像围棋这类高密集结构性策略对弈那样，采用一种更高级的结构性探索与回溯进化机制来完成高级宏观策略与复杂任务的决策模式建模，以构建企业专有多元风险与竞争下的多因素复杂决策模型。

### 4.2 从外状态优化到模型层隐参数权重的引导性微调

在目前SkillOpt的工作中，Agent的模型权重是”冻结”的，优化完全发生在外部Skill文档上。但一个自然的问题是：我们能否利用优化后的Skill和Agent交互轨迹，来引导模型内部权重的快速微调（Fine-Tuning），使得模型内化那些被外部Skill文档所捕获的”能力”？

这种思路的潜在优势在于：

- **高质量的过程性信号**：不同于传统SFT仅提供最终输出作为监督信号，Skill优化过程中产生的因果分析、编辑决策等提供了丰富的”过程性反馈”，可以支持更精细的策略学习；

- **蒸馏外化知识**：如果模型能够通过微调内化那些被外部Skill所捕获的”问题解决策略”和”经验性知识”，那么Agent在推理时对Skill文档的依赖就可以逐步减轻，类似于人类从”需要查阅操作手册”到”内化为肌肉记忆”的转变；

- **防御知识遗忘**：与SDFT等工作强调的持续学习中的灾难性遗忘问题相结合，模型在保持已有能力的同时内化新技能。

然而这个方向并非没有挑战。一个核心问题是：外部Skill文档中蕴含的“经验性知识”能否被有效地编码进模型权重，而不发生显著的性能退化即灾难性遗忘，以及这种内化过程是否会导致模型在迁移到新环境时失去外状态优化所提供的灵活性？

看来Continued Learning还需努力，当然我们也侧面看到这一方向未来更多的潜力与价值。

### 4.3 自带明确奖励信号的强化学习闭环

SkillOpt框架中一个特别优雅的设计是：验证集分数提供了明确的、可度量的奖励信号。

这与RLHF中采用依赖人类偏好标注、或者传统RL中依赖稀疏环境奖励的模式有着本质差别。在SkillOpt的优化循环中，每一次编辑的接受与否由验证集分数严格决定，形成了一个自洽的“优化-验证-接受/拒绝”闭环。这一闭环天然适用于强化学习的训练框架，验证集分数可以作为奖励信号，Agent的Skill编辑决策可以作为动作，整个优化过程可以被建模为一个序贯决策问题。

EvolveR的工作已经展示了这一思路的初步可行性：使用GRPO强化学习训练Agent“学会如何善用经验”，奖励函数不仅包括最终答案的正确性，还包括检索策略、推理格式等过程性指标的合理性。SkillOpt框架中的编辑决策和验证筛选机制，可以进一步为这种过程性强化学习提供更精细的信号。

更进一步，如果我们将SkillOpt的优化器模型本身也纳入强化学习框架——即训练一个专门的“Skill优化策略网络”来学习在给定Agent执行反馈的情况下如何更有效地提出编辑建议，那么我们就有可能构建一个双层强化学习体系：

- **内层**：Agent学习如何利用Skill文档更好地执行任务；

- **外层**：Optimizer学习如何更好地为Agent优化Skill文档。

这种“元优化”的能力一旦形成，就构成了真正意义上的“Learning to Learn”，使Agent体系具备了在开放环境中持续自主进化的基础。

### 4.4 Harness作为承上启下的信号传导层

在上面的讨论中，一个逐渐清晰的图景浮现出来：Harness体系在“外状态自进化”与“内权重持续学习”之间，扮演着信号传导和数据飞轮的核心角色。

具体而言，一个完整的自进化Agent工程化体系或许应包含以下三个层次的循环，做张图简单举例：

![图片](https://mmbiz.qpic.cn/sz_mmbiz_jpg/Jric6EjH3919ERsLGVvcfGRKK6zzkb0iahLfH3xjQg9XDh9e1fqZFeomU4icBtVo1tEic60Ujr4GNMw9uI18dAW7pZdSFQnynRZhZsxlAXGicIGY/640?wx_fmt=jpeg#imgIndex=8)

Harness体系需要为这三个层次的循环提供统一的运行时支撑：数据采集、信号聚合、版本管理、安全审计、灰度发布等工程化能力。这与AI Harness Engineering论文中提出的“十一项组件责任”——包括可观测性、失败归因、验证、权限管理等在理念上高度一致。

实际上，SkillOpt论文中“冻结Agent、独立Optimizer、受控接受机制”的设计，已经在快速循环层次上展示了一种兼具科学严谨性和工程可行性的范本。这种设计的精髓，既在于其明确的科学方法论精神（严格验证、保守更新），也在于其在企业应用场景下的高可用性（零推理开销的Skill注入），为向中速和慢速循环的延伸提供了坚实的基础。

## 五、未来工程化全栈蓝图：从通用到企业专有领域的纵深思考

在梳理了SkillOpt的技术内核、与梯度下降的深层关系、以及作为在Harness体系中的信标等这些洞察之后，我想结合自己的实践观察，尝试先勾勒一个稍宏大且粗糙一点的全栈蓝图：一个从通用领域到企业专有领域、从Harness外部状态到Model内部权重、从离线优化到在线进化的自进化Agent工程化体系。也请大家轻拍哈，期待妲己也给出更多的有独到见解的参考建议。

### 5.1 通用领域：Skill生态的”集市化”与”标准化”

在通用领域（开源社区、CC或Codex平台、通用Agent平台、甚至是近期被资本追逐的类OpenRouter商业形态），自进化Skill体系可能走向类似开源软件生态的“集市化”演进路径。在这个路径下：

- **Skill人机协作社区型优化**：不同的开发者可以在公共Skill文档上进行协同优化，利用SkillOpt类框架各自独立提出编辑建议，通过社区验证集投票决定是否合并，类似于开源项目的Pull Request + CI机制；

- **Skill的可组合性与迁移性**：高质量的Skill文档可以作为”插件”在不同的Agent、不同的执行环境之间迁移。SkillOpt论文中已经初步展示了Skill的跨环境迁移能力，随着这一能力的进一步增强，我们是否在未来可能看到一个更完备且更具有规范性的”Agent Skill App Store”的出现，开发者上传优化后的Skill，甚至于平台上持续进化，其他Agent可以直接下载使用；

- **Skill的评估基准与排行榜**：类似于ImageNet之于计算机视觉、SWE-Bench之于代码Agent的作用，我们需要建立标准化的Skill评估基准和排行榜，使得不同Skill的质量具有可比较的量化指标。

这一方向的关键挑战在于标准化，Skill文档的格式、编辑操作的语义、验证集的构建方法都需要形成行业共识，才能真正实现跨组织、跨平台的Skill互操作性。

### 5.2 企业专有领域：私域内壁垒型Skill的构建与持续演进，最终沉淀为企业高价值Asset

在企业专有领域（垂直行业的私有化部署），自进化Skill体系的路径则可能呈现出不同于上述通用领域的特征，如：

- **领域知识的外化与沉淀**：企业多年积累的行业经验、专家知识、业务规则可以通过SkillOpt框架被系统性地编码为可优化的Skill文档，实现从”人脑经验”到”可训练外状态”的转化；

- **私有化的持续进化闭环**：企业可以在自己的私有环境中构建”任务执行 → 反馈收集 → Skill优化 → 模型微调”的完整闭环，所有数据和优化的Skill都保留在企业内部，形成具有竞争壁垒的自进化能力；

- **多租户Skill的隔离与共享**：在大型企业中，不同业务部门可能需要独立的Skill实例，但又需要共享某些通用能力。Harness体系需要支持Skill的多租户管理，包括权限隔离、版本分支、跨部门共享等功能；

- **合规性驱动的可解释Skill**：在金融、医疗、法律等强监管领域，Agent的决策过程需要可审计和可解释。Skill文档作为”声明性知识的外化状态”天然具有可解释性，企业可以逐条审查Skill文档中的指令，理解Agent为什么会做出某个决策，这对于企业合规具有重要价值。

这里需要注意的是：类似SkillOpt中所采用Optimizer Model或未来其它Self-Evo框架中需使用的Frontier Model的选择，其原始专家构建的Skill→到前向Rollout采样得到执行轨迹→Optimizer Model诊断并修改方案→验证集给出的轨迹样本与评价得分等作为企业核心数据资产，我想在短期还是需要通过采用私有化开源模型部署的方式来完成Self-Evo，尽管与御三家等旗舰闭源模型存在差距，我想短期是可以通过Harness Self-Evolve拉回一些的。

这里也有一个我特别关注的方向：在企业私有环境中，如何利用SkillOpt的“验证集筛选”机制构建领域专属的评估体系？

不同于通用领域的公共benchmark，企业场景中的任务评估往往是高度定制化的，例如“客户投诉处理的满意度”、“财务报表分析的准确性”、“生产线调度的效率提升”等。SkillOpt的框架在允许企业根据自身业务指标构建私有验证集，使得Skill的优化方向与业务目标保持精确对齐上，这一点我想在传统深度学习模型的微调中是很难做到的，即企业无法快速并准确的定义一个“客户满意度”的Loss，但构建一个模拟客户反馈的验证集来筛选Skill编辑我想是相当可行且直观的，且企业这部分数据维度的累计资产应相当丰富。

### 5.3 Harness体系中的关键使能组件

在这样一个全栈蓝图中，我想接下来以下几个工程性组件将扮演关键角色：

- **（1）Skill Registry & Version Control**：类似于Docker Registry或Hugging Face Model Hub的Skill注册中心，支持Skill的版本管理、依赖追踪、回滚和灰度发布。Skill文档的每一次”成功编辑”都应该被自动记录为一个新版本，并保留完整的优化轨迹和验证结果。

- **（2）Validation Suite Manager**：管理验证集的构建、维护和版本化。由于Skill的优化方向由未来的某种类似于论文中的验证集思想决定，验证集的质量和覆盖度直接决定了Skill的质量。同时验证集管理器需要支持动态扩展（新增测试用例）、统计监控（难度分布、覆盖率分析）和自动去噪（过滤质量低下的测试用例）。

- **（3）Evolution Scheduler**：管理Skill优化的时机和频率。在通用领域，Evolution Scheduler可以基于设定的周期（如每日/每周）或事件触发（如新的验证用例上线）来启动Skill优化流程。在企业场景中，在不同的企业IT Infra下，Evolution Scheduler还需要考虑业务波峰波谷，在业务低峰期进行Skill优化以避免对生产环境造成影响。

- **（4）Cross-Model Skill Translator**：虽然SkillOpt展示了Skill的跨模型迁移能力，但在实际部署中，不同模型家族（GPT、Claude、Gemini、DeepSeek、Qwen等）对Skill文档的理解可能存在微妙差异。一个专门的Skill翻译器可以根据目标模型的特点对Skill文档进行微调，使得同一套Skill在不同的底层模型上都能保持良好的表现。

- **（5）Human-in-the-Loop Review Interface**：在关键业务场景中，Skill的某些编辑可能需要人工审核后才能上线。这要求Harness提供一个高效的人工审核界面，展示编辑的Diff对比、验证集分数变化、可能影响的任务范围，以及该编辑对应的典型case。

### 5.4 迈向更长远且本质的目标：Model与Harness边界与进化的统一

最后，我想回到一个更本质的思考：SkillOpt所代表的方向，将Agent技能视为可训练的外部状态，是否为”Model与Harness的边界统一理论”提供了一条可能的通路？

我在之前的文章《[从AutoHarness到Heuristic Learning，探析未来Model与Harness间隐含的关系演进与统一视角下的新研究方向](https://mp.weixin.qq.com/s?__biz=MzkxOTY2MjE3Nw==&mid=2247488892&idx=1&sn=4282e1347c79f334fb3903f8fddb79c5&scene=21#wechat_redirect)》中曾经写道：

> “策略算法与工程约束之间那层越来越模糊的边界与定义.. 同时这种新的关系与边界的交织耦合似乎又会为更具复杂、更具垂直深度的产业AI落地与交付带来新的潜在可探索空间与可执行路径。”

现在，SkillOpt为这个模糊的边界提供了一种可操作的刻画，即Skills或Harness可变通用框架作为那个位于”模型策略”与”工程约束”之间、可被双边操作的”可训练外状态”的其中之一的信标。

- **从模型侧看**：Skills及Harness可变框架是模型能力的”外化延伸”，它们补充了模型可能不具备的特定领域知识、操作流程和约束规则；

- **从Harness侧看**：Skill与Model则是工程约束与策略指引下的”两种分布表达”，它们将业务规则、合规要求、操作规范等编码为模型可理解的指令及围栏；

- **从整体Self-Evo视角看**：Skills+Harness+Model三者同时受到来自人类先验知识、工程验证指标、模型执行反馈等不同工程化体系阶段下的多重优化机制，这种”三位一体”的完整性，也许使得当前阶段Skill将率先成为突破Model与Harness交互的”界面层”的最优候选。

未来的统一或许可以围绕这一”界面层”展开：定义清晰的状态表示（Skill的格式与语义）、操作原语（增/删/改编辑的语义与边界）和优化目标（多目标下的验证分数提升），从而在Model和Harness之间建立起一套严谨的、可工程化的协同演进规范。当然，随着Model与Harness间工程体系的进一步体系化，三者间更充分的协同进化将会成为一种新的更紧密的AI演进模式。

## 结语：从”教会Agent”到”让Agent学会”

微软这篇SkillOpt论文带给我的最大启发，不仅是某项具体的技术创新，而是一种看起来更激进思想。

在过去的Agent开发实践中，我们一直在做的是“教会Agent”，人类工程师编写Prompt、配置Skill、设计工具链、手动调参。这是一种“人类教”的模式。

SkillOpt让我们看到了另一种可能性：“让Agent学会”，通过搭建可行的、完备的、系统化的、受控的、验证驱动的自进化机制，Agent能够在人类设定的目标框架内自主优化自身的行为策略。

这不是AGI，甚至离AGI还有很远。但它是通往“更具自主性的AI系统”的一步扎实的脚印，或者或许可以为未来AGI铺下另一条可加速的路径。

正如我在此前一篇文章中写道：“未来的Token该如何演化或者进化？是人类与AI循序渐进的协作式演化，还是人类开盒后的AI Self-Evolve？”

——来自《[从「AI4Chip」角度看：从AI模型对复杂空间求解到Token·词元的共进化模式演进](https://mp.weixin.qq.com/s?__biz=MzkxOTY2MjE3Nw==&mid=2247488781&idx=1&sn=e2894dbf5aa9e6e3de6e8f544262a903&scene=21#wechat_redirect)》这篇笔记

SkillOpt给出了一种可能的答案：两者兼有，但需要架设一套系统性的工程框架作为中间的桥梁。 人类设定目标（验证集）和边界（编辑约束），Agent在框架内自主寻找最优策略，这是一种“受控的自主性”，或许正是当前技术阶段下自进化Agent体系一条务实、有效的发展路径。

当Skills拥有了自己的“反向传播”，当文本空间中的离散符号也可以被像连续参数一样被系统性地优化，Agent从“会用Skill”走向“会从经验中长出Skill”的道路，似乎不再那么遥远了。而这条道路的工程化实现，即构建一个同时承载外部Skill自进化和内部模型持续学习的Harness体系，也许将成为未来几年Agent工程领域最值得投入的方向之一。

BY 吕明 06.05.28
