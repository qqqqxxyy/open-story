# 文件故事迁移辅助工具

本目录独立理解旧 storage format 4；正常导演/作者流程不加载旧协议。兼容重放代码在 replay.py 内，不依赖未跟踪的 v5_old。

命令：

```powershell
$py = '<PYTHON>'
& $py -B -X utf8 -m script.compat.file_story.cli plan --source '<源故事>' --branches '<保留branch>' --default-branch '<默认branch>' --output '<计划.json>'
& $py -B -X utf8 -m script.compat.file_story.cli import --plan '<计划.json>' --target '<空目标目录>'
& $py -B -X utf8 -m script.compat.file_story.cli verify --plan '<计划.json>' --config '<目标sqlite.json>' --output '<检查.json>'
```

plan 只读源资料。import 不覆盖已有故事，通过 Repository/结构接口创建历史节点和事件，在整库事务末尾满足唯一归属、本地正文摘要指针和真实叶子 head 契约。verify 检查保留的每个路径cutoff、原文/输入、包索引和导出默认入口，并在临时副本开幕召回；不是作者agent E2E。--no-opening 可仅做历史与导出检查。

content 的 `_migration_provenance` 保存在业务payload内；标准 `_control` 外壳不加自定义字段。原生正文/输入/摘要等直接JSON记录在 provenance 中保存来源。来源地址不取代生产幕归属。信息包索引只存JSON，动作依赖关系沿用event_action_target。

工作流与历史管理记录按类别复用容器。partial角色/关系先按本前驱状态深合并，再以完整内容replace。跨fact ID替换用cancel旧对象内容、append新事实。关闭线索以cancel及结案内容保存。角色记忆保留原主观种类/置信度，不从后台真相推断知情。

已完成的历史包作为历史记录保存，不伪造native scene_context/session/author_binding；新幕仍由scene-next开启。旧对话片段若与正式正文精确对应，保存正文范围；混合用户/正文/技术标记的不同源transcript保留原文于历史record，不编造轮次，不选为当前正文。正式叙事指针仍只有一份。

此适配器支持本次两个源格式的inherit树、空业务root基线及所确认的归属策略；不是所有更老格式、前传或中途reset的通用迁移器。

## 显式迁移策略

plan可使用`--policy <策略.json> --legacy-source <原始备份目录>`，先生成核心计划，再在内存中应用源故事专属取舍。策略声明story_id、fact_topics中的key/name/fact_ids、archive_fact_ids、strip_node_metadata_fields及可选legacy来源文件/最终导演归属节点。结构模板见`policies/example.json`；具体故事的策略文件留在本机，默认不纳入版本控制。

该转换保持原event ID、生产node和动作目标，主题归组不合并原始事实；历史规则调整转入作者记事。原V3 committed_at保存在node_metadata，最终director快照有独立来源及末幕归属。计划声明supplemental_sources的路径与哈希，import在配置/数据库创建前核验。所有补充event进入同一计划，verify无需放宽预期事件集合。

这种策略不改变正常创作CLI、角色提示词或召回算法，也不迁移未指定的旧格式。目标仍须为空；历史检查可使用verify的--no-opening，不自动续写、生成capsule或同步前端。
