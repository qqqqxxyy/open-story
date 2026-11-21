# 脚本与接口开发

## 职责

conf只保存JSON声明。schema_for_agent定义公共请求/响应、操作入参/结果及业务负载；schema_for_workflow只保存event_owner、deletion_context等内部结构；data schema定义数据接口结构。公共与内部都使用的结构只有一个权威定义，按$ref复用，不复制；API字段不得因为内部连接或阶段变化而迫使调用方改变。

CLI bootstrap建立内存资源，arguments读取operations目录生成参数和help，workflow入口接收公共契约，dispatcher校验输入/结果，handler执行业务。内部结构由内部使用处校验。data/workflow/util不导入CLI；脚本配置从CLI加载，故事sqlite.json仍由data读取。依赖方向conf ← util ← data ← workflow ← cli，高层可直接调用任意低层。

## 新增与修改API

在agent schema定义或复用input/output结构；字段description随必要结构维护；operations条目定义operation/cli_name/input_schema/output_schema/storage_mode/handler/containers/bindings以及help元数据。handler签名(context,params)→result，按业务分组放workflow/pipeline/handlers。

help元数据只维护summary/effect/notes/examples/errors；参数类型/必填/枚举/结构由schema和bindings自动生成（必填沿input_schema中的path推导，bindings不再复制required），不能另写参数表。shared data字段的含义可由binding.description或runtime.help.field_descriptions补充，不复制数据schema。修改实现时同步业务前提/副作用说明；自动生成并不能推导这些自然语言语义。

同类新操作只新增契约/条目/handler；新绑定机制或存储模式才扩展通用引擎。不引入配置条件/循环语言、动态插件扫描或依赖注入框架。组合操作进程内调用Repository/handler，同库事务交给业务工作流，SQL仍在data保留JOIN/CTE/批量查询。

## 默认值与开放内容

dispatcher仅填充公开操作入参顶层的default，然后执行校验；不递归改写content或原始消息。分页limit/offset/descending/include_total等实际默认从公共契约读取，help从同一源显示。嵌套内容默认如消息source由业务代码读取对应schema默认；protagonist/narration默认由初始化业务代码与正常功能测试维护。JSON Schema的default本身不执行赋值。

未知表意键只在契约允许的开放区域保留；JSON字符串不改写；data只存合法JSON，content不被底层解释。event内容/归属不可覆盖，修订追加；业务条件、状态、知识、增量/全量不由help或schema自动推断。

## help生成

总help只列名称/summary和reserved状态。单help展示参数、必要内容树、结果树、包络、相关错误和实例，按runtime.help.max_depth折叠，重复引用停止展开。schema_ref解析保留文档上下文；机器校验使用完整引用，不受展示折叠影响。

help不得调用handler、打开故事库或读取内容文件。单help按命令展示，不打印所有API或整套schema。解析器的参数帮助、说明和返回树只在查询help时实际格式化。

## 日志、错误与验证

日志 debug/info/warn/error，默认 info，统一写到 runtime.logging.default_path，不按故事建日志目录；故事与数据库一一对应，统一以database_id/branch_id定位，不另外记录story_id；初始化入口的story_id在日志中归一为database_id。已确认后记录，缺少时省略。invocation_id 沿用 Application 上下文，call_id/parent_call_id 关联内部调用。info记录目标、控制参数、耗时和结果摘要；debug记录关键校验、路由、存储和事务阶段，不重复整份正文。rotation_days 默认7，正整数天；真实日志实例化时按第一条日志时间在锁内检查，到期重命名归档，不使用定时器、不自动删除归档。FileLock保护轮转及追加/flush，不锁业务SQL；help只加载配置和契约，不实例化日志、不取得日志锁、不触发轮转；stdout留给JSON或help，日志失败不改变业务结果。API错误来自errors目录，进程退出码独立；引导失败有最小兜底。

增量开发补对应正常功能测试，包括省略默认参数的执行、新注册操作的help、公开返回和必要负载；结构检查验证公共定义归属与ref能解析。help场景验证无存储副作用及内容可按说明成功调用，不测试攻击/极端情形。标准输入示例从同一操作注册生成 PowerShell UTF-8 管道，可在一次调用中完成内容准备与提交。

测试纲领见[测试规范](testing.md)，入口 tests/data/run.py 支持单模块与 all；保留原CRUD/分支/SQL组合场景；不做迁移等价、压测或全库一致性审计。v5_old只归档。

