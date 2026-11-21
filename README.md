# Open Story

**与你一起创造一个只属于你的故事世界。**

读到小说的某个转折时，你也许想过：如果主人公作出了另一个选择，后面的世界会怎样发展。也许你想走进故事，与其中的人物相处；也许你想暂停情节，讨论一个人的心意，再看看故事还能走向哪里。

Open Story 是一个用于持续创作中文互动故事的 Agent Skill。你可以从一个人物、一处场景或一个想法开始，与 AI 逐幕发展故事，也可以在已有经历上开启另一条世界线。人物经历、关系变化与世界设定保存在本地，供后续创作查询和理解。

这个项目希望让你在乎的人物有机会继续生活，让你的选择和想象在故事中留下回响。创作的方向，可以随着你的参与一起改变。

## 你可以做什么

- **逐幕创作**：一次阅读完整的一幕，再决定接下来关心什么。
- **进入对话**：在同一幕中逐轮与人物交流，给自己的回应留出空间。
- **讨论故事**：暂停推进，讨论人物、关系、世界观或某个情节为什么不合适。
- **修改当前稿**：调整对话与细节，或重新构思本幕的主要发展。
- **探索分支**：从指定的历史节点分出另一条世界线，尝试不同选择。
- **接续长期故事**：结合历史正文、人物经历和长期摘要，寻找后续发展的依据。
- **离线阅读**：通过本地 HTML 页面浏览故事、章节与分支关系。

## 快速开始

### 本地验证环境

以下是本项目当前在本地运行验证的版本，不表示各组件的最低版本要求。

| 组件 | 本地验证版本或方式 |
| --- | --- |
| 操作系统 | Windows 10，构建 19045，64 位 |
| Agent 宿主 | Codex，加载本仓库的 Skill |
| Python | 3.12.15 |
| Node.js | 24.22.3 |
| pnpm | 11.25.0 |

Python 依赖由 [requirements.txt](requirements.txt) 声明；阅读页依赖由 [story-display/package.json](story-display/package.json) 和锁文件管理。模型及其访问方式由 Agent 宿主提供。

当前工作流默认生成阅读页，因此标准安装同时准备 Python 和 Node.js 环境。Agent 需要能够读写本地故事文件、运行项目命令，并访问所选模型。

### 1. 获取仓库

本文使用以下占位符。执行命令前，请将尖括号中的内容替换为自己的配置。

| 占位符 | 含义 |
| --- | --- |
| `<SKILLS_DIR>` | 你的 Agent 宿主识别的 Skill 目录 |
| `<REF>` | 与本文对应的发布标签或分支；公开默认分支为 `main` |
| `<PYTHON>` | 你为本项目准备的 Python 解释器命令或路径 |

下面的命令使用 PowerShell 语法。先准备好上表中的环境，再获取希望使用的版本：

```powershell
git clone --branch "<REF>" https://github.com/qqqqxxyy/open-story.git "<SKILLS_DIR>/open-story"
Set-Location "<SKILLS_DIR>/open-story"
```

让宿主识别这个目录中的 [SKILL.md](SKILL.md)。本地使用 Codex 加载该 Skill，调用名称为 `$open-story`；具体 Skill 目录及加载方式以你的宿主配置为准。

### 2. 安装依赖

以下路径均相对于仓库根目录。安装和运行时使用同一个 Python 环境：

```powershell
& "<PYTHON>" -m pip install -r ./requirements.txt
& "<PYTHON>" -B -X utf8 ./script/cli/main.py --help

Set-Location ./story-display
pnpm install --frozen-lockfile
Set-Location ..
```

如果 Python 或 Node.js 使用独立安装路径，请在 Agent 的运行环境中配置好解释器，并让 `node` 命令可用。CLI 帮助正常输出后，即可开始创建故事。

### 3. 首次启动与本机默认

首次调用 `$open-story` 时，Agent 会按 [INITIALIZE.md](INITIALIZE.md) 了解你的主人公和默认叙述视角要求。你可以指定固定姓名、身份、人称和视角，也可以明确选择每个故事再决定；项目不预置任何人的姓名。

选择保存在本机 `.openstory/preferences.json`，并实际写入生成的 `author/writing-contract.md`。公开仓库只保存 [通用模板](author/writing-contract.template.md)，个人设置和本地契约由 `.gitignore` 排除。具体故事的要求优先于本机默认。安装完成后的状态可用以下命令查看：

