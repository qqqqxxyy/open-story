# 读者反馈旁路工具

这里保存读者对具体幕的评分和原始评价，供另行安排的开发分析使用。工具只使用 Python 标准库，代码、schema、反馈及测试都在本目录；不导入项目 script，不读取故事库，不修改创作数据、提示词或展示文件。

同一个 story+branch 使用一个 UTF-8 JSON 文件，保存在 data/<story_id>/<branch_id>.json。根对象保存 story_id、branch_id 和 feedbacks 数组；每条反馈保留 node_id、反馈ID、时间及原始内容。同一幕的不同阅读感受也追加到该数组，已有条目保持原样。评分和评价至少提供一项，评价保留原始文字、标点、空格及换行；没有评价时存 null。评分不表示任何自动分析结论。

schema.json 定义分支汇总文件及其中的单条反馈。字段包括反馈ID、记录时间、故事/分支/节点ID、评分、评价、可选正文版本元信息和开放 extra 对象。时间为带时区的实际记录时间，与故事时间分开。

使用项目 Python：
~~~powershell
$py = '<PYTHON>'
$tool = './develop/reader_feedback/feedback.py'
& $py -B -X utf8 $tool --help
& $py -B -X utf8 $tool append --help
& $py -B -X utf8 $tool query --help
~~~

追加评分：
~~~powershell
& $py -B -X utf8 $tool append --story-id example-story --branch-id example-branch --node-id example-node --score 7
~~~

追加评价可使用 --comment，或 --comment-file 指定本目录内的 UTF-8 文件。多行文字也可从 stdin 提交：
~~~powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
@'
<读者原始评价>
'@ | & $py -B -X utf8 $tool append --story-id '<story_id>' --branch-id '<branch_id>' --node-id '<node_id>' --comment-file -
~~~
stdin 保存收到的全部文字，包括末尾换行。中文 JSON 输出若要传入 ConvertFrom-Json，先将 [Console]::OutputEncoding 也设为 UTF-8。

查询指定幕：
~~~powershell
& $py -B -X utf8 $tool query --story-id example-story --branch-id example-branch --node-id example-node
~~~

query 还支持 --feedback-id、--min-score、--max-score、--keyword、--offset、--limit 和 --descending。返回 items、total、next_offset；不合并不同反馈，也不根据分数推断偏好。评分过滤不匹配仅有评价的记录。

--narrative-event-id 和 --narrative-sha256 只接收调用者显式提供的版本元信息，不自动查询或验证故事正文。无法取得时 source_version 为 null；不会虚构哈希。反馈保留在此，不随故事删除或重创联动变化。以后分析时可用版本元信息关联对应正文。

--feedback-id 可用于重试：相同ID与相同内容返回原记录；相同ID但内容不同返回 IDEMPOTENCY_CONFLICT。未提供ID的每次追加创建新记录。

所有路径相对 reader_feedback 解析。--data-dir 只能指向本目录内的子目录；--comment-file、--extra-file 也只能读取本目录内文件。extra-file 接收 JSON 对象。query 不创建目录，不连接数据库。成功/失败均输出 JSON，退出码分别为 0/1；help 输出文本。

运行本工具的独立功能验证：
~~~powershell
& $py -B -X utf8 './develop/reader_feedback/test_feedback.py'
~~~
测试数据位于本目录内的临时子目录，结束后清理；测试不调用创作 CLI、不使用故事库。

迁移旧格式：
~~~powershell
& $py -B -X utf8 $tool migrate
~~~
migrate 将旧单条文件按 story+branch 汇总，完整保留已有记录。删除旧文件前，在本目录 backups 中保存一份 ZIP 备份，并核对汇总结果。再次执行不会重复添加。query 遇到尚未迁移的旧文件会要求先迁移。

append 使用分支级文件锁保护读取—追加—保存，以临时文件和原子替换写入完整 JSON。同一分支旁的 .lock 是同步辅助文件，不是反馈记录；查询不需要写锁文件。
