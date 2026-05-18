---
title: "Cursor 团队是怎么把 SKILL 写成协议、骨架和契约的"
description: 拆解 cursor/plugins/cursor-team-kit 的 17 份 SKILL，提炼出可直接抄走的写作规范：触发协议、四段骨架、输出契约、反面清单，以及一份操作清单与速查表。
author: Alden
date: 2026-05-18 19:00:00 +0800
categories: [LLM Engineering, Methodology]
tags: [Agent, AI Coding, Best Practice, LLM, Methodology, Cursor]
pin: false
mermaid: true
comments: true
---

> 最近 Cursor 团队开源了 `cursor-team-kit`，作为顶尖的 Harness 工程团队，他们这套 17 个 SKILL、1 个 Agent、2 条 Rule 的写法，自然很有学习价值。本文只回答一件事：**他们写 SKILL 的姿势里，哪些规范值得任何人原样抄走？**

---

## 一、为什么这套 SKILL 值得当样本

Cursor 团队这一打 SKILL 平均 **40 行**：最短的 `deslop` 只有 16 行，最长的 `pr-review-canvas` 177 行，但那一份带 `template.html` + `renderer.js` + `styles.css` 三个工程附件，纯文本部分仍然短。整个 kit 里 17 个 SKILL，**只有 1 个**带附件；1 个 Agent（`ci-watcher`，配 `model: fast` + `is_background: true`）；2 条 Rule（都用 `alwaysApply: true`），其中 `no-inline-imports.mdc` 正文只有一句话："Always place imports at the top of the module."。这不是省事，这是态度。

但话说回来，写 SKILL 的判断力跟写代码的判断力是两码事。笔者审过自己工位上 `~/.agents/skills/` 那一坨 SKILL，单文件 200–300 行是常态，`Use when / Anti-triggers / Tips / Examples / Notes` 段段都全，看上去像一篇博文。Cursor 团队写一份 60 行能搞定的事，自己写到 250 行还觉得"不够详细"。

更直观的对比：`get-pr-comments` **总共 21 行**，从 frontmatter 到 Output 段全包，覆盖了"从 PR 上抓评论 → 按 severity 分组 → 输出 action list"整条路径。`fix-ci` **29 行**走完了 CI 失败的诊断到推送闭环。`new-branch-and-pr` **29 行**包含新建分支、提交、推送、开 PR 五步。它们不是写得简陋，是写得**只剩骨头**。

差距不在文笔。差距在**对 SKILL 这个文体到底是什么的判断**。

这份 kit 的官方定位写得明白：*"Designed to be plug and play without requiring third-party service integrations"*。但更值得抄的是 README 没明说的那部分——**SKILL 的读者不是人，是另一个 LLM**。把这一句话当公理推下去，Cursor 团队的所有写法都立得住。

---

## 二、SKILL 是什么：四个并列断言

不要写一个长定义。写四个独立成立的"SKILL 是 X"，每一条都能单独被引用。

### SKILL 是一份触发协议

SKILL 不是"教程"，是 LLM 和运行时之间的一份契约：**给定什么样的用户语义，把这个 SKILL 装进上下文**。Cursor 团队的 `description` 字段几乎全是同一个公式：

> **\<做什么\> + \<典型触发场景\> + \<用户原话\>**

举 `make-pr-easy-to-review` 的 description：

```text
Prepare PRs for review by cleaning noisy history, improving PR descriptions, and
adding reviewer guidance without changing code behavior.
Use for "make this easy to review", "tidy this PR", "clean up commits",
or "annotate the diff".
```

最后那一段引号里的"用户可能说出的原话"才是触发的关键。LLM 的召回是语义相似度，**和用户语料越对齐的 description，召回越准**。光写"清理 PR 历史的工具"是不够的，因为用户不会这样说话，用户会说 "tidy this PR"。

再对照三份风格各异的 description，看公式怎么变形：

```text
# pr-review-canvas（重操作，要描述"产出物形态"）
Generate an interactive PR review walkthrough as an HTML page. Fetches PR data
via gh API, categorizes files into core vs mechanical changes, adds reviewer
annotations, and renders diffs with moved-code detection. Use when the user
pastes a GitHub PR URL and asks for a review, walkthrough, or summary,
or says "review this PR".
```

```text
# control-ui（取证底座，要描述"什么场景调它"）
Build or adapt a local browser/CDP harness to drive and inspect a web, IDE,
or Electron UI. Use for local UI verification, screenshots, accessibility
snapshots, perf profiles, visual diffs, or reproducing UI bugs.
```

```text
# weekly-review（高频例行任务，触发词就一句）
Produce a weekly synthesis of authored commits with highlights by bugfix,
tech debt, and net-new work.
```

