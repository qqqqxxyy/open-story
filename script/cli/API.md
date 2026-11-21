# CLI help 入口

逐API的用法、控制参数、JSON内容、返回结构、示例和前提，唯一通过CLI help生成与暴露。先看总览，再只查本次相关命令，不加载全量API文档。

```powershell
Set-Location '<REPO>'
$py = '<PYTHON>'
& $py -B -X utf8 script/cli/main.py --help
& $py -B -X utf8 script/cli/main.py story-init --help
& $py -B -X utf8 script/cli/main.py object-events --help
```

help不打开数据库、不执行handler，不需要--config或业务必填参数。预留接口在总览和单help中明确标注。

唯一外部入口是子命令与控制参数；开放内容用--content-file <UTF-8 JSON路径>，路径-从stdin读取。batch用--commands-file读取内部operation/params数组；没有--request整体请求入口。脚本时间/seq及可自动生成的ID不让agent构造。

公共API契约见[agent schema](../conf/schemas/schema_for_agent.json)，输入和返回由执行过程校验；开放content语义由业务解释。业务工作流说明何时调用哪个API，不复制参数表或返回定义。

维护者的契约归属、注册、默认值、help与正常功能测试纲领见[维护说明](MAINTAINING.md)。本文件不再维护逐接口说明。

业务记录操作按需查 business-save、scene-archive、business-read 的 help：event-action 默认 append；替代/取消用 target-event-ids，cancel 可不输入内容文件。候选保存于导演包。summarize 是独立摘要记录，使用 capsule-check/read/save 批量接口。event-cancel 是叶子记录存储状态维护，不等同于业务 event-action=cancel。

## 大文本读取与工具传输

所有子命令支持可选 `--output-file <JSON路径>`，这是CLI传输选项，不进入业务API参数。省略时保持原有stdout完整JSON；填写时，将完整统一响应包络（`ok/operation/data/error`）以UTF-8无BOM写入文件，自动创建父目录，通过同目录临时文件原子替换目标。业务成功且文件写入成功后，stdout仅返回统一包络中的文件回执：`data.output_file`为绝对路径，附完整JSON字符数、UTF-8字节数和SHA-256。文件内保存原响应，不是回执；工具输出截断不会截断该文件。

业务失败时文件可保存完整错误响应，stdout仍返回原错误及非零退出码；文件写入失败返回 `OUTPUT_WRITE_FAILED`，不会报告转储成功，已有目标文件保留。业务操作可能已完成，先按状态或已有阶段回执恢复，不将输出失败当成未执行。Agent自行决定读取文件的方式、范围与是否继续补读；转储成功只表示完整保存，不表示模型已读完整份材料。

`scene-prepare` 与 `scene-context` 默认compact均返回选中的 `projection` 和Capsule等材料；full额外返回原始 `sources`。可用 `scene-context --config <配置> --node-id <幕ID> --output-file <召回结果.json>` 保存完整结果。已由scene-prepare取得的材料不需再召回。

历史全文使用 context-read 的 prose 视图，具体参数和分页契约查询该命令 help。默认页大小来自 creative.reading.prose_page_characters。API 保持统一 JSON 包络，每页只展开所选正文的连续片段；根据 page.next_cursor 续读，按顺序保留所有原始字符。

宿主传输时解析 JSON，只输出本页正文、来源 ID 与简短分页信息。exec_command 的 max_output_tokens 与外层 functions.exec 的 max_output_tokens 分别生效，按本页大小配置两层预算；同一次外层调用内多个结果共享外层输出预算。正文页面分次交给模型，其他查询结果按实际需要另行组织。

宿主采用 functions.exec 时，可以按以下方式传递一个已分页的正文结果；参数定义仍以 CLI help 为准：

```javascript
// @exec: {"max_output_tokens": 8000}
const result = await tools.exec_command({
  cmd: "<从 context-read help 组织本页命令>",
  max_output_tokens: 8000
});
const response = JSON.parse(result.output);
if (response.ok) {
  text({ scope: response.data.scope, page: response.data.page });
  for (const item of response.data.narratives) {
    text({ node_id: item.node_id, narrative_event_id: item.narrative_event_id,
           text_start: item.text_start, text_end: item.text_end,
           node_complete: item.node_complete });
    text(item.literary_text);
  }
} else {
  text(response);
}
```

出现工具截断提示时，依据已取得的来源与文本位置定向补读。API 的 complete 表示全部所选文本已由分页接口返回；宿主工具记录用于判断模型实际收到的内容。

CLI 自动记录请求节点、读取范围、正文数量、正文版本与字符量；response.serialized 记录最终 JSON 的字符数与 UTF-8 字节数，不含输出末尾换行。日志只记录元数据，CLI 生成响应与宿主接收情况分别理解。


## 统一版本与数据库兼容

当前发布版本及数据库兼容起点只在 runtime.json 声明。打开数据库时根据 PRAGMA user_version 使用公共规则校验，不通过连接配置或 event.content 判断版本。VERSION_UNSUPPORTED 表示需要使用支持该库的发布或显式迁移；重试业务请求不会修正版本。

