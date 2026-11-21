# 正常功能测试入口

统一政策见[develop/testing.md](../../develop/testing.md)。run.py 支持按 --module 运行单一模块，或以 all 运行全部模块；可用模块以该入口 --help 为准。后端 sqlite；模块注册与实际数量以执行为准。

```powershell
& '<PYTHON>' -B -X utf8 tests/data/run.py --module runtime
& '<PYTHON>' -B -X utf8 tests/data/run.py --module all
```

runtime 验证配置注册、集中日志/轮转、依赖与组合查询；help 验证当前帮助与示例；创作模块验证普通幕、交互、业务修订、召回与展示。历史测试仅归档。

新增 maintenance、management、history、event_actions 模块，均可单独执行；all包含全部模块。

event_actions验证定向替代/取消、历史与分支隔离、取消后追加、归档重试、CLI及低阶写入的一致契约；不按业务类别预定处理方式。

真实故事副本的召回/分页检查是可选本地集成测试：仅当本机存在对应私有 debug 配置时运行，干净公开仓库会明确跳过这两项。其余功能测试使用临时生成的通用数据，不要求发布故事库。

setup 模块验证首次启动状态、偏好落地、本地写作契约生成和恢复，以及新故事对默认值的采用与显式覆盖。