三段都遵循"功能 + 场景 + 用户原话"的骨架，但**侧重点跟着 SKILL 性质走**：

- `pr-review-canvas` 是重操作，所以 description 里要把"产出物长什么样"（HTML、moved-code detection）明示，让 LLM 在普通对话里**敢于不调用它**。
- `control-ui` 是底座，所以 description 强调"场景列表"（screenshots / a11y snapshots / perf profiles / visual diffs / repro），方便上层 SKILL 用关键词触达。
- `weekly-review` 用户语料天然窄，"weekly synthesis / bugfix / tech debt / net-new" 四个名词就够 LLM 召回，反而不需要堆 "用户原话"。

**通用公式**：description ≤ 50 词。第一句一定是动名词开头的功能；第二句是场景列表或用户原话。多写一个字都是浪费 LLM 的注意力预算。

### SKILL 是一份四段骨架

打开任何一份 Cursor 团队的 SKILL，结构都一样：

```text
---
name: ...
description: ...
---

# Title

## Trigger          # 什么场景叫我
## Workflow         # 1. 2. 3. 编号步骤，每步一句
## Guardrails       # 不要做什么
## Output           # 交付什么
```

只有四段。可选段位（`When To Use` / `Commands` / `Example Commands` / `Suggested Checks` / `Output Shape` / `Focus Areas` / `Setup Pattern` / `Style Notes`）按需追加，但**主干永远是这四个**。`Overview`、`Introduction`、`Background`、`Conclusion`、`Tips` 这种空话标题一个都没有。

frontmatter 同样是白名单——实际只用到 4 个字段：

```yaml
---
name: kebab-case-name
description: <做什么> <典型触发场景> <用户原话>。
# 可选：
disable-model-invocation: true   # 重操作、强制手动触发
model: fast                       # 仅 agent，让监视/轮询走轻量模型
is_background: true               # 仅 agent，在后台跑不占主对话
---
```

骨架的好处是：LLM 可以做"分段对位"。读到 Trigger 决定要不要进来，读到 Workflow 拿到执行步骤，读到 Guardrails 知道哪里要收口，读到 Output 知道该返回什么。**结构本身就是 prompt engineering**。

为啥 4 段就够？因为这 4 段对应了 LLM 处理一份 SKILL 时实际要回答的 4 个问题：**该不该用？怎么做？哪里别越界？要返回什么？**。多出来的段位都是细化版（`Commands` 是 Workflow 的命令清单细化，`Output Shape` 是 Output 的字段细化），不是新维度。

### SKILL 是一份输出契约

`verify-this` 把这一点做到了极致。它的 Output 不是"输出一份验证报告"，而是直接给一个**可机检的 schema**：

```text
VERIFIED | NOT VERIFIED | INCONCLUSIVE
Claim: <falsifiable claim>

Evidence:
<metric/artifact>: baseline=<...>, treatment=<...>, delta=<...>, threshold=<...>

Reasoning:
<one tight paragraph naming the evidence and any confounds>
```

注意三点：

1. **三态枚举**：`VERIFIED` / `NOT VERIFIED` / `INCONCLUSIVE`。`INCONCLUSIVE` 被显式建模出来，避免"测不出来"被默默归到"通过"。
2. **字段固定**：`Claim`、`Evidence`、`Reasoning` 三个段，连段名都规定好。
3. **最后一句兜底**："Do not soften a negative result. A clear `NOT VERIFIED` is useful." 这一句是给 LLM 听的——它本能想给用户一个"好消息"。

输出写成 schema，下游随便用什么解析都能接。输出写成博文，下游只能祈祷 LLM 这次格式没漂。

`verify-this` 还顺手规定了一份**artifact 目录布局**，让多次验证之间可对比、可归档：

```text
/tmp/verify-this/<claim-slug>/
├── claim.md      # 改写过的可证伪 claim
├── timeline.md   # 这次验证做了哪些动作
├── baseline/     # 改前的取证
├── treatment/    # 改后的取证
├── diff/         # baseline vs treatment 的差异
└── verdict.md    # 最终的 VERIFIED / NOT VERIFIED / INCONCLUSIVE
```

这一段是"输出契约"的延伸——**契约不只规定字段，还规定文件放哪、长什么名**。下次跨 session 复检的时候，LLM 不需要重新理解上次的布局；上次留的 `verdict.md` 是这次 baseline 的天然起点。看似多事，实际是让 SKILL **跨时间维度也可机检**。

`verify-this` 还有一句给隐私上锁的：*"If artifacts may contain sensitive code, prompts, screenshots, HTTP bodies, or heap data, keep only the minimal inline evidence unless the user agrees to disk storage."* 这条不是 Guardrails 里的"不要做什么"，是**写在 artifact 段里的"默认行为"**——默认就不写盘，要写盘必须用户同意。这种"安全默认值"的写法比单独写一条 Guardrails 更不容易被 LLM 跳过。

