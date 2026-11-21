---
name: story-display
description: Build OpenStory read-only offline pages from current exported story snapshots.
---

# 故事展示

本目录是 OpenStory 仓内派生展示器，按 ../script/cli/API.md 的 display-export 入口导出。具体创作和提交遵循 ../director/workflow.md，不调用旧 scene-preview/scene-finalize。源码根由脚本路径确定，输出根由调用方提供。快照不维护独立版本，结构变化时从权威数据库重建，正常校验字段和引用。

运行入口、离线产物、旧源同步和阅读状态边界见 README.md；旧历史资料按来源接续，不反向改写故事数据。
