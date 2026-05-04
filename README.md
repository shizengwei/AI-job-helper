# Agentic AI 求职系统

这是针对 `Inspire 校招 AI Engineer Homework` 的实现仓库。

## 项目目标

- 用自定义 Agent loop 体现规划、工具调用、反思和迭代补足能力。
- 自动收集 AI Engineer / ML / LLM 相关的校招、实习、fellowship 岗位。
- 覆盖至少 2 个招聘网站，并导出标准化 CSV / JSON。

详细设计见 [docs/design.md](AI Engineer Homework/docs/design.md)。

## 当前实现

系统由以下模块组成：

- `job_agent/agent`: Planner、Executor、Reflector、Runner
- `job_agent/tools`: 搜索、抓取、分类、技能抽取、去重、导出
- `job_agent/parsers`: Greenhouse / Lever / Ashby 解析器
- `job_agent/services`: 文本归一化和可选 LLM 适配

默认数据源优先使用公开 board API：

- `job-boards.greenhouse.io`
- `jobs.lever.co`

当环境中存在 `OPENAI_API_KEY` 时，可启用 LLM 增强的语义判断、技术栈抽取和 Query 优化；否则自动走规则模式。

## 快速运行

安装依赖：

```bash
python3 -m pip install -e '.[dev]'
```

直接运行：

```bash
python3 scripts/run_agent.py
```

推荐联调参数：

```bash
TARGET_COUNT=50 \
MAX_ITERATIONS=8 \
BATCH_QUERIES=6 \
SEARCH_RESULTS_PER_QUERY=15 \
REQUEST_TIMEOUT_SECONDS=10 \
INTER_REQUEST_DELAY_SECONDS=0.1 \
python3 scripts/run_agent.py
```

启用 LLM 增强模式：

```bash
export OPENAI_API_KEY=your_key
python3 -m pip install -e '.[llm]'
python3 scripts/run_agent.py
```

## 输出内容

默认会在 `outputs/` 下生成：

- `jobs_*.csv`
- `jobs_*.json`
- `report_*.json`

CSV 字段与题目要求一致：

- `title`
- `company`
- `location`
- `salary`
- `tech_tags`
- `requirements`
- `source`
- `job_url`

## 测试

```bash
pytest
```