### SKILL 是一份反面清单

Guardrails 是 Cursor 团队最克制的一段。措辞高度一致：**全部负面祈使句，每条一行，可枚举**。从 `loop-on-ci` 抄两条：

```text
- Do not bypass hooks (`--no-verify`) to force progress.
- If the failure is clearly unrelated to the PR and appears fixed on main,
  merge latest main instead of bloating the PR with unrelated fixes.
```

从 `control-cli` 再抄两条：

```text
- Prefer deterministic waits over sleeps. If you must sleep, explain why.
- Do not send credentials or destructive commands into a controlled session.
```

再来一组**特别值得抄走的领域专属 Guardrails**：

```text
# fix-merge-conflicts
- Regenerate lockfiles with package manager tools instead of hand-editing.
- Do not leave conflict markers in any file.
- Avoid broad refactors while resolving conflicts.

# run-smoke-tests
- Prefer deterministic waits and assertions over brittle timeouts.
- Re-run passing fixes to reduce flaky false positives.
- Quarantine tests only when explicitly requested and documented.

# control-ui
- Do not rely on stale element references after navigation or structural changes.
- Avoid coordinate clicks unless a fresh screenshot was captured immediately before the click.
- Do not hard-code selectors, ports, or script paths from another repository.
```

每一条都对应一个 LLM 容易踩进的具体坑：手改 `package-lock.json` 制造一堆 phantom diff、看见一次 pass 就报喜把 flake 漏过去、用 `await new Promise(r => setTimeout(r, 1000))` 求快、抄上一个 repo 的选择器到当前 repo 不验证。**写 Guardrails 的方法**：回想自己/同事/LLM 上一次在这个领域翻车的姿势，把它取反、加 `Do not` 前缀，就是一条 Guardrails。

为什么 Guardrails 一定写"不要做什么"？因为 LLM 已经被对齐成"积极有用的助手"，正面祈使句它本来就会做，负面祈使句才是它真正需要被警告的边界。**Guardrails 的信息密度等于"LLM 容易踩进去的坑"的清单**——不踩坑的部分根本不需要写。

---

## 三、什么时候你需要写一个 SKILL · 什么时候你不需要

写 SKILL 之前先想清楚要不要写。Cursor 团队的 `workflow-from-chats` 把这个判断拆得非常干净。

### 什么时候你需要写一个 SKILL

满足以下任意一条：

- **可重复的多步流程，且有清晰触发词**。比如"看 CI 直到绿"——多步、可枚举、触发词明确（"loop on CI"、"watch the build"、"是不是过了"）。
- **存在唯一可信源的判断**。例如 `gh pr checks` 是 PR check 的 source of truth，而 `gh run list` 只覆盖 GitHub Actions——这种"看起来等价、实际有覆盖差异"的命令选择，要在 SKILL 里**显式锁住**。
- **取证/裁决/构造**这三类操作之一。Cursor 团队把它们分层做：`control-cli` / `control-ui` 是**取证底座**，`verify-this` 是**裁决器**，`pr-review-canvas` 是**构造器**。每一层独立成 SKILL。
- **有"重操作"风险，需要 disable-model-invocation 关闸的**。下文会展开。

### 什么时候你不需要 SKILL

`workflow-from-chats` 给出四个选项里有三个**不写 SKILL**：

- **Rule**：是"广泛适用的行为约束"，不是"多步流程"。例如 `typescript-exhaustive-switch.mdc` 整篇正文只有一句：*"In switch statements over discriminated unions or enums, use a `never` check in the default case so newly added variants cause compile-time failures until handled."* `no-inline-imports.mdc` 也是一句话。配上 `alwaysApply: true`，一直挂在 system prompt 里——**适合"短、绝对、跨场景"的约束**，比塞进每个 SKILL 的 Guardrails 重复一遍干净得多。
- **Workflow doc**：是"对未来有用、但不可靠触发"的上下文。例如某次架构决策的笔记，存进 docs/，不要往 SKILL 里塞。
- **No artifact**：是"情境性、过时、低置信"的观察。`workflow-from-chats` 显式列出"No artifact: situational, stale, or low-confidence observation"——**承认有些经验不该被编码**比强行编码出一个 SKILL 健康得多。

**Rule vs SKILL 的判断**：约束如果"看到代码就该生效"（imports 位置、switch 穷尽），就是 Rule。约束如果"看到某种用户意图才生效"（清理 PR、修 CI、看烟雾测试），就是 SKILL。两者不要混。把 Rule 内容塞进每个 SKILL = 重复维护 N 份；把 SKILL 工作流塞进 Rule = 永久挂在 system prompt 里，污染所有对话的 context。

