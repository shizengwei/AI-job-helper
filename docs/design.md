# Agentic AI 求职系统设计文档

## 1. 作业要求拆解

### 1.1 明确目标
- 构建一个基于 Agent 的自动求职系统，而不是单纯爬虫。
- 自动收集 50 条 AI Engineer 校招 / 实习岗位。
- 岗位需要覆盖至少 2 个不同招聘网站。
- 输出标准化结果，至少支持 CSV，最好同时保留 JSON。

### 1.2 必须体现的 Agent 能力
- 任务规划：将目标拆为搜索、抓取、解析、筛选、去重、存储。
- 工具调用：可调用搜索、网页抓取、信息解析和导出工具。
- 迭代搜索：当岗位数量不足时，自动改写查询并继续搜索。
- 语义判断：判断岗位是否属于 AI Engineer 方向，而非普通后端岗位。
- 数据清洗：结构化输出职位字段。
- 汇总输出：导出标准 CSV/JSON。

### 1.3 输出字段
- `title`
- `company`
- `location`
- `salary`
- `tech_tags`
- `requirements`
- `source`
- `job_url`

## 2. 设计目标

### 2.1 功能目标
- 稳定获取 50 条符合条件的岗位。
- 同一套流程支持多招聘网站。
- 支持在岗位不足时自动继续搜索。
- 支持 LLM 增强的语义判断和技能标签抽取。

### 2.2 工程目标
- 模块解耦，方便扩展到更多网站或更多岗位类型。
- 默认可在无 LLM Key 时以规则模式运行。
- 有清晰日志、可重复执行、可导出最终交付物。

### 2.3 非目标
- 不做浏览器自动化 UI 流量伪装。
- 不做分布式采集。
- 不做复杂数据库持久化，当前以文件交付为主。

## 3. 总体方案

系统采用“规划器 + 工具执行 + 状态驱动迭代”的轻量 Agent 架构。

1. 用户给出目标：收集 50 条 AI Engineer 校招岗位。
2. Planner 根据目标生成初始搜索计划。
3. Search Tool 在多个招聘站点上搜索候选岗位链接。
4. Fetch Tool 拉取详情页。
5. Parse Tool 结构化提取岗位信息。
6. Judge Tool 判断岗位是否符合 AI Engineer + 校招 / 实习条件。
7. Dedup Tool 对岗位去重。
8. 若数量不足，Planner 基于当前状态调整关键词和站点优先级继续迭代。
9. 达到目标后导出 CSV 和 JSON。

## 4. 数据源策略

### 4.1 优先接入的网站
- `boards.greenhouse.io`
- `jobs.lever.co`
- `jobs.ashbyhq.com`

### 4.2 选择原因
- 页面结构相对稳定，公开访问门槛低。
- 具备较多英文校招 / intern / new grad 岗位。
- 适合做多站点适配器，便于体现 Agent 多源切换能力。

### 4.3 搜索策略
- 使用通用搜索引擎 HTML 结果页作为“发现工具”，按站点域名约束搜索。
- 搜索词由 Agent 动态组合，例如：
  - `AI Engineer intern site:jobs.lever.co`
  - `Machine Learning Engineer new grad site:boards.greenhouse.io`
  - `LLM Engineer internship site:jobs.ashbyhq.com`
- 当命中不足时，自动扩展近义词和岗位族：
  - `AI Engineer`
  - `Machine Learning Engineer`
  - `Applied Scientist`
  - `NLP Engineer`
  - `LLM Engineer`
  - `Recommendation Algorithm Engineer`
- 校招条件词同步扩展：
  - `intern`
  - `internship`
  - `new grad`
  - `graduate`
  - `university`
  - `campus`

## 5. Agent 架构

### 5.1 核心角色

#### Planner
- 输入：目标数量、已完成数量、已尝试查询、站点成功率、失败记录。
- 输出：下一批待执行搜索查询与站点优先级。
- 能力：任务拆解、查询改写、停止条件判断。

