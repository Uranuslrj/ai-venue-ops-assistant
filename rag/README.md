# RAG MVP

## 范围与准确描述

这是使用 Python 标准库实现的 BM25 检索 MVP：四份模拟运营知识文档、章节级 Chunk、来源元数据、Top-K 去重、查询覆盖门槛、正向反馈保护、无依据人工复核降级和固定小型评测集。BM25 相关度分是排序信号，不是概率或模型置信度。本版本没有 Embedding、向量数据库或生成式答案链。

知识来源和真实性边界见 `../rag_knowledge/SOURCES.md`。文档是基于项目模拟场景起草的产品假设，不是经真实门店验证的制度。

## 流程

玩家原始反馈 -> 领域词项分析 -> BM25 召回和排序 -> Top-K 章节去重 -> 相关度/覆盖门槛 -> 来源引用；无依据、泛化问题和范围外反馈转人工；正向反馈不生成负向改进。

## 运行

```powershell
python retrieval.py
python evaluate_rag.py
```

服务启动后：

```text
GET /api/rag?query=<url-encoded query>&top_k=3
```

## 验证

运行 `evaluate_rag.py` 执行 `evaluation_cases.json`。当前 7 个模拟案例全部通过；详细边界与失败案例见 `EVALUATION.md`。这不是生产级效果指标。

## 不包含

真实门店SOP核验、Embedding/向量数据库、LLM带引文生成、真实用户验证、云部署、权限、生产监控和真实经营效果验证。
## 混合检索配置

默认权重：BM25 0.60，Embedding 0.40。

- BM25 保留规则名称、问题类型和领域术语的精确匹配；
- Embedding 补充玩家口语化、同义表达和改写后的语义召回；
- Embedding 未配置、端点错误或调用失败时自动降级为 BM25；
- API 返回 `method` 和 `weights`，可在评测中核验实际使用模式；
- Embedding 缓存只保存向量，不保存 API Key。

环境变量示例（请在本地终端配置，不要写入代码或提交文件）：

```powershell
$env:DASHSCOPE_API_KEY = "在本地设置你的Key"
$env:DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
$env:DASHSCOPE_EMBEDDING_MODEL = "text-embedding-v4"
$env:DASHSCOPE_EMBEDDING_DIMENSION = "1024"
$env:RAG_BM25_WEIGHT = "0.6"
$env:RAG_EMBEDDING_WEIGHT = "0.4"
```

粘贴到聊天中的 Key 已视为暴露凭证，应在百炼控制台撤销或轮换后再使用新 Key。

## 当前推荐权重

BM25 0.60 + Embedding 0.40。原因：运营知识包含“规则讲解、剧本节奏、现场考核”等专业术语，需要 BM25 保持精确；玩家评论又有口语化和同义表达，需要 Embedding 补充语义召回。当前默认只在配置 `DASHSCOPE_API_KEY` 后启用 Embedding；否则返回 `bm25_only:not_configured` 并保持原有 BM25 功能。