### Agent 是 SKILL 之外的第四种形态

`ci-watcher` 是整个 kit 里唯一一个 Agent，13 行：

```yaml
---
name: ci-watcher
description: Watch PR CI for the current branch and report pass/fail with relevant failure links. Use when waiting for CI results or CI has failed. Use proactively to monitor branch CI.
model: fast
is_background: true
---
```

注意三个细节：

1. **`model: fast`**：监视/轮询这种事不需要 frontier model 的推理，用快模型省 token 也省时间。
2. **`is_background: true`**：不占主对话上下文，可以"挂在后台慢慢等"。
3. **description 末尾的 `Use proactively`**：明确告诉运行时可以主动触发，不需要等用户说话——和重操作 SKILL 的 `disable-model-invocation: true` 是镜像关系。

**通用规则**：长时间轮询、低频但需要兜底的监视、跨 session 的状态守望——这些任务应该写成 Agent，不是 SKILL。Agent 是"挂着的进程"，SKILL 是"被调起来的函数"。

第三档最容易被忽视。笔者过去最常踩的坑就是把一次性 anecdote 强行变成 SKILL：当时是好用的，三个月后语境变了再回头看，反而成了误导新对话的诱饵。**编码下来的经验是有半衰期的**，不该编码的就让它过去。

---

## 四、每一个 SKILL 都是一份"协议"，不是一篇博文

这是全文最值得记住的一句话。它来自审计报告的总评：

> **SKILL 不是教程，是协议**——它的读者是另一个 LLM，越像 API 文档（精确、可枚举、可机检）就越好用；越像博文（铺垫、举例、修辞）就越容易失效。

为什么这个区分重要？因为博文的读者是人，人有耐心、有上下文、会跳读、会脑补。协议的读者是 LLM，**每读一个 token 都要从你这里付**一次注意力税。一份 250 行的 SKILL 占用的上下文窗口是一份 60 行 SKILL 的 4 倍，而后者覆盖的执行路径不一定更少。**短不是为了好看，是为了让 LLM 有预算去处理用户真正的问题**。

帕斯卡那句法语放在这里恰好：

> *"我之所以把这封信写得这么长，是因为我没空把它写短。"*

`deslop` 这份 SKILL 只有 16 行，但每一行都是一条具体的反面清单（"Extra comments that are unnecessary"、"Casts to `any` used only to bypass type issues"）。它没有任何"什么是 AI slop"的铺垫，因为这种铺垫人会脑补、LLM 也会脑补——花笔墨写它就是浪费上下文预算。

记住这一条：**写完 SKILL 之后通读一遍，每一句话都问"如果删掉，LLM 的行为会变吗？"如果不会变，就删**。

---

## 五、写 SKILL 的操作清单（Step 0 起步）

把上面这些规范压成可逐步执行的清单。注意 Step 0——不是 Step 1。

### Step 0：先想清楚谁会调它

动笔写 SKILL 之前，写出**三句用户原话**。不是用户应该说什么，是用户实际会说什么。

举 `babysit` 这种 SKILL 为例。功能描述是"把 PR 维持在 merge-ready 状态"，但用户烦躁起来时不会这样说。用户会说：

- "盯一下这个 PR"
- "搞定它，我去吃饭"
- "make sure this lands"

把这三句话直接抄进 `description`。这就是召回的语料。**这一步不做，后面 SKILL 写得再漂亮也召不出来**。

### Step 1：搭四段骨架

```yaml
---
name: <kebab-case-name>
description: <做什么> + <典型场景> + <用户原话>。
---

# Title Case Heading

## Trigger
<1-3 句话，不要 list>

## Workflow
1. <谓词动词开头>
2. ...

## Guardrails
- Do not ...
- Do not ...

## Output
<能给 schema 就给 schema>
```

四段填完就停笔。如果觉得"还有很多没说清"，先别加段，先回去砍。

### Step 2：Workflow 编号步骤，每步一句

Workflow 是 SKILL 的执行核心，规则三条：

1. 用 `1. 2. 3.` 编号，**每步一句陈述句**，谓词以动词开头（Resolve / Inspect / Capture / Compare / Return）。
2. 步骤数 4–8 步。超过 8 步说明事情不止一个 SKILL，拆。
3. **扁平化**。不要二级编号、不要嵌套 bullet。一级 list 撑不下的内容下沉到独立段（`## Commands`、`## Artifact Layout`、`## Verdict Rules`）。

反面教材：

