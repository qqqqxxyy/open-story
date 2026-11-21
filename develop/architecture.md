# 架构与职责

## 文档边界

SKILL.md 承接技能目标、角色入口与流程路由；director 与 author 维护各自运行时行为；role-interaction/director-author 维护共同职责、交接和同一信息的角色应用。默认同一主 Agent 连续承担两种职责；显式多 Agent 各入口引用共同契约。少量流程集中于 workflow.md，长篇判断方法才按角色专题拆分。

develop 维护现行开发约束，docs 保存工程历史；agents/openai.yaml 是平台展示/默认调用配置，不是作者定义或调度；examples 是当前内容模板与程序调用示例，不是契约权威。

## 脚本边界

依赖方向 conf ← util ← data ← workflow ← cli。高层可调用任意低层；conf/util 不能依赖高层，本地反向导入禁止。第三方包与标准库不受本地层级约束。

- conf：JSON/YAML 声明、schema、操作与错误注册、可调参数，不放执行逻辑；Python 若有仅全局常量。
- util：通用日志、契约和运行资源工具，不依赖业务层。
- data：存取接口、结构约束、事务、SQL与高效批量/组合查询。
- workflow/data：映射业务数据请求、归属与投影来源，不执行 SQL。
- workflow/pipeline：业务编排、生命周期、范围、召回、业务投影和组装；handler 是薄路由函数。
- workflow/cli：程序调用上下文与统一执行入口。
- cli：配置引导、参数/help生成和公共返回。脚本全局配置在此加载；故事连接配置由 data 识别。

业务 agent 的增删改查通过公共 API，不自行手改故事存储。SQL仅在 data 后端；组合查询有独立存储接口，不能以抽象为由拆成 N 次逐条查询。SQLite 为当前主后端，文件后端仅保留占位，禁止为占位后端增添不必要的等价实现。

## 权威定义

schema_for_agent：公开请求、结果和最小业务 content；schema_for_workflow：内部编排结构；schema_for_data：存储接口结构。共享结构只有一份定义，通过 $ref 引用，不复制。operations.json：注册与路由/help元数据；runtime/creative 配置：运行与召回策略。单一 skill_version 表达全局发展，不另外新增互相漂移的子系统版本。

开发规范描述维护方法，不复制完整 schema 和参数说明；修改规则更新其权威文件，旧入口留索引，不留第二份规范。


## 统一发布与数据库兼容

runtime.json 是当前 skill 版本和数据库兼容策略的唯一来源；data 在业务解码前根据 PRAGMA user_version 统一校验。配置/初始化历史版本不构成额外门槛；只读不更新标记，实际成功写事务原子更新到当前发布。四表不增逐记录版本字段。前端与导出器同次发布、经测试保证配套，快照需要时从数据库重建，不维护历史快照版本分支。
