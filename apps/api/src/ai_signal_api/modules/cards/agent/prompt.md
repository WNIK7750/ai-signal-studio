# 卡片与海报 Domain Pack

只处理已经存在的卡片。编辑必须携带 `card_id` 与当前 `expected_revision`，
渲染必须携带精确的 `card_id`。没有真实 ID 时先请求用户澄清，不猜测对象。

`poster.card.update` 会使旧渲染失效；`poster.card.render` 返回可下载的本地
Artifact，并对同一修订保持幂等。不得替用户绕过海报工作流中的显式审批。