#### Executor
- 顺序执行工具链：搜索 -> 抓取 -> 解析 -> 筛选 -> 去重 -> 存储。
- 负责失败重试、异常隔离和状态回写。

#### Reflector
- 在每轮结束后分析：
  - 当前新增岗位数是否过低
  - 某站点是否连续失败
  - 查询是否过窄或过宽
- 输出下一轮策略调整建议。

### 5.2 状态模型

Agent 运行过程中维护单一状态对象：

- `target_count`: 目标岗位数，默认 50
- `accepted_jobs`: 已接收岗位
- `rejected_jobs`: 被拒绝岗位及原因
- `visited_urls`: 已访问详情页
- `tried_queries`: 已尝试查询
- `source_stats`: 各站点成功率、失败数、命中数
- `iteration`: 当前迭代轮次
- `max_iterations`: 最大迭代轮次，防止无限循环

### 5.3 停止条件
- 已收集岗位数 >= 50
- 达到最大迭代轮次
- 连续多轮无新增结果
- 所有搜索查询空间耗尽

## 6. 工具设计

### 6.1 Search Tool
- 输入：`query`, `source_domain`, `page`
- 输出：候选岗位 URL 列表
- 职责：
  - 执行搜索
  - 过滤非目标域名链接
  - 去除已访问 URL

### 6.2 Fetch Tool
- 输入：`job_url`
- 输出：网页 HTML
- 职责：
  - 请求详情页
  - 处理超时、重试和 User-Agent
  - 记录抓取失败原因

### 6.3 Parse Tool
- 输入：HTML + URL
- 输出：`RawJobPosting`
- 职责：
  - 抽取标题、公司、地点、薪资、正文
  - 识别页面所属站点并路由到对应解析器

### 6.4 Judge Tool
- 输入：结构化岗位
- 输出：`accepted/rejected`, `reason`, `score`
- 职责：
  - 判断是否属于 AI Engineer 方向
  - 判断是否满足校招 / 实习属性
  - 排除普通后端、测试、纯前端、纯运维岗位

### 6.5 Skill Extraction Tool
- 输入：岗位正文
- 输出：`tech_tags`, `requirements`
- 职责：
  - 提取技术关键词
  - 生成岗位核心技能摘要

### 6.6 Dedup Tool
- 输入：岗位对象
- 输出：去重后的岗位集合
- 职责：
  - 基于 `title + company + normalized_location` 做主去重
  - 基于 `job_url` 做强一致去重
  - 近似重复时保留信息更完整的一条

### 6.7 Export Tool
- 输入：岗位列表
- 输出：CSV / JSON 文件
- 职责：
  - 统一字段顺序
  - 导出到 `outputs/`
  - 生成运行摘要

## 7. 语义判断与 LLM 策略

### 7.1 双模式设计

#### LLM 模式
- 当环境变量中存在 `OPENAI_API_KEY` 时启用。
- 使用 LLM 完成：
  - 岗位是否属于 AI Engineer 方向的语义判断
  - 技术栈标签抽取
  - 岗位技能摘要生成
  - 查询改写建议

#### Heuristic 模式
- 无 API Key 时启用。
- 通过关键词词典、正负向特征、规则评分实现降级运行。
- 保证系统可跑通，避免因为外部依赖导致无法交付。

### 7.2 岗位判断规则

正向特征示例：
- `machine learning`
- `deep learning`
- `llm`
- `nlp`
- `computer vision`
- `recommendation`
- `applied scientist`
- `data intelligence`
- `algorithm engineer`

校招特征示例：
- `intern`
- `internship`
- `new grad`
- `graduate`
- `campus`
- `university`
- `student`

负向特征示例：
- `backend engineer`
- `frontend engineer`
- `qa`
- `sre`
- `devops`
- `account executive`

## 8. 站点适配器设计

### 8.1 抽象接口

每个站点实现统一接口：