```text
1. Run the tests
   a. First check if there are tests
   b. If yes, run them
      - Use pytest if Python
      - Use jest if JavaScript
   c. If failed, look at the output
2. ...
```

正面：

```text
1. Resolve the PR for the current branch.
2. Inspect current PR checks before waiting.
3. If checks already failed, diagnose those failures first.
4. If checks are pending, watch with `gh pr checks --watch --fail-fast`.
5. After each push, re-check the full PR check set and repeat until green.
```

后者来自 `loop-on-ci`，五步走完整个 CI 循环。每一步都是一个独立可勾选的动作。

### Step 3：Guardrails 全部写成"不要做什么"

写 Guardrails 时只问一个问题：**LLM 在这个 SKILL 上下文里最容易做错什么事？**

`make-pr-easy-to-review` 的 Guardrails 三条：

```text
- Never hide meaningful behavior changes inside "cleanup".
- Do not bypass hooks unless the user explicitly asks.
- If the PR is too large to make reviewable with notes, recommend splitting
  instead of polishing around the problem.
```

每一条都精准对准 LLM 的"积极但越界"倾向：把行为改动伪装成清理、绕过 hook 求快、明明该拆 PR 却硬要靠 PR 描述补救。

数量上限：**≤ 6 条**。超过 6 条说明你在写"代码规范"，不是 Guardrails，迁到 `references/` 或独立 Rule。

### Step 4：Output 写成可机检的形状

回到 `verify-this` 的 Output 模板。三个特征：

1. **首字段是状态枚举**——LLM 一上来必须从有限集里选一个。
2. **字段名固定**——`Claim:`、`Evidence:`、`Reasoning:` 都规定好。下游 grep 就能解析。
3. **每个字段长度有暗示**——`one tight paragraph`、`<metric/artifact>: baseline=<...>, treatment=<...>`。给了形状，LLM 不会随便铺开。

如果 SKILL 的输出真的没有结构（比如就是一段聊天回复），就明说："Return a concise paragraph naming the action taken." 不要为了凑 Output 段而硬塞 schema。

### Step 5：重操作必须加 `disable-model-invocation`

`pr-review-canvas` frontmatter 里有一行容易被忽视：

```yaml
disable-model-invocation: true
```

这是反默认的设计：**明确告诉运行时"别自动判断要不要用我，必须用户显式说"**。`pr-review-canvas` 要生成 HTML、起 HTTP server、占端口（固定 8432 而不是 `--port 0`，因为 background shell 没 TTY 读不到随机端口）——这种重操作绝对不能被 LLM 在普通对话里误触发。

判断标准：

- 起 server / 占端口 → 加上。
- 生成 HTML/PDF/视频等"输出物本身就是一项工程"→ 加上。
- `git push --force` / 改写历史 / 删 branch → 加上。
- 大量写盘到非 `/tmp` → 加上。

宁可让用户多打一句 `/run pr-review-canvas`，也不要让 LLM 猜中后跑起一个端口。

### Step 6：跨 SKILL 组合，不要重复造轮子

`verify-this` 不自己实现取证。它的 "Local Surfaces" 一段写得清清楚楚：

```text
- CLI/TUI behavior: control-cli, terminal transcript, or demo recording.
- UI behavior: control-ui, screenshots, accessibility snapshots, or browser traces.
```

`control-cli` 提供 tmux 和 PTY 两套最小可运行 harness、提供 `NODE_OPTIONS="--inspect=127.0.0.1:0"` 绑 loopback 的取证脚本——这些都跟"是不是验证"无关。`verify-this` 只做裁决，不做取证。

这是分层的力量：取证底座变了不影响裁决器，裁决器变了不影响取证底座。如果把取证逻辑塞进 `verify-this`，你会发现它越长越像 `control-cli` 的克隆，且每次 `control-cli` 改了你都得手动同步。

**通用规则**：取证、构造、裁决、清理这四类操作分开成独立 SKILL，上层 SKILL 通过引用名字（`Use control-cli`）来组合下层 SKILL。引用是契约，复制是债。

---

## 六、藏在 SKILL 里的工程级细节

短不等于浅。Cursor 团队的 SKILL 里塞了一批"被血洗过才写得出"的工程细节，每一条都值得单独抄走当成自己 SKILL 的兜底。

### 6.1 `pr-review-canvas` 里的两个反直觉细节

**(a) JSON 注入到 `<script>` 不能只靠 `json.dumps`**

`pr-review-canvas` 要把 PR 的 patch 数据嵌进 HTML 的 `<script>` 标签。常识做法是 `json.dumps()`——但 SKILL 里直接给了反例警告：

> CRITICAL: Patch strings can contain `</script>` in addition to newlines, backslashes, and quotes. Even `json.dumps(...)` is not enough if you paste raw output into executable `<script>` because HTML parsing can terminate the tag early.

