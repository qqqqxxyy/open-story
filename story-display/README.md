# 故事经纬

仓内只读展示器，与当前 skill 的导出器配套交付，不维护独立版本或历史快照协议。SQLite 是故事权威来源，story/ 与 dist/ 均可重建，不在派生快照中改写正文。

从主仓库查询 script/cli/main.py display-export --help，指定故事配置和输出目录；多故事先仅导出，再在本目录运行 pnpm generate 或 run.ps1 -Action open。结构不匹配时重新从数据库导出。生成器区分代码资源根和输出目录，可在隔离目录生成。

旧原始文件同步使用 run.ps1 -Action sync -StoryId <id> -DataRoot <原始文件根>，需要显式来源，不读取或适配历史展示快照。旧快照与旧 HTML 保留为备份；无权威来源的资料报告为尚不能重建，不静默删除。

pnpm install --frozen-lockfile 安装现有依赖；pnpm test 与 pnpm typecheck 用于验证。HTML 可离线阅读；display-version.js 在 HTML 写入后发布，仅携带内容摘要，每 2.5 秒检查当前故事变化。正文 revision 和阅读 key 保持稳定；新页面路径不会自动继承旧路径的浏览器阅读状态。

`conf/reading-update-repairs.json` 为可选本地阅读状态维护数据，默认不跟踪 Git，缺少时按空清单处理。需要时可从 `conf/reading-update-repairs.example.json` 建立本地文件；其中的故事与节点记录不随项目发布。