- `match(url) -> bool`
- `parse(html, url) -> RawJobPosting`
- `normalize_company(raw) -> str`
- `normalize_location(raw) -> str`

### 8.2 已规划适配器
- `GreenhouseParser`
- `LeverParser`
- `AshbyParser`

### 8.3 扩展方式
- 新增站点只需实现解析器并注册到解析器注册表。
- Planner 和 Agent 主流程不需要改动。

## 9. 数据模型

### 9.1 RawJobPosting
- `title`
- `company`
- `location`
- `salary`
- `description`
- `source`
- `job_url`

### 9.2 JobPosting
- `title`
- `company`
- `location`
- `salary`
- `tech_tags`
- `requirements`
- `source`
- `job_url`
- `match_score`
- `match_reason`

### 9.3 RunReport
- `target_count`
- `collected_count`
- `iterations`
- `queries_used`
- `sources_used`
- `rejection_breakdown`
- `output_csv`
- `output_json`

## 10. 目录结构设计

```text
AI Engineer Homework/
  docs/
    design.md
  job_agent/
    __init__.py
    config.py
    models.py
    logging_utils.py
    constants.py
    agent/
      __init__.py
      state.py
      planner.py
      executor.py
      reflector.py
      runner.py
    tools/
      __init__.py
      search.py
      fetch.py
      classify.py
      extract.py
      dedupe.py
      export.py
    parsers/
      __init__.py
      base.py
      greenhouse.py
      lever.py
      ashby.py
      registry.py
    services/
      __init__.py
      llm.py
      normalize.py
  scripts/
    run_agent.py
  tests/
    test_classify.py
    test_dedupe.py
    test_parsers.py
  outputs/
  pyproject.toml
  README.md
```

## 11. 执行流程

1. 读取配置并初始化 Agent 状态。
2. Planner 生成首轮查询计划。
3. Search Tool 搜索候选详情页链接。
4. Fetch Tool 拉取 HTML。
5. Parser 按站点解析岗位。
6. Judge Tool 判断岗位是否符合要求。
7. Skill Extraction Tool 补全 `tech_tags` 和 `requirements`。
8. Dedup Tool 去重。
9. 未达 50 条则 Reflector 调整查询，进入下一轮。
10. 达标后导出 CSV/JSON 和运行报告。

## 12. 关键异常与兜底

### 12.1 搜索结果太少
- 自动扩展岗位关键词。
- 自动切换站点。
- 放宽校招词组合，但仍保留 AI 方向判断。

### 12.2 页面抓取失败
- 指数退避重试。
- 记录失败，不阻塞全局流程。
- 某站点持续失败时降低优先级。

### 12.3 LLM 不可用
- 切换到规则模式。
- 仍然保证导出结果和主流程可运行。

### 12.4 无限循环风险
- `max_iterations`
- `max_queries_per_source`
- 连续无新增停止

## 13. 验收标准

- 能运行一个完整命令生成 CSV。
- CSV 至少 50 条岗位。
- 来源域名至少覆盖 2 个招聘网站。
- 字段完整度符合题目要求。
- 代码结构体现 Agent 规划、工具调用和迭代补足能力。

## 14. 本次实现决策

### 14.1 技术栈
- Python 3.11+
- `httpx`
- `beautifulsoup4`
- `pydantic`
- `tenacity`
- `python-dotenv`
- `openai`（可选）

### 14.2 架构决策
- 不依赖重量级 Agent 框架，使用自定义 Agent loop。
- 原因：
  - 作业重点在 Agent 设计能力，而不是框架堆砌。
  - 自定义状态机更便于解释规划、反思和停止条件。
  - 对小型交付更直接，可控性更高。

## 15. 后续实施顺序

1. 按本文档搭建目录结构与依赖配置。
2. 实现数据模型、配置和日志模块。
3. 实现搜索、抓取、解析、筛选、去重、导出工具。
4. 实现 Planner / Reflector / Runner。
5. 联调生成 CSV。
6. 整理 README、运行说明和交付包。