解决方案是注入前再做一次 unicode 转义：

```python
safe_json = json.dumps(patches) \
  .replace('<', '\\u003c') \
  .replace('>', '\\u003e') \
  .replace('&', '\\u0026')
```

这个细节值得每一个"生成 HTML 报告/PDF/邮件"的 SKILL 抄走。不抄的代价就是哪天你的 patch 里出现了 `</script>` 字面量，整个页面被截断，且 LLM 自己看不见这个 bug。

**(b) 固定端口 8432 而不是 `--port 0`**

直觉是用 `--port 0` 让操作系统分配空闲端口。但 SKILL 里写了具体诊断：

> Background shells have no TTY, so Python buffers its startup message ("Serving HTTP on...") indefinitely — using port 0 means you can never read which port was chosen.

所以方案是：固定 8432，失败回退 8433、8434……。看似 hack，实际是对**工具链局限性的具体诊断和解法**——远胜于含糊的 "start a local server"。

**通用规则**：SKILL 里凡是涉及"起进程 / 读输出"的步骤，都要先问一句"在 background shell 里这个输出读得到吗？"。读不到就别让 LLM 去解析它。

### 6.2 `make-pr-easy-to-review`：用 tree hash 校验"只改可读性不改行为"

整理 PR 历史时最大的风险是**手抖把行为改了**。这份 SKILL 给了一个三行的 git 兜底，简单到不可思议：

```bash
# 改之前先记住
ORIGINAL_TREE=$(git rev-parse origin/<headRefName>^{tree})

# 改完之后比一下
echo "Original tree: $ORIGINAL_TREE"
echo "Current tree:  $(git rev-parse HEAD^{tree})"
git diff origin/<headRefName> --stat
```

`git rev-parse HEAD^{tree}` 拿的是 commit 指向的 tree 对象 hash——**两个 tree hash 相同就铁定证明文件内容完全一致**（git 自己的 Merkle 结构保证），只是 commit 历史不同。这一招把"是否改了行为"从"靠 LLM 自检"变成"靠 git 内部 hash 比对"。

后面 SKILL 再补一刀：*"Do not push if the tree changed unintentionally."*

这是把**校验从主观判断挪到客观验证**的范式。任何"改了 A 但保持 B 不变"的 SKILL 都该植入类似机制——比如改 README 别动 code、改注释别改逻辑、改测试别改实现。

### 6.3 commit topology：5 段重排顺序

同一份 SKILL 还顺手给了一个**可复用的 commit 拓扑清单**：

```text
1. Schema/storage or generated API definitions.
2. Core logic.
3. Wiring and integration.
4. UI or surface behavior.
5. Tests.
```

依赖在前、应用在后；机械的在前、判断的在后。这五段顺序就是**让 reviewer 从浅到深线性读完**的最优路径——而不是按时间倒推 commit 顺序。建议直接当成团队规范。

### 6.4 `control-ui`：选择器优先级

UI 自动化的失败 90% 来自选择器选错。`control-ui` 给的优先级是：

> Prefer accessibility roles, labels, and stable `data-*` selectors over coordinates.

具体到代码层面就是 `page.getByRole("button", { name: /submit/i })` 而不是 `page.click({ x: 320, y: 480 })`。坐标是"今天能用，明天 layout 一改就废"的脆弱契约；a11y role 是 W3C 标准 + 经过 designer review 的稳定契约。

更深一层：**这条约束顺手强制了 a11y 落地**——能用 role 选中的 UI 默认就是 a11y-friendly 的。一条 Guardrails 同时解决"selector 稳定性"和"无障碍合规"两件事。

### 6.5 `weekly-review`：前置依赖必须显式 ask

```text
- If git email is missing, ask the user to set it before proceeding.
```

这一行有两个细节：

1. **前置依赖检查放在 Guardrails 段**，不是失败后再补救。
2. **"ask the user"** 而不是"猜一个默认值"——LLM 默认行为是猜测，这里明确否定。

把所有 SKILL 里"我需要 X 才能跑"的前置条件都按这个模板写一遍：缺什么 → ask user → 不要猜。

### 6.6 `loop-on-ci`：source of truth 显式比较

```text
Use `gh pr checks` as the source of truth. It includes all PR-attached checks,
while `gh run list` only covers GitHub Actions.
```

这一句的写法值得单拎出来。它不只是说"用 A 不要用 B"，而是**显式比较 A 和 B 的覆盖差异**——这才是"source of truth"应该写的样子。LLM 看见 `gh run list` 会本能想用，因为 GitHub Actions 是它最熟的；只有把"为什么 A 严格优于 B 在这个场景"挂在原文，才能压住这种本能。