## 创作content与召回配置

公共业务content_定义维护在schema_for_agent，额外表意字段保持开放；通用event API不把这些语义下沉为data规则。creative.json引用业务schema，并维护类别别名、身份/文本提取路径、身份/文本提取与召回数量；bootstrap加载检查，workflow读取内存资源。配置不重复字段类型/必填定义。业务kind追加时同步content定义、类别映射、业务正常功能测试；CLI help自动展开kind对应契约。业务投影明确区别于原event，含source_event_ids；信息包引用原记录，来源索引仅保存在 content，保存时批量校验范围；不额外生成 creative_source 关系，追溯索引不自动递归展开。工作流容器由 creative.json 的 workflow_objects 映射按故事类别复用，映射以内部 workflow schema 校验；event 的 type_name、ID 和 node 归属保持独立。

library存储模式用于不需要单故事config的目录发现；不得将其伪装成reserved。API新增仍只注册契约、bindings/help与handler。记录payload与_record是业务公开封装，不是data额外字段；event_action控制如何形成内容视图，schema定义一次并在归档条目复用。默认append无类别特例。

## Capsule 增量维护

摘要policy、批量预算和目标篇幅在creative.json，内部配置以workflow schema校验；公开批量项、摘要元信息与视图在agent schema。工作流分离状态投影、批次计划和API编排，不让data解释content。批量按object_ids取得范围内来源，保留组合JOIN，不逐object执行API；精确投影始终排除summarize，摘要视图独立计算。低层event.create的summarize也走相同结构/范围验证，普通business/归档不混入摘要。新类别策略、层级来源、重建、分支截止与精确数量变更补capsule/recall相关正常功能用例。

## 大文本读取与日志增量维护

正文读取的传输预算配置在 creative.reading，由内部 reading_config 校验；公开视图、分页与片段字段由 agent schema 和对应 help 维护。全文分页固定读取范围、节点顺序与正文版本，保留全部原始字符。资料分页与文本分页分别解释，正文专用视图复用批量节点和来源查询，不逐 node 拼接独立 CRUD。

参数与结果日志从正常请求及返回结构自动提取；记录范围、来源 ID、文本量和分页元数据，不记录正文。CLI 对同一份序列化响应计算字符数及 UTF-8 字节数；可选 --output-file 在CLI层原子保存完整响应并返回轻量回执，不进入业务参数；文件读取由Agent按需安排。API完成、响应生成与宿主实际接收是不同阶段，宿主截断不能由 CLI 成功日志推定。增量功能测试覆盖完整重组、配置生效、版本与范围、批量查询、help和自动日志。

召回筛选在 workflow/pipeline 计算有界 selection_diagnostics，与公开结果一起返回并由通用日志工具记录；只保留计数、策略、限额、ID/时点边界与匹配统计，不复制文学正文，不为诊断新增逐条数据库查询。策略和阈值的权威配置仍在 conf/creative.json，业务判断不进入日志工具。


## 统一发布与数据库兼容

统一版本声明与校验边界见[架构](architecture.md#统一发布与数据库兼容)。CLI 引导运行资源供下层使用，help从现行契约生成；展示导出与前端配套，重建入口见[API指导](../script/cli/API.md#展示数据重建)。

## 稿件与延迟维护编排

creative/manuscripts集中处理attempt、采用和来源；visibility供context-read/prose/history复用采用选择。scenes编排prepare/submit/accept，maintenance批量发现祖先待办并持久化独立scope。归档及Capsule仅在内部ContextVar维护域跳过leaf限制，其他校验保留；不提供可由调用者伪造的通用绕过参数。复用现有repository批量源查询、publish、正文展开和四表，无需另建数据层或改版本策略。

scene-prepare/submit/accept/maintenance、author-save/read和dialogue-save/close的schema、注册bindings、help及示例同步维护。help按公共schema展开条件，业务流程只引用调用时机。日志记录attempt/adoption/job/阶段和数量，不记录正文或原始输入；没有content的maintenance查询也可能生成维护控制回执。

维护范围还限制目标节点的本地来源：冻结后只接收归档回执列出的语义及带同maintenance_job_id的生成摘要；业务查询复用同一来源过滤。展示材料按稿件固定，状态核对复用与导出相同的单幕内容投影，不为检查一幕加载全部故事。resume复用已完成准备；对外部分完成错误区分author_saved、display_published和manuscript_accepted。