```powershell
& "<PYTHON>" -B -X utf8 ./script/initialize.py --status
```

已有配置且本地契约缺失时，可用 `--restore` 恢复；修改默认不会改写已有故事。

### 4. 开始第一个故事

在加载了 Skill 的 Agent 会话中输入，例如：

```text
使用 $open-story 创建一个新的故事。
我想写一个发生在海边小镇的少年成长故事，以第三人称展开。
先和我讨论主人公、主要人物与故事的开端，再开始第一幕。
```

也可以直接提供开场，让 Agent 在这个基础上发展。题材、主人公、叙述视角、基调和参与方式都可以明确指定；尚未想好的部分可以在交流中逐渐形成。

故事初始化、资料组织、文学创作、成文 review、保存和展示由 Agent 按工作流完成。普通使用通过自然语言进行，具体接口由 Agent 调用。

### 5. 打开阅读页

默认阅读页生成在：

```text
story-display/dist/index.html
```

可以直接用浏览器打开，不需要启动服务进程。你也可以对 Agent 说：

```text
打开这个故事的阅读页。
```

已有展示快照时，在仓库根目录运行下面的命令可重新生成并打开页面：

```powershell
Set-Location ./story-display
pnpm open
Set-Location ..
```

`pnpm open` 根据已导出的快照构建页面；需要从数据库重新导出时，可以让 Agent 操作，或查询 `display-export --help`。

## 与故事一起发展

你可以描述人物的行动，也可以提供下一幕的大纲、希望经历的感受，或指出当前文字哪里不对。明确说出本次想继续、讨论还是修改，有助于 Agent 理解你的介入。

| 想做的事情 | 可以这样说 |
| --- | --- |
| 继续独立下一幕 | “继续下一幕，让这次争执的影响自然延续。” |
| 进入逐轮交流 | “接下来开启对话模式，让我逐句回应她。” |
| 暂停讨论 | “暂停故事。我们先讨论她为什么作出这个选择，不推进情节。” |
| 小修当前稿 | “小修这一幕，保留主要发展，让他的说话方式更直接一些。” |
| 重构当前幕 | “重新构思这一幕，保留人物处境，但改变冲突的发展方式。” |
| 创建另一条分支 | “从第三幕结束的位置创建新分支，尝试另一种选择，保留原分支。” |
| 明确定稿 | “这一幕定稿，暂时不继续下一幕。” |
| 接续已有故事 | “继续故事 `<STORY_ID>` 的 `<BRANCH_ID>` 分支。” |

一幕完整写成后，先保存并展示为待反馈稿。你可以继续修改；基于它开始独立下一幕，或明确表示定稿时，工作流才固定采用稿。普通讨论或暂停不会自动采纳当前稿。

逐轮对话中的“继续说”和开启独立下一幕属于不同情境；拿不准时，可以直接说明是否仍在当前场景中。切换会话或同时创作多个故事时，提供故事和分支 ID，便于找到正确的接续范围。

## 它如何工作

### Agent 判断与脚本职责

默认由同一个 Agent 连续承担导演和作者两种职责：导演理解读者兴趣、组织资料和构思发展；作者选择本幕实际展开的经历，完成文学创作与成文 review。多 Agent 分工是可选路线。

| 工作 | 主要承担者 |
| --- | --- |
| 理解输入、讨论人物与走向、比较情节可能性 | Agent |
| 写正文、演绎人物、安排节奏、review 和文学调整 | Agent |
| 从采用稿中提炼记忆、事实、关系与长期摘要 | Agent 作语义判断 |
| 保存记录、校验结构和引用、限定查询范围、编排流程与恢复 | Python CLI 与 SQLite |
| 将展示快照构建为离线页面 | 阅读页脚本 |

长期记忆、摘要和人物理解需要 Agent 归纳；脚本负责按确定的规则存储、检索和组织它们。作品的文学效果仍取决于所用模型、创作判断以及持续交流。

### 历史、分支与长期背景

故事按幕保存，每条分支有自己的历史路径。接续创作沿所选分支和截止点读取资料，避免把其他世界线尚未发生的事情带进来。

历史正文与精确记录保留具体经历；人物记忆、事实和关系提供不同侧面的理解；两级长期摘要（Capsule）在启用时提供较长时段的背景概览。遇到具体疑点，Agent 可以再定向查阅原始材料。