通用模板：

```text
Use <A> as the source of truth. <one sentence explaining why A is strictly
broader/more authoritative than B in this domain>.
```

填进任何"多个看起来等价但实际有差异"的领域：日志接口、配置加载顺序、缓存层级、metric 聚合方式。

---

## 七、写完之后：让飞轮转起来

完成态的 SKILL 库不是"写完就完了"。Cursor 团队留了两个机制让 SKILL 长寿。

### `deslop`：对自己产出风格的元约束

`deslop` 是整个 kit 里最有意思的一份。它的作用是**用 LLM 检查 LLM 自己写的代码里的 AI slop**：

> Check the diff against main and **remove AI-generated slop** introduced in the branch.
>
> Focus areas: extra comments, defensive try/catch, `any` casts, deep nesting, ... patterns inconsistent with the file and surrounding codebase.

把"AI 生成代码的常见坏味道"显式编码成可触发 SKILL，让 LLM 用这个 SKILL 审自己——闭环非常优雅。它的存在传递了一个态度：**你不能假设 LLM 默认写出来的就是干净代码，你需要一份元 SKILL 反向校准**。

照搬到自己的工位：列出自己最容易产出的 AI slop 模式（中英混杂注释、画蛇添足的 log、过度防御 try/except、说明性 comment），写一份本地 `deslop`，diff against main 触发。

### `workflow-from-chats`：让 SKILL 从对话里长出来

这一份是元层的元层。它的工作是读最近 7 天的 Cursor 聊天记录，抽取"preference atom"（trigger / workflow step / decision rule / quality bar / stop condition / evidence / confidence），按置信度四档分级：

```text
- Strong: 显式偏好，工作流级修正，重复出现的父对话模式。
- Medium: 被接受的工作流，重复出现的工具/模型偏好。
- Weak: 一次性、来源模糊。
- Contradicted: 证据互相矛盾，必须问用户。
```

然后决定要不要产出 artifact。再说一遍：**`No artifact: situational, stale, or low-confidence observation`** 是一个选项。这一档不存在的话，飞轮就会变成"每次都生成新 SKILL"的废品工厂。

每周跑一次 `workflow-from-chats`，让对话里浮现的真实偏好慢慢沉淀成 SKILL/Rule/doc，而不是凭感觉一拍脑袋写。

### `verify-this`：验收的套件

最后留一个永久挂着的 `verify-this`。任何一份 SKILL 改完之后，跑一次 `verify-this`：

- 改前的行为是什么？（baseline）
- 改后的行为是什么？（treatment）
- 差异方向是不是符合预期？（compare）
- 给一个 `VERIFIED` / `NOT VERIFIED` / `INCONCLUSIVE`。

**SKILL 的回归测试就是 `verify-this`**。不挂这个套件，今天写的 SKILL 明天被另一个 SKILL 静默拆台你都不知道。

### `what-did-i-get-done` / `weekly-review`：让 SKILL 自己产出"产品经理周报"

这两个 SKILL 看起来跟"SKILL 写作规范"无关，实际是飞轮里被忽视的一环。它们干的事是：

```text
1. Resolve the requested time window into concrete dates.
2. Read commits authored by the current git user email within that range.
3. Exclude merge commits and uncommitted changes.
4. Synthesize the most important shipped changes into a concise status update.
```

为什么这跟 SKILL 飞轮有关？因为它们的 Guardrails 写得极克制：

```text
- Be extremely concise and information-dense.
- Prioritize substantial behavior or architecture changes.
- Omit cosmetic-only changes (formatting, imports, minor renames).
- Do not infer intent or motivation. Describe changes functionally.
```

把这四条挪到任何"摘要型" SKILL 里都成立。**"Do not infer intent or motivation"** 这一条尤其值得抄——LLM 写周报会本能"脑补这周的故事线"，加 "the team focused on..." 这种没事实根据的总结句。这一条直接把它关停。

---

## 八、再敲三个钉子

写技术深度文的老规矩，再钉三条最重要的：

**第一钉：description 决定召回，召回决定一切**。description 不是文档说明，是路由触发器。把功能描述、典型场景、用户原话三段写完整，召回率比"做 X 的工具"高一个量级。description 里如果没有用户原话，相当于 `endpoint` 没注册——SKILL 写得再好也没人调它。

**第二钉：Guardrails 写"不要做什么"，不是"要做什么"**。LLM 已经被对齐成积极有用的助手，正面祈使句它本来就会做。Guardrails 的真正用途是把 LLM 容易踩进去的坑显式列出来。每条 1 行、负面祈使句、≤ 6 条。超出说明你在写代码规范，挪去 Rule 或 references。

