# 导演工作流

首次协作阅读[共同契约](../role-interaction/director-author/contract.md)。本文件维护流程步骤和调用时机；参数、返回与示例按需查[CLI help](../script/cli/API.md)。先区分创作、查询、评审和维护；场外讨论不自动推进故事。

本机首次启动与个人默认设置按 [INITIALIZE.md](../INITIALIZE.md) 完成。创作中使用生成的 `author/writing-contract.md`；下方写作章节链接指向公开通用模板。

## 创建新故事

1. 根据用户题材与明确输入，通过普通聊天确认影响体验的背景、基调、主人公处境和叙述缺项，不固定问卷，不询问已明确或已授权自由生成的内容，不提前泄露秘密与后续转折。明确用户要求优先；未指定时，沿用写作契约的[默认主人公与叙述视角](../author/writing-contract.template.md#主人公与作者权限)。
2. 总标题指向整部作品的核心体验、长期处境、关系或整体意象，保留未知，不以第一幕地点或单次动作代替。初始设定只记录确立的世界与起点；未来想法归可修订规划。
3. 组织确认后的设定和逐字原始消息，通过 story-init 创建数据库、root 与初始记录。输入与解释分开，保留标点、错字、空格、换行和真实来源。无法取得宿主原文时诚实标为转录，工程材料标为 simulation。只使用本次请求、默认值和一般创作知识，不自动读其他故事；用户指定外部参考时保留来源。
4. 初始化完成后转入下方“普通下一幕”，通过 scene-prepare 创建第一幕；需要初始设计时按[规划原则](planning-and-backstage.md)处理，不把完整长期大纲当开局前提。作者按[写作契约](../author/writing-contract.template.md)从值得经历的时刻进入故事。

## 普通下一幕

1. **辨认任务并开幕。** 读者基于当前稿开始独立下一幕时，调用 scene-prepare 的 action=next，传稳定 request_id；前幕待反馈时附读者实际看到的 expected_author_packet_event_id；API原子采纳前稿、开启后继并固定读取范围。普通“继续”需结合当前是否仍在同幕交互判断。讨论、暂停和修改不作为采纳信号；重试复用 request_id，已有任务走[恢复](#中断恢复)。
2. **取得资料并建立处境。** 保存 node_id、attempt_id 和 preparation。缺少连续上下文时按[接续阅读准备](querying.md#接续已有故事的阅读准备)补齐；按[召回组织](querying.md#本幕资料召回与组织)使用当前 projection，摘要开启时结合[长期背景](capsule.md)。大结果可用 --output-file；具体缺口通过 context-read 补查，不重复召回已掌握材料。前幕已采纳全文可直接承接，即使其语义尚未归档；后来归档不会回填本幕固定范围。
3. **理解本次介入。** 按[读者期待方法](reader-expectations.md)确定本幕关注、依据、范围与不确定性；区分约定和候选，必要资料缺口回第2步。
4. **构思并保存导演包。** 执行[创作导演信息包](#创作导演信息包)，取得本 attempt 的 packet_event_id。尚未采纳的本幕新设计随包保留，不提前转成人物记忆或正式设计事实。
5. **完成文学创作和 review。** 同一 Agent 承接[普通幕作者流程](../author/workflow.md#普通幕)第1～3步，独立选择发展并完成成文 review。导演包是参考，复用上下文，不为角色切换重新读包。
6. **保存并展示当前稿。** 对应作者普通幕第4步，scene-submit 传 attempt_id、实际 source_packet_event_id、完整正文及 display 元信息，摘要按[每幕摘要](../author/writing-contract.template.md#每幕摘要)编写。成功进入 awaiting_feedback；分别确认保存和展示，失败按[恢复](#中断恢复)复用稿件。此次不归档当前幕。
7. **展示后维护前幕。** 对应作者普通幕第5步的交接，按返回 maintenance.next_job 执行[已采纳幕维护](#已采纳幕维护)，无需手工寻找节点或先归档前幕再写当前幕。阅读页已展示，同轮串行收尾；最终回复后不会自行继续运行。随后交还读者，当前稿等待反馈，不自动生成下一幕。

## 创作讨论

1. 按[讨论方法](reader-expectations.md#开展创作讨论)辨认读者要确认的关系、声音、走向或不适来源，复用现有上下文，有具体事实疑点再查询。
2. 结合范围与依据比较具体例子、人物反应或开端，说明已确立内容和推测；没有必要时不展开完整后续，不以固定问卷阻断讨论。
3. 明确共同理解仍是候选还是已确认设定。普通讨论不采纳当前稿、不归档它；明确要求保存独立设定时按维护路线保存原话和确认内容，不将导演的解释自动升为永久人物特征。

## 小修当前稿

1. 确认当前待反馈稿及修改目标；现有构思足够承接时用小修，局部情节和顺序也可以修改。读者指定路线优先；需要重新选择主要发展则转[大修](#大修当前稿)。
2. scene-prepare 用 action=revise、revision_kind=minor、当前 base_author_packet_event_id 与稳定 request_id 保存反馈，取得同 node 的新 attempt。preparation=null，不调用召回；状态保存不属于内容召回。
3. 承接[作者小修](../author/workflow.md#小修当前稿)第1～2步完成修改。原则上沿用当前稿和已知材料；上下文缺失时仅按作者包ID恢复该稿或确有必要的来源，不重做五幕正文、十幕摘要准备。
4. 按作者小修第3～4步完成review、scene-submit与展示，沿用基准稿的导演包；旧稿不覆盖。只处理 API 返回的已采纳前幕维护，修订稿仍等待反馈。

## 大修当前稿

1. 确认重构方向，scene-prepare 用 action=revise、revision_kind=major、当前 base_author_packet_event_id 与新 request_id，取得同 node、同存活前驱的新 attempt。
2. 依次执行普通下一幕第2～5步的资料准备、期待理解、导演构思和作者创作，保存本 attempt 的新导演包。已掌握材料继续复用；原稿仅作明确重构对象，不当作前驱正史。
3. review 后 scene-submit 新稿并等待反馈。API保留旧稿与原始输入，不用 node-rewrite 删除当前未采纳幕；已采纳历史的重创另走[删除与重新创作](#删除与重新创作)。

## 已采纳幕维护

1. 使用当前已展示稿的 author_packet_event_id 与 maintenance.next_job；中断恢复时调用 scene-maintenance 查询待办，按 API 返回顺序处理，不自己拼队列。它只包含已采纳未完成幕，最新待反馈稿不在其中。
2. semantic_pending：依据 job.adopted 指向的确切采用稿和 job.scope，按[提炼归档](archiving.md)整理事实、知情、关系、画像、采用设计及必要记事，批量提交 scene-maintenance 的 events。已掌握采用稿不机械读回；正文缺失按作者包ID恢复。资料有具体缺口时，context-read显式传maintenance_job_id按任务独立范围补查，普通创作仍用原范围；归档保留截至目标幕的事实和知情。API负责受限非叶追加与事务，不移动 head 或改正文。
3. capsule_pending：按[摘要流程](capsule.md)依据返回的 capsule_jobs 写摘要，用同一 scene-maintenance 提交 capsules；API返回下一批或层级，直至 next_job=null。Capsule关闭或未达阈值由API直接完成，不手工补 check。
4. 重试复用 job_id 和原完整批次。回执完成后才宣称归档完成；失败保留成功阶段，下次沿原任务恢复。整个维护不调用展示、不刷新快照或HTML。

## 明确定稿或结束故事

1. 读者明确采纳最后一幕且不创建后继时，scene-accept 传 node、branch、当前 author_packet_event_id 和稳定 request_id。普通暂停或讨论不调用。
2. 按返回维护任务执行[已采纳幕维护](#已采纳幕维护)，不重新展示。没有明确定稿时，最后一幕保留待反馈。

## 创作导演信息包

在普通下一幕已完成范围固定、信息获取和意图理解后，依次执行以下创作判断，结论用于组织同一次交接。出现具体资料缺口时返回信息获取步骤，构思或设计需要调整时回到相应步骤。

1. **发掘值得发展的张力。** 按[本幕情节可能性](planning-and-backstage.md#本幕情节可能性)，从当前处境与读者介入中发掘值得发展的矛盾，明确本幕可以深化的机会。
2. **构思并比较发展可能。** 承接上一步，按[候选构思与比较](planning-and-backstage.md#本幕情节可能性)构思、比较本幕的发展可能，同时完成其中的意外线构思，形成供作者发展的候选。
3. **判断并补足必要的后台设计。** 按[设计触发与分工](planning-and-backstage.md#导演持续统筹按需设计作者写本幕)判断是否需要新增或重构设计；需要时按[正式设计评估](planning-and-backstage.md#以故事和戏剧力量评估正式设计)完成构思，选定内核、候选和拟替代目标先随导演包保存，待采用稿维护时再沉淀 plan/truth/secret；明确的独立设定维护另走维护路线。设计改变处境或候选时回到相关步骤调整。
4. **组织并保存交接。** 按[资料组织](querying.md#本幕资料召回与组织)和[一次组织可用的信息包](planning-and-backstage.md#一次组织可用的信息包)汇总材料、构思与具体源索引；开启摘要时保留选中摘要 ID 与激活对象索引。调用 director-handoff-save 保存并取得 packet_event_id。它是阶段性构思与来源索引；持续单 Agent 直接沿用已经掌握的材料，缺失上下文或显式多 Agent 时再通过 director-handoff-read 一次展开。

## 同幕交互

1. 用户明确要求逐轮交互时，scene-prepare 用 action=next、稳定 request_id 选择 dialogue；开幕准备复用普通下一幕第1～4步，再进入交互作者流程。候选随开幕包提供，续轮沿已有理解发展，有意义的转向按需补充。
2. 首轮使用开幕返回的原始输入 event ID 为 turn_id；续轮先调用 dialogue-input 保存新增原话。当前 Agent 已掌握原话与历史时直接承接，有缺口按本幕范围定向补查，不逐轮重建整包。
3. 按[交互作者流程](../author/workflow.md#交互幕)第1～4步完成本轮演绎、review和保存，再在聊天呈现本轮完整正文。中间轮不发布阅读页；场内言行及实际回应进入作品，场外指令不写成对白。
4. 用户要求结束或作者自然收束时，先按交互作者流程完成整幕review，再提交收幕轮或dialogue-close；需要调整已存片段时一并传final_literary_text。已有原始轮次保留，交流是否收束由故事决定。
5. 稿件完成后用 author_packet_event_id 和 attempt_id 调 scene-submit，只提交 display 元信息，摘要按[每幕摘要](../author/writing-contract.template.md#每幕摘要)编写；关闭后再改走同幕修订。缺失片段才定向恢复。成功后当前幕等待反馈，仅处理返回的已采纳前幕维护；独立下一幕才采纳它。

## 可选多 Agent 模式

如无特殊说明，不启用。用户明确要求或适用工作约定指定分工时，按[多 Agent 路线](multi-agent.md)执行持续作者选择、真实身份绑定、回执交接和恢复。普通主流程维持同一 Agent 的串行职责；可选路线只改变执行实体与通信，不改变文学裁量、数据范围或保存阶段。

## 维护与设置变化

场外讨论不自动开启下一幕。需保存原话通过 business-save 的 user_input 类别归属现有节点；业务资料维护也通过 business-save 追加。已发布节点由脚本 updating→追加→active，旧内容不覆盖。共享历史节点明确分支范围。business-read 查询当前采用内容及历史；active 不自动代表当前采用；event_action 按明确 ID 追加、替代或取消；正常归档按采用稿维护任务操作目标幕，独立设定维护明确其归属。

叙述方式、主人公等设置通过 story_setting 追加，条件和生效意图写入开放 content 并由导演与作者理解，不交给数据层执行。维护、删除按对应 API 前提，不能解除外部依赖或改写存活记录强行删除。

## 中断恢复

1. 用 scene-status 定位原 node、设计包、作品及展示状态；若已有 error.details，先保留其中已确认的阶段与 ID。复用原幕及已成功内容，不开替代幕。若入口报告数据库版本不受支持，按[版本指导](../script/cli/API.md#统一版本与数据库兼容)处理，不把重开幕当作恢复。
2. 用原 node 通过 scene-prepare 的 action=resume 恢复；已有有效导演包时直接返回作者或交互步骤，不重复召回。旧未完成节点尚无attempt与完整稿时，可显式传request_id接入新流程；召回确有缺口才用scene-context；资料与文学上下文缺失时按[接续阅读](querying.md#接续已有故事的阅读准备)补齐，再执行未完成设计/创作阶段。
3. 正文已保存时复用作者包，经 scene-submit 提交原 display 元信息；有 display_event_id 时可定向读其元信息。分别检查 display_snapshot_available 与 display_html_available，恢复缺失的生成步骤。已有全文仍在上下文时不机械读回。
4. 交互幕通过 dialogue-read 找回未掌握的输入和片段，沿[作者恢复](../author/workflow.md#中断恢复)继续；完整后复用作者包展示。展示后中断用scene-prepare(resume)取得维护任务及真实trigger作者包；有任务则恢复，无任务则等待反馈。若返回resume_branch_head，先按resume_node_id完成当前head展示，再维护旧幕；accepted_pending_archive/capsules沿[已采纳幕维护](#已采纳幕维护)继续。最终回复如实说明状态，不承诺回合结束后自行运行。

创作补查均使用原幕固定范围。显式多 Agent 的身份与消息恢复见[对应路线](multi-agent.md#恢复)。

## 删除与重新创作

用户要求删除之后全部节点，node-delete 默认保留锚点；要求删除目标幕则选择包含目标。node-rewrite 包含目标及全部后继，删除后返回新ID草稿，用scene-prepare(resume)及稳定request_id接入，再执行设计、作者、review、展示和待反馈步骤。重创保留原始输入和本次指令，不把旧稿、已删后继或旧秘密提供给作者；必要时恢复无污染作者上下文。

一次删除超过一个 node，首次调用只取得 confirmation_required、完整范围、影响分支与 token。必须在独立一轮普通聊天中向用户展示这次具体范围并得到确认，之后才能携带原 token 与 user-confirmed 执行。不能自行回填 token，当次“执行改造”的授权也不等于以后删除任意历史范围的确认。范围变化重新取得确认；叶子单节点按明确请求处理。

选定重创分支取得存活父节点唯一head，其他无head分支对象保留。外部依赖阻断，不修改存活记录强行删除。数据库事务结束后刷新派生展示；若展示失败，明确数据库结果并用 display-export 恢复，不再次删除或重创。

## 故事管理与只读历史

story-list 只发现元数据，不读其他世界正文；story-info、branch-list 定位当前世界。story-state-set 归档/恢复，branch-state-set 完成/弃置/开放；有head与已完成是不同概念。归档或关闭阻止新创作，管理恢复和只读查询仍可使用。管理状态在root归属记录中保存，对全故事/相应分支生效，不作文学召回材料。

纯查询用 history-list、context-inspect、history-search/read，不为看历史而开新幕；创作补查使用本幕固定范围。搜索返回正文版本与段落位置，读取指定版本后再解释，不把算法命中当全部历史。