当前稿展示后仍可修订，其语义归档会等到采用稿固定后再进行。普通续写先展示新幕，再维护已采纳前幕的语义资料和必要摘要，让阅读与后台整理按工作流接续。

## 数据、阅读与备份

默认目录结构如下；使用自定义数据根或输出目录时，以初始化及展示回执为准。

```text
story-data/
├── online/<STORY_ID>/
│   ├── sqlite.json        # 故事连接配置
│   └── story.sqlite3      # 正文、经历、设计及流程记录
├── debug/                 # 测试故事
└── default_logs/          # 运行日志

story-display/
├── story/<STORY_ID>/story.json  # 导出的展示快照
└── dist/
    ├── index.html              # 离线阅读页
    └── display-version.js      # 页面更新检测标记
```

数据库是故事的权威来源，展示快照和 HTML 可以重新导出、构建。备份故事时，应保存故事配置与对应数据库；使用 SQLite 备份方式，或在停止写入并关闭连接后复制完整故事目录。恢复后可从数据库重新生成阅读页。

本地故事数据和生成的阅读页默认不跟踪 Git；`docs/` 中的个人素材与维护记录、读者反馈、源故事专属迁移策略及阅读提醒修复数据也作为本地资料忽略。阅读页可包含正文、摘要、输入和分支信息，适合按需要导出阅读内容。使用在线模型时，进入模型上下文的故事材料会通过所选 Agent 宿主处理；本地持久化描述的是故事的保存方式。

当前 skill 发布版本统一声明在 `script/conf/runtime.json`，数据库兼容性由脚本校验。展示快照作为可重建产物随项目演进。详细说明见 [CLI 与版本说明](script/cli/API.md#统一版本与数据库兼容)。

## 自定义与文档导航

| 想了解或调整什么 | 入口 |
| --- | --- |
| Agent 如何加载并进入工作流 | [SKILL.md](SKILL.md) |
| 创作风格、人物表达和文学取舍 | [作者写作契约](author/writing-contract.template.md) |
| 导演如何构思与组织资料 | [导演工作流](director/workflow.md)、[规划与后台设计](director/planning-and-backstage.md) |
| 如何理解读者期待与开展讨论 | [创作讨论与读者期待](director/reader-expectations.md) |
| 导演和作者的职责与裁量 | [共同契约](role-interaction/director-author/contract.md) |
| CLI 控制参数、JSON 内容与命令发现 | [CLI 入口](script/cli/API.md) |
| 内容模板与程序调用示例 | [内容示例](examples/data/README.md)、[程序调用示例](examples/programmatic/README.md) |
| 阅读页生成与旧源同步 | [展示器说明](story-display/README.md) |
| 架构、数据、脚本与开发规范 | [开发入口](develop/README.md) |

`director/` 和 `author/` 维护创作职责与方法；`script/` 维护 CLI、配置和持久化流程；`story-display/` 维护阅读体验。你可以通过与 Agent 讨论调整某个故事，也可以在二次开发中修改项目的规则与实现。

## 开发与反馈

开发前可阅读 [开发规范](develop/README.md)。接口用法通过帮助查询，以下命令均从仓库根目录执行：

```powershell
& "<PYTHON>" -B -X utf8 ./script/cli/main.py --help
& "<PYTHON>" -B -X utf8 ./script/cli/main.py story-init --help
& "<PYTHON>" -B -X utf8 ./script/cli/main.py display-export --help
```

测试入口见 [正常功能测试](tests/data/README.md) 和 [测试规范](develop/testing.md)。开发时按修改范围选择模块，完整检查可使用：

```powershell
& "<PYTHON>" -B -X utf8 ./tests/data/run.py --module all

Set-Location ./story-display
pnpm test
pnpm typecheck
Set-Location ..
```

欢迎通过 [Issues](https://github.com/qqqqxxyy/open-story/issues) 反馈安装、功能和创作体验问题，或提交改进。技术问题可以提供环境版本、操作步骤和错误信息；创作体验可以提供相关片段、希望获得的效果，以及实际哪里不合适。先整理一份适合公开的最小材料，通常比提交整个故事库更便于讨论。

## 使用授权

**允许任何非商业用途的使用与二次开发。**

商业用途不包含在上述授权范围内。该授权针对本仓库的项目内容；第三方依赖遵循各自的许可证。
