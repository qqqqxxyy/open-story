# 首次使用：建立本机创作默认

这是公开版 Skill 的首次启动流程。安装中不预置任何使用者的姓名、身份或叙述偏好；初始化结果只保存到本机。

## 启动与恢复

1. 首次加载 Skill 时，在本安装根目录执行 `python -B -X utf8 script/initialize.py --status`，使用该安装配置的 Python 解释器。已经完成初始化的持续会话直接沿用结果。
2. `initialized=true` 时读取本机 `author/writing-contract.md`，进入普通导演/作者工作流。它是实际生效的写作契约。
3. 已有偏好、仅缺少契约时执行 `python -B -X utf8 script/initialize.py --restore`，复用保存的选择，不重复询问。
4. 尚无偏好时，通过普通聊天了解下面两项。用户已经明确提供的内容直接采用；只有未明确的部分需要询问。

## 与使用者确认什么

- **主人公默认要求**：是否使用固定姓名、性别、身份或其他特点，还是每个故事独立决定。
- **默认叙述视角**：第一、第二或第三人称；跟随谁的有限视角、全知视角，或每个故事再决定。需要时保留对切换视角的偏好。

可以自然地问：“你希望主人公有固定的姓名或身份吗？默认采用怎样的人称和视角，还是都留到每个故事开始时决定？”不要求使用者填写技术字段。使用者选择不设固定默认是完整、有效的回答。

## 保存并生成契约

1. 将已确认的选择组织为 UTF-8 JSON，保存到 `.openstory/setup-request.json`。`protagonist` 和 `narration` 都需要明确填写对象或 `null`；`null` 表示不设固定默认。对象字段保持开放，例如主人公的 `name`、`gender`、`notes`，或叙述的 `person`、`viewpoint`、`notes`。原话可以另保留在本地 `raw_user_messages` 中。
2. 执行 `python -B -X utf8 script/initialize.py --content-file .openstory/setup-request.json`。脚本把偏好保存到 `.openstory/preferences.json`，并依据 [公开写作模板](author/writing-contract.template.md) 生成 `author/writing-contract.md`，默认主人公和叙述要求实际写入契约内容。
3. 确认回执 `initialized=true` 后继续原始创作请求。保存失败则复用已有请求文件恢复，不把尚未保存的状态宣称为已初始化。

这些文件都由 `.gitignore` 排除。公开仓库只保留通用模板，初始化结果、个人原话和本地写作契约不加入 Git。

## 后续调整

使用者要求改变本机默认时，以新确认的偏好重新执行初始化命令。脚本只更新契约中带标记的默认值区段，保留其他本地文学规则。故事级明确设置优先；调整本机默认不会改写已有故事的数据库或历史。
