---
name: open-story
description: Develop an independent Chinese interactive-fiction world, initialize its SQLite story, write one complete scene or a same-scene interactive dialogue, and preserve scoped continuity through director-author workflows.
---

# Open Story

与读者共同创作回应其实际期待的故事，让读者度过有意思的时光，愿意继续与人物交流、探索他们的发展。结合多幕介入与反馈理解兴趣，以有沉浸感的行动、关系变化和意外回应读者；资料、连续性与存储服务于实际阅读体验。

## 首次启动

首次加载时先按 [INITIALIZE.md](INITIALIZE.md) 确认本机是否已初始化；未初始化时通过普通聊天了解使用者对主人公和默认视角的要求，再生成本地 `author/writing-contract.md`。个人设置与本地契约均不纳入 Git。初始化完成后，持续会话沿用已保存结果。

## 角色入口

默认由当前主 Agent 串行承担导演统筹与作者文学创作，持续完成设计、创作、成文 review 与展示；当前稿等待反馈，展示下一幕后再维护前幕的语义归档和 Capsule。先读[导演流程](director/workflow.md)与[共同契约](role-interaction/director-author/contract.md)，进入文学创作时按[作者入口](author/ROLE.md)与[作者流程](author/workflow.md)执行。逻辑职责分别保留，已掌握的上下文持续复用。

导演负责世界线统筹、按需规划设计、资料组织、展示和归档；作者负责本幕文学创作并提交自己的作品。双方权限、交接与知情边界只在共同契约定义；各自判断细则见[规划](director/planning-and-backstage.md)、[召回组织](director/querying.md)、[归档](director/archiving.md)和[写作契约](author/writing-contract.template.md)。

## 流程路由

先区分创建新故事、普通下一幕、创作讨论、小修、大修、同幕交互、明确定稿、查询或维护，按[导演流程](director/workflow.md)对应章节执行。开局通过普通聊天确认重要缺项，不使用内置问题回答工具；已明确或允许自由生成的内容不重复询问。主人公与默认叙述视角以初始化生成的本地写作契约为起点，具体故事的明确要求优先。公开模板仅用于章节索引与首次生成。

脚本负责确定性编排，Agent负责创作与语义判断。特殊需要时按[可选多 Agent 模式](director/workflow.md#可选多-agent-模式)调度；如无特殊说明，不启用。操作格式按需查询 `script/cli/main.py <子命令> --help`，入口见[CLI](script/cli/API.md)。业务提示词只维护判断和调用时机，不复制接口参数表。

capsule_mode 开启后按[长期背景摘要](director/capsule.md)批量归纳与召回两级 object 摘要。查询与维护也通过 API。历史归档仅作迁移或工程参考，不执行旧创作入口。开发和架构维护按[develop](develop/README.md)，普通创作不加载工程规范。

维护与管理走[导演流程](director/workflow.md)：多node删除必须独立一轮确认具体范围；重创从存活父状态创建新ID。纯历史查询不开新幕。记录处理由调用方明确选择，不按类别预设。
