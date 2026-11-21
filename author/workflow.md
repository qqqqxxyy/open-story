# 作者工作流

实际创作先读取初始化生成的本地 `author/writing-contract.md`；缺少时按 [首次启动](../INITIALIZE.md) 恢复或初始化。下方章节链接指向公开模板，执行时使用本地契约中的对应内容。

进入作者阶段时补齐尚未掌握的[共同契约](../role-interaction/director-author/contract.md)、[角色职责](ROLE.md)和[写作契约](writing-contract.template.md)，随后复用已掌握规则。默认由同一主 Agent 承接导演材料并创作，流程按独立任务执行；参数和返回按需查[CLI help](../script/cli/API.md)。显式多 Agent 的实体交接见[可选路线](../director/multi-agent.md)。

导演流程对本文件的引用是同一阶段的衔接：已完成的创作、review、提交和展示继续使用其结果；返回导演时进入下一阶段，不重复执行交接处的同一操作。

## 接收材料

1. 确认故事配置、node_id、实际导演包ID及本幕范围。默认沿用自己已经组织的原始输入、creative_intent、scene_need、情节候选、上一幕正文和资料；上下文缺失或来自另一 Agent 时才 director-handoff-read 一次展开。
2. 结合多幕介入、已读经历与当前情境理解材料的适用范围。按[共同契约](../role-interaction/director-author/contract.md#职责与裁量)独立选择与发展，不将候选覆盖率作为创作目标。
3. 摘要和选集有损，遗漏不代表人物不知道；有具体缺口主动 context-read 定向查询人物、对象、事件、关键词和原节点正文。信息包索引供追溯，不逐条重读已经掌握的材料，不选择其他分支未来或其他故事。

## 接续已有故事的阅读准备

1. 首次接续已有故事或恢复后缺少文学上下文时，阅读固定范围最近至少5幕完整正文和10幕每幕摘要；不足时读取已有部分，已完整读过的材料计入数量。同一 Agent 转换逻辑角色本身不触发重新阅读。
2. 用 history-list 取得最近幕与真实正文/摘要指针，按叙事顺序选择。object 的 capsule 摘要另作长期背景，不能代替所需完整作品。
3. 用 context-read 的 prose 视图批量分页，沿 page.next_cursor 到 complete，依序保留全部原始字符和正文版本。具体历史段落用 history-read 默认 prose 或 paragraphs；同范围多关键词用 history-search keywords。工具传输见[读取指导](../script/cli/API.md#大文本读取与工具传输)。
4. 按叙事顺序理解声音、关系、期待、叙述距离、句段节奏与详略；有具体缺口继续读有代表性的正文和资料。准备完成后沿原节点进入创作，持续协作复用已有理解。

## 本幕文学创作

普通幕在材料接收与必要阅读完成后，先确定发展，再进入具体演绎；整体取舍与表达安排贯穿创作。写作中出现更好的发展可回到相关步骤调整，具体资料缺口按本幕范围补查。

1. **确定本幕的发展。** 按[回应读者期待](writing-contract.template.md#回应读者期待)、[接住输入并继续创作](writing-contract.template.md#接住输入并继续创作)和[情节取舍](writing-contract.template.md#情节取舍)，独立决定本幕实际采用的发展及展开重点。
2. **演绎具体经历。** 按[人物演绎](writing-contract.template.md#人物的认识情感与表达)、[场景与画面感](writing-contract.template.md#场景与画面感)和[因果与知情](writing-contract.template.md#连续性理解因果与知情)，将所选发展写成人物之间的实际经历。
3. **安排整体表达与收束。** 随写作按[情节取舍](writing-contract.template.md#情节取舍)和[情节、气口与篇幅](writing-contract.template.md#情节气口与篇幅)安排详略、节奏与落点，完成本幕。

## 普通幕

1. 按[接收材料](#接收材料)与适用的[接续阅读](#接续已有故事的阅读准备)承接本幕，确认当前 attempt_id 和本次导演包；有具体缺口再补查。
2. 执行[本幕文学创作](#本幕文学创作)三个步骤，完成全部虚构人物包括主人公的演绎。引号对白同样按[输入原则](writing-contract.template.md#接住输入并继续创作)理解为大纲，原句合适可保留。
3. 完整成文后执行[成文 review](writing-contract.template.md#成文-review)，在上下文中做必要文学小调整；需要重构主要发展时回到创作步骤。
4. 组织最终 literary_text、按需的简短 feedback 与完整 display；其中 summary 按[每幕摘要](writing-contract.template.md#每幕摘要)编写。反馈记录重要改向、[值得延续的变化](writing-contract.template.md#历史经历与人物声音)及影响，可建议 plan/truth/secret/记事；无交接需要可省略。默认一次 UTF-8 标准输入 scene-submit，传 attempt_id 和实际 source_packet_event_id。显式多 Agent 只 author-reply-save 交回执，由导演展示。
5. 成功后当前稿等待反馈，不提炼本幕记忆事实；由导演阶段仅处理 API 返回的已采纳前幕维护。失败按[恢复](#中断恢复)复用已保存稿，不能无依据声称完成。呈现按[交付契约](writing-contract.template.md#呈现与交付)。

## 小修当前稿

1. 承接导演 prepare(revise/minor) 返回的新 attempt、基准作者包和本次反馈，确认保留内容与修改目标。使用上下文中的当前稿；缺失才按 packet_event_id 定向 author-reply-read，不触发常规召回或历史阅读准备。
2. 按写作契约修改有关经历、反应、顺序或细节，保留仍适用的构思；需要重选主要发展时转大修，不用润色暗换主要因果。
3. 对完整修订稿做[成文 review](writing-contract.template.md#成文-review)，scene-submit 传新 attempt 和基准稿的导演包，保存完整正文及该稿 display。
4. 成功后等待反馈，旧稿及原话保留；失败复用本次稿件恢复，不覆盖旧 event。

## 大修当前稿

1. 承接导演 prepare(revise/major) 后完成的资料准备和新导演包，确认同 node 的新 attempt 与原固定历史范围。原稿是修改对象，不是已发生历史。
2. 顺序执行普通幕的文学创作、review和提交，使用本 attempt 的导演包。完整执行判断不等于重复读取已掌握材料。
3. 展示成功后等待反馈；尚未被采纳的稿件及其新造人物特征、事实和设计不进入语义归档。

## 交互幕

1. 首轮按接收材料与必要阅读理解开幕，续轮复用文学上下文。新增原话先由导演阶段 dialogue-input 保存，使用返回 turn_id；缺失原文时 context-read 按该 ID 取回。
2. 按[同幕交互契约](writing-contract.template.md#对话模式)演绎一个可介入片刻，自然呈现用户的场内言行和实际回应，场外要求不写成对白。一轮的推进和停点由交流与阅读效果决定。
3. 对当轮文本做[成文 review](writing-contract.template.md#成文-review)；准备收幕时先检查整幕衔接，需要调整已存片段才准备 final_literary_text。review在完成稿件的提交之前进行。
4. 新回应默认通过一次 UTF-8 标准输入调用 dialogue-turn-save 保存，收幕轮标 scene_complete；已有输入均回应时也可 dialogue-close 追加必要结尾。成功后呈现已存片段；原始输入、已存轮次和顺序保留。稿件关闭后再修改走同幕修订流程。
5. 整幕完成后，用 scene-submit 的 author_packet_event_id 分支和 attempt_id 展示完整稿，摘要按[每幕摘要](writing-contract.template.md#每幕摘要)编写；当前幕等待反馈，仅由导演处理 API 返回的已采纳前幕维护。中间轮不发布阅读页。

## 中断恢复

1. 用 scene-status 及 error.details 确认原幕、实际导演包与已保存作者包/片段；保留已成功内容与 ID。
2. 小修缺失当前稿时按作者包ID定向恢复；其他路线按[接收材料](#接收材料)，确实缺少历史文学上下文才执行[阅读准备](#接续已有故事的阅读准备)；交互通过 dialogue-read 找回缺失的完整输入和片段，不将已存交流改成摘要。
3. 普通正文已保存或交互整幕已完成时，用 scene-submit 复用作者包和原 display 元信息，修复缺少的展示阶段；不因恢复创建新幕或覆盖旧正文。
4. 展示已完成则当前稿等待反馈，只恢复导演[已采纳幕维护](../director/workflow.md#已采纳幕维护)中的待办。显式多 Agent 按[回执恢复](../director/multi-agent.md#恢复)交接；反馈中的作者记事由导演随采用稿维护以 author_notes 保存并注明来源，不覆盖事实。

## 回复来源与定向历史

1. 普通作品声明实际依据的导演包：初稿和大修使用本 attempt 的包，小修沿用基准稿的包。同 attempt 中另有新包不自动否定实际来源，不新增文学审批。
2. 同幕交互以 turn_id、fragment_event_id 和整幕作者包标明真实来源与交付；定向历史查询使用本幕固定范围。
3. 原 event 业务负载在 payload，控制元信息在外层；当前视图返回解包内容及 source_event_ids，不把合成投影视为新史实。常规资料使用已有 compact 的 projection；需同时追查原始来源时选择 scene-context full。大结果可用 CLI --output-file 完整转储，文件读取方式和范围按本幕需要决定。