**第三钉：SKILL 是协议不是博文，写完先砍后加**。读者是另一个 LLM，每读一个 token 都在付注意力税。写完通读一遍，每句话问"删掉 LLM 行为会变吗"，不会就删。能压到 60 行以内的 SKILL 几乎都不该写到 100 行。

最后照抄 `verify-this` 收尾那一句：

> *Do not soften a negative result. A clear `NOT VERIFIED` is useful.*

写 SKILL 也一样。`No artifact` 是一个有用的产出。该不写就不写。

---

## 附 A · 一页速查表

| 维度 | Cursor 团队的做法 | 自己常踩的坑 |
|---|---|---|
| 平均长度 | 30–60 行（最短 16 行） | 100–300+ 行 |
| Description | 功能 + 场景 + 用户原话，≤ 50 词 | 只写"做 X 的工具" |
| Frontmatter | 4 字段白名单（`name` / `description` / 可选 `disable-model-invocation` / 可选 `model`+`is_background`） | 一堆自创字段 |
| 骨架 | Trigger / Workflow / Guardrails / Output | Overview / Background / Tips |
| Workflow | 1. 2. 3. 扁平编号、动词开头、4–8 步 | 嵌套二级编号、a/b/c 子项 |
| Guardrails | 负面祈使、可枚举、≤ 6 条 | 缺失或与 Workflow 混写 |
| Output | 状态枚举 + 字段固定 + 长度暗示 | "产出一份 md 报告" |
| Artifact | 固定目录布局（如 `/tmp/verify-this/<slug>/`） | 临时随手丢 |
| Source of truth | 显式比较 A vs B 的覆盖差异 | 选哪个全靠 LLM 直觉 |
| 重操作 | `disable-model-invocation: true` | 默认允许模型自动触发 |
| Agent vs SKILL | 监视/轮询 → Agent + `model: fast` + `is_background: true` | 全写成 SKILL，每次手动触发 |
| Rule vs SKILL | 一两句、跨场景 → Rule (`alwaysApply: true`) | 短约束塞进每个 SKILL 重复 |
| 跨 SKILL | 取证/裁决/构造/清理分层、显式引用 | 单 SKILL 包打天下 |
| 元层 SKILL | `deslop` 自审 + `workflow-from-chats` 蒸馏 | 没有元层 |
| 决策 | "No artifact" 是合法选项 | 一有想法就建一个新 SKILL |
| 校验 | tree hash / `verify-this` 三态裁决 | "LLM 自己说改对了" |

> 一句话：**SKILL 越像 API 文档，越好用；越像博文，越容易失效**。

---

## 附 B · 17 个 SKILL 一行价值点

| SKILL | 一行价值点 |
|---|---|
| `loop-on-ci` | 用 `gh pr checks` 而不是 `gh run list` 作为 PR CI 唯一真源 |
| `fix-ci` | 一次只修一个失败因；`gh pr checks --json` 作为状态判断锚 |
| `ci-watcher` (Agent) | `model: fast` + `is_background: true`，专门做轻量轮询 |
| `review-and-ship` | 4 行 `Suggested Checks` 命令块给出"现成的诊断套件" |
| `pr-review-canvas` | JSON-safe 注入（`\u003c` 转义）+ 固定端口绕过 background buffering |
| `make-pr-easy-to-review` | `ORIGINAL_TREE` 的 tree hash 校验 + 5 段 commit 拓扑 |
| `get-pr-comments` | 按 severity × actionability 分组，输出 action list 而非摘要 |
| `verify-this` | 三态裁决 + falsifiable claim + `/tmp/verify-this/<slug>/` 布局 |
| `control-cli` | tmux 与 PTY 两套最小可运行 harness；deterministic waits over sleeps |
| `control-ui` | a11y role/data-* 选择器优先；不抄别 repo 的选择器 |
| `run-smoke-tests` | "Re-run passing fixes to reduce flaky false positives" 反 flake 哲学 |
| `new-branch-and-pr` | 极简 6 步，强调 "branch scope focused on one change set" |
| `check-compiler-errors` | 按 file × category 分组报错，先修高置信度那些 |
| `fix-merge-conflicts` | "Regenerate lockfiles with package manager tools instead of hand-editing" |
| `deslop` | 元层自审：把 AI slop 的常见味道做成可触发 SKILL |
| `weekly-review` / `what-did-i-get-done` | "Do not infer intent or motivation"；自动从 `git config user.email` 抽 commit |
| `workflow-from-chats` | 置信度四档 + `No artifact` 选项，让 SKILL 从对话里长出来 |

---

## 相关资料

- 仓库地址：[cursor/plugins · cursor-team-kit](https://github.com/cursor/plugins/tree/main/cursor-team-kit)
