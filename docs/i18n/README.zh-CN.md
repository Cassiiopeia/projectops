<div align="center">

<img src="https://raw.githubusercontent.com/Cassiiopeia/projectops/main/docs/images/hero-en.webp" alt="Projectops：从 Issue 到发布" width="100%">

[한국어](https://github.com/Cassiiopeia/projectops/blob/main/README.md) | [English](https://github.com/Cassiiopeia/projectops/blob/main/docs/i18n/README.en.md) | **简体中文** | [日本語](https://github.com/Cassiiopeia/projectops/blob/main/docs/i18n/README.ja.md)

[![npm](https://img.shields.io/npm/v/projectops?label=npm)](https://www.npmjs.com/package/projectops) [![Release](https://img.shields.io/github/v/release/Cassiiopeia/projectops?label=release)](https://github.com/Cassiiopeia/projectops/releases) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](../../LICENSE) [![Docs](https://img.shields.io/badge/docs-site-4f46e5)](https://cassiiopeia.github.io/projectops/)

</div>

---

## 30 秒开始

| 我想要… | 执行这个 |
|---|---|
| 开始一个新项目 | 在 GitHub 上点击 **Use this template**（约 1 分钟自动完成初始化） |
| 集成到现有项目 | `npx projectops` |
| 仅安装 Agent Skills | `npx projectops --mode skills` |
| 检查安装状态（只读） | `npx projectops --mode doctor` |

> 只需 Node.js 20.12+，无需单独安装即可运行交互式向导。

![npx projectops 交互式向导](https://raw.githubusercontent.com/Cassiiopeia/projectops/main/docs/images/cli-wizard.gif)

> 以上是在示例 Spring 项目上的**真实运行画面**（向导界面目前为韩文）。画面中的版本号以录制时为准。非交互式用法和全部选项请见 [CLI 参考](https://cassiiopeia.github.io/projectops/en/cli)（英文）。

---

## 为什么选择这个模板？

本项目从两个方向自动化开发工作流。

**① GitHub Actions**：推送一次 main，版本管理、更新日志、CI/CD 部署全部自动完成。
**② Agent Skills**：通过 `/pro-github`、`/pro-commit`、`/pro-report` 等命令，由 AI 代你撰写 Issue、提交信息和实现报告。

| 传统做法 | 使用 Projectops |
|----------|---------------------|
| 手动管理版本、手动创建标签 | 发布时按提交标题自动升级版本并创建标签 |
| 手写更新日志（30 分钟以上） | 每个发布 PR 自动生成（提交分析；配置 AI 密钥后为 AI 摘要） |
| 从零搭建 CI/CD | 立即按项目类型配置好工作流 |
| 每次按格式手写 Issue（5 分钟以上） | `/pro-github` 一步按标准模板生成并提交 |
| 手动把 Issue 链接复制到提交信息 | `/pro-commit` 根据 Issue 上下文自动补全 |
| 手写 PR 说明和报告 | `/pro-report` 分析 git diff 后自动生成 |
| 每次代码审查和分析都要重新输入提示词 | 20 个 Skills 提供一致的结果，无需重复输入 |

---

## 实际运行效果

本仓库自身就是用这个工具运营的。下面不是模拟图，而是**本仓库真实的 Issue、PR 和发布页面**。

![从 Issue 到发布的真实画面](https://raw.githubusercontent.com/Cassiiopeia/projectops/main/docs/images/demo/demo.gif)

| 步骤 | 发生的事 |
|------|------------|
| 1. 创建 Issue | `/pro-github` 按模板撰写并提交；标签变化后，Projects 看板状态随之同步 |
| 2. 自动指引 | Issue 创建后，评论会告诉你**分支名和提交信息模板** |
| 3. 实现报告 | `/pro-report` 把变更内容和流程图留在 Issue 评论中 |
| 4. 发布 PR | 在 develop → main 的 PR 中确定版本、撰写发布说明并自动合并 |
| 5. GitHub Release | 合并到 main 后，会自动创建带版本标签的 Release |

<details>
<summary>查看每一步的大图</summary>

![1. Issue + Projects 状态同步](https://raw.githubusercontent.com/Cassiiopeia/projectops/main/docs/images/demo/1-issue.webp)
![2. 自动给出分支名和提交信息](https://raw.githubusercontent.com/Cassiiopeia/projectops/main/docs/images/demo/2-issue-helper.webp)
![3. 实现报告评论](https://raw.githubusercontent.com/Cassiiopeia/projectops/main/docs/images/demo/3-report.webp)
![4. 发布 PR 自动合并](https://raw.githubusercontent.com/Cassiiopeia/projectops/main/docs/images/demo/4-release-pr.webp)
![5. 自动创建 GitHub Release](https://raw.githubusercontent.com/Cassiiopeia/projectops/main/docs/images/demo/5-release.webp)

</details>

---

## 组成部分

| 组成 | 作用 | 文档 |
|---|---|---|
| **GitHub Actions** | 推送一次 main，版本管理、更新日志、CI/CD 部署全部自动完成 | [版本管理](https://cassiiopeia.github.io/projectops/VERSION-CONTROL)（韩文） |
| **Agent Skills**（20 个） | 通过 `/pro-github`、`/pro-commit`、`/pro-report` 等命令，由 AI 代你撰写 Issue、提交信息和实现报告 | [Skills 指南](https://cassiiopeia.github.io/projectops/SKILLS)（韩文） |
| **npx CLI** | 向现有项目安装并更新工作流，并诊断其状态 | [CLI 参考](https://cassiiopeia.github.io/projectops/en/cli)（英文） |

<details>
<summary>查看全部 20 个 Agent Skills</summary>

### 🔄 开发周期自动化

| 技能 | 用途 |
|------|------|
| `/pro-init-worktree` | 创建 Git worktree 并自动复制敏感文件 |
| `/pro-commit` | 根据 Issue 上下文自动补全提交信息（遵循 superpowers） |
| `/pro-report` | 分析 git diff → 生成实现报告并自动发布为 GitHub 评论 |
| `/pro-changelog-deploy` | 推送 develop → 创建 main 发布 PR + 撰写发布说明 + automerge |
| `/pro-github` | GitHub 全面操作：创建 Issue（一句话描述 → 按模板撰写并提交）/查看/编辑/评论/标签/负责人，创建/合并/查看 PR，浏览仓库，管理 Actions 与 Secret |

### 📊 分析类（不修改代码）

| 技能 | 用途 |
|------|------|
| `/pro-review` | 从安全、性能、缺陷、质量等 6 个角度审查，按 Critical/Major/Minor 分类 |
| `/pro-note` | 遇到困难时检索过往记录，并把查明的内容保存为可执行的记录 |

### 🔧 实现类（实际编写代码）

| 技能 | 用途 |
|------|------|
| `/pro-figma-verify` | 把 Figma 设计稿转成代码，并逐像素对比成品与设计稿是否一致 |
| `/pro-build` | 运行项目构建、分析错误、给出优化建议 |
| `/pro-launch` | 启动、操作并截取应用、网页和服务器：固定状态栏、调整宽度、替换响应（空列表、失败场景）、用代码渲染 |
| `/pro-design-brief` | 设计稿出来之前，为已做好的页面生成设计需求：各状态截图、备选方案、文案候选、必须遵守的约束，整理成画板交给设计师 |
| `/pro-oss-consult` | 以开源项目的标准诊断 GitHub 仓库：判别类型、6 个维度评分、成熟度阶段，仅在获得批准后修改 About、topics、标签和文件。支持单个仓库或整个账号 |

> 设计、规划和实现流程由 `superpowers`（brainstorming → writing-plans → executing-plans）负责。
> `/pro-plan`、`/pro-analyze`、`/pro-implement` 是同类职责的上一代路径，仅在显式调用时运行。加上上表中的 17 个，共 20 个。

### 📝 文档/产出物生成类

| 技能 | 用途 |
|------|------|
| `/pro-testcase` | 分析 Issue → 生成 QA 检查清单 |
| `/pro-agent-test` | 真正运行应用、网页和服务器来查找缺陷的 QA，并附复现步骤、依据和严重程度（不修改代码） |
| `/pro-synology-expose` | 将 Synology NAS 服务暴露到外部域名的设置指南 |
| `/pro-ssh` | 通过 SSH 连接远程服务器并执行命令（AWS EC2、Synology NAS、Linux 等通用） |
| `/pro-skill-creator` | 创建/审查/改进 Skill（CREATE / REVIEW / IMPROVE 三种模式） |

</details>

<details>
<summary>查看开发周期与流水线流程图</summary>

### AI 开发周期

Agent Skills 覆盖整个开发周期。

```mermaid
flowchart TD
    A(["开始工作"]) --> B["/pro-github<br/>创建 Issue"]
    B --> C["/pro-init-worktree<br/>worktree + 复制敏感文件"]
    C --> D{"工作类型"}

    D -->|新功能 / 设计 / 重构| E1["superpowers:brainstorming<br/>确定做什么、为什么做"]
    D -->|缺陷 / 故障| E2["/pro-note<br/>检索过往记录 + 排查"]

    E1 --> P["superpowers:writing-plans<br/>实现计划"]
    P --> F["superpowers:executing-plans<br/>执行计划"]
    E2 --> F
    F --> H["/pro-review<br/>自我审查"]
    H --> I["/pro-commit<br/>关联 Issue 的提交"]
    I --> J["/pro-report<br/>实现报告 + GitHub 评论"]
    J --> K(["创建 PR"])
    K --> L["/pro-changelog-deploy<br/>发布 PR + automerge"]
```

> Skills 完整列表和用法：**[docs/SKILLS.md](../SKILLS.md)**（韩文）

### GitHub Actions 自动化流水线

```mermaid
flowchart TD
    A([推送 develop]) --> B[集成开发]
    B --> C[develop→main 发布 PR]
    C --> D["在 PR 中确定版本<br/>基于提交升级 + 标签 + AI 更新日志"]
    D --> E[自动合并]
    E --> F["推送 main → CI/CD 部署<br/>Flutter / Spring / React 等"]
    F --> G([完成])
```

</details>

<details>
<summary>仅安装 Agent Skills（Claude Code、Gemini CLI、Codex CLI、Cursor）</summary>

```bash
# Claude Code
claude plugin marketplace add Cassiiopeia/projectops
claude plugin install projectops@projectops-marketplace --scope user
```

```bash
# Gemini CLI
gemini extensions install https://github.com/Cassiiopeia/projectops
```

```bash
# Codex CLI (macOS / Linux)
codex plugin marketplace add Cassiiopeia/projectops
```

`--mode skills` 向导会注册 Codex marketplace，并自动准备原生 skills 回退方案。`/plugins` 仅用于确认和管理安装。

在无法使用 Codex plugin marketplace 的环境中，请使用 [Skills 指南](../SKILLS.md) 中的回退安装方式。

```bash
# Cursor / 完整的 Agent Skills 安装菜单（推荐：npx）
npx projectops --mode skills
```

> Claude Code 优先使用 `/pro-` 自动补全，Gemini 优先使用 extension，Codex 优先使用 plugin marketplace。详见 [Skills 指南](../SKILLS.md)。

</details>

---

## 支持的项目类型

| 类型 | 版本文件 | CI/CD |
|------|----------|-------|
| `spring` | build.gradle | SSH+Docker 部署、Nexus |
| `flutter` | pubspec.yaml | TestFlight、Play Store |
| `react`（含 Next.js） | package.json | Docker |
| `node` | package.json | Docker |
| `python` | pyproject.toml | SSH+Docker 部署 |
| `react-native` | Info.plist + build.gradle | — |
| `react-native-expo` | app.json | — |
| `basic` | 仅 version.yml | — |

---

## 评论命令

在 Issue 或 PR 中通过评论运行自动化。

| 命令 | 功能 | 适用对象 |
|--------|------|------|
| `@projectops server build` | 部署临时服务器 | Spring、Python |
| `@projectops server destroy` | 删除服务器 | Spring、Python |
| `@projectops server status` | 查看服务器状态 | Spring、Python |
| `@projectops build app` | 构建 iOS + Android | Flutter |
| `@projectops apk build` | 仅构建 Android | Flutter |
| `@projectops ios build` | 仅构建 iOS | Flutter |
| `@projectops create qa` | 自动创建 QA Issue | 所有项目 |

> 详情：[PR Preview](../PR-PREVIEW.md) | [Flutter 构建](../FLUTTER-TEST-BUILD-TRIGGER.md) | [Issue 自动化](../ISSUE-AUTOMATION.md)

---

## 配置

### 必需的 Secret

```
Repository Settings → Secrets → Actions → New repository secret
Name: _GITHUB_PAT_TOKEN
Value: [Personal Access Token - repo、workflow 权限]
```

### Organization 设置

```
Settings → Actions → General
├─ ✅ Allow GitHub Actions to create and approve pull requests
└─ ✅ Read and write permissions
```

---

## 需要了解的限制

我们宁愿先告诉你它不适合哪些情况。

- **仅支持 GitHub。** 以 GitHub Actions 和 GitHub Issue/PR 为前提，不支持 GitLab 等。
- **发布以“开发分支 → 默认分支”的 PR 流程为前提。** 分支名可在 `version.yml` 中修改，但不适合不区分两个分支的仓库。
- **Issue 和 PR 自动化需要注册个人访问令牌（PAT）。** 请按上面的[配置](#配置)操作。
- **服务器部署工作流以可通过 SSH 连接的 Docker 服务器为前提。**

---

## 文档

可在**[文档站点](https://cassiiopeia.github.io/projectops/en/)** 中搜索浏览全部内容。大部分指南目前仅有韩文。

- [开始使用（英文）](https://cassiiopeia.github.io/projectops/en/getting-started)
- [CLI 参考（英文）](https://cassiiopeia.github.io/projectops/en/cli)
- [Agent Skills 指南（韩文）](https://cassiiopeia.github.io/projectops/SKILLS)
- [版本管理（韩文）](https://cassiiopeia.github.io/projectops/VERSION-CONTROL)
- [更新日志自动化（韩文）](https://cassiiopeia.github.io/projectops/CHANGELOG-AUTOMATION)
- [PR Preview（韩文）](https://cassiiopeia.github.io/projectops/PR-PREVIEW)
- [Issue 自动化（韩文）](https://cassiiopeia.github.io/projectops/ISSUE-AUTOMATION)
- [SSH + Docker 部署（韩文）](https://cassiiopeia.github.io/projectops/SSH-DOCKER-DEPLOYMENT-GUIDE)
- [Flutter CI/CD（韩文）](https://cassiiopeia.github.io/projectops/FLUTTER-CICD-OVERVIEW)
- [故障排查（韩文）](https://cassiiopeia.github.io/projectops/TROUBLESHOOTING)

---

## 支持

- [Issues](https://github.com/Cassiiopeia/projectops/issues)：缺陷报告、功能请求
  - 本仓库不会关闭已完成的 Issue，而是用 `작업완료`（已完成）标签标记。这就是未关闭 Issue 数量看起来很多的原因。
- [CONTRIBUTING.md](../../CONTRIBUTING.md)：贡献指南（韩文）
- [SECURITY.md](../../SECURITY.md)：请不要在公开 Issue 中报告安全漏洞，而是私下报告

---

<div align="center">

**MIT License**

</div>