新连接配置不再写 skill_version；旧配置字段兼容保留。只读不升级库标记；真实成功的写事务与当前库版本标记一起提交，失败一起回滚。前端快照为可重建派生数据，不拥有独立兼容策略。


## 展示数据重建

展示源码位于仓内 story-display；快照与 HTML 是只读派生物，不设独立数据版本。结构变化后按 display-export help 从受支持的数据库仅导出，再用生成器构建。多故事先导出再统一生成。缺少权威来源保留旧页面并说明，浏览器阅读状态不能当作可随意重建的缓存。


## 稿件展示与延迟归档

新流程经 scene-prepare 的 action=next/revise/resume 创建或恢复 attempt，review 后 scene-submit 保存正文和完整阅读元信息、展示当前稿，进入 awaiting_feedback。同幕修改产生新稿及一次有意的展示；同稿重试不重复发布。独立下一幕原子采纳前稿，明确定稿用 scene-accept；采纳不等于语义归档完成。scene-maintenance 依据展示后的返回任务，先保存目标采用稿 events，再推进 Capsule，整个维护不修改前端。scene-display/scene-archive 保留底层及旧流程兼容，新 attempt 的归档必须走维护任务。展示回执以 publication_status、changed_node_ids、removed_node_ids、node_revision表示实际变化。只导出后再请求生成时会检查HTML内容，避免将旧HTML误判为已完成。


scene-context默认compact，返回当前projection而不重复展开原始sources；选集、capsule、固定范围与诊断不变。需同时追查原始来源时显式选择full，参数与结果按该命令help。


接续历史先用 history-list 取得最近幕摘要及真实来源指针；本幕补查传 scene-node-id，纯历史查询传 branch/cutoff，不开新幕。history-read 默认 prose，仅需段落引用选 paragraphs，需要完整诊断才选 full。多个同范围关键词合用 history-search 的 keywords，各词独立分页；完整多幕正文仍按 context-read prose 分页读取。持续单Agent复用已经完整读过的内容。


capsule-check 默认 jobs 仅返回待办及检查汇总；审计选 full。capsule-save 默认附受影响对象的 next_jobs，直接继续需要的二级处理，不必保存后机械再查一次；关闭 include-next-jobs 只返回保存回执。各视图与控制参数详见相应 help。


正常单Agent显式使用 scene-prepare 的 action、稳定 request_id 及基准作者包固定开幕/修订；小修 preparation=null 且不召回，大修返回正常资料。作品 review 后 scene-submit 携 attempt_id 一次提交展示。当前稿不自动召回，定向恢复传 author-reply-read 的 packet-event-id；采用的前幕正文即使未语义归档也能正常读取。scene-submit/scene-accept 的 maintenance.next_job 与 scene-maintenance 的 next_job 是同一任务结构；按 phase 提交 events 或 capsules，API固定scope并推进，无任务 next_job=null。交互片段按原接口保存，完成后用author-packet-event-id复用整幕。error.details只包含已确认阶段/ID与resume_operation，失败不意味着已保存正文丢失；沿同一node恢复。组合接口及展示不放进batch事务。scene-archive支持default_source_event_ids，条目显式列表（包括[]）优先。

新路线的全部参数、状态、任务结构与示例按需查看 scene-prepare、scene-submit、scene-accept、scene-maintenance、dialogue-close 的 help。scene-status 的 published 表示正文已采纳，展示回执的 publication_status=published 表示阅读页已生成，两者分别描述采纳与展示；complete 还要求维护完成；awaiting_feedback 不归档当前稿，accepted_pending_archive/capsules 按返回任务恢复。action 省略维持旧显式分步语义，不自动采纳。维护范围独立于创作 scene_context，迟写语义不回填已经开启后幕的历史截止。

恢复时scene-prepare按已保存阶段返回作者、交互、展示或maintenance，不重复已有资料准备；旧未完成节点没有attempt及完整稿时，显式request_id可接入。展示后中断返回维护trigger，head尚未展示则返回resume_node_id。新稿display固定阅读输入及实际导演来源；快照/HTML同时核对正文和阅读元信息。恢复省略output_root/generate复用该稿保存的选择，普通讨论不使展示失效。维护范围限制冻结后的无关本地资料，仅本任务输出可继续进入Capsule；内部维护身份由API生成。

维护恢复有具体资料缺口时，context-read显式传maintenance-job-id查询任务固定范围，包括更早幕已补齐的语义及该任务受控输出；普通context-read不传此参数，仍保持开幕截止。任务须属于目标采用节点及所选分支，不能借任务读取当前草稿或后幕。参数与例子见context-read help。

scene-status 的 author_binding 是所选分支沿历史保留的可选多 Agent 作者绑定，不表示本次单 Agent 的执行身份，也不要求默认流程恢复该作者；启用多 Agent 时按导演可选路线确认或更新真实绑定。

公开版的安装初始化见 [INITIALIZE.md](../../INITIALIZE.md)。story-init 只在请求未指定相应字段且本机已保存默认值时补充 protagonist/narration；技术调用没有个人配置时保持请求原样，不植入固定姓名或视角。本机默认调整不改写已初始化故事。
