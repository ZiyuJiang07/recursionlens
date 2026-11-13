# RecursionLens

[English](https://github.com/ZiyuJiang07/recursionlens/blob/main/README.md) | **简体中文**

**不只看递归返回了什么，还要看到重复计算发生在哪里。**

RecursionLens 是一个零运行时依赖的 Python 包，用于在 JupyterLab 中观察递归执行过程。它把一次追踪转换成可展开的调用树、压缩后的子问题 DAG，以及 naive 与 memoized 的定量对比。

> **已执行的 JupyterLab 教程：** [打开 RecursionLens_Tutorial.ipynb](https://github.com/ZiyuJiang07/recursionlens/blob/main/docs/RecursionLens_Tutorial.ipynb)。15 个代码单元都已保存输出。如果 Jupyter 因为 notebook 未受信任而隐藏 HTML/SVG，点击 **Trust**，或执行一次 **Run All Cells**。想零配置预览，可以直接下载并打开[静态 HTML 版教程](https://github.com/ZiyuJiang07/recursionlens/raw/main/docs/RecursionLens_Tutorial.html)。

## 项目团队

CS1302A Group 50：

- Ziyu JIANG
- Xinyue CAI
- Kehan CAO
- Ruoxi LYU
- Haobo MA

## 为什么需要 RecursionLens？

递归函数通常只暴露最终返回值或 traceback，学生必须在脑中重建整个执行过程。RecursionLens 回答三个不同的问题：

1. **调用树：** 逐次调用来看，到底发生了什么？
2. **子问题 DAG：** 合并相同参数之后，真正有多少个不同的子问题、它们如何依赖？
3. **执行对比：** 开启 memoization 之后，哪些指标发生了变化？

以 `fib(5)` 为例，整个过程是 **观察到 15 次调用 → 6 个唯一子问题 → memoization 后只执行 6 次函数体**。

## 相比调用图的新意

现有 `rcviz` 包已经能画出基于装饰器的递归树，包含参数、返回值和 Jupyter 渲染。RecursionLens 有意聚焦另一条工作流：

- 在同一份 trace 上，在调用树与压缩子问题 DAG 之间转换；
- 一次性用 SVG 展示完整调用树，或在较大的运行中保留可折叠树；
- 量化重复调用、实际执行次数、缓存命中与最大深度；
- 在一份报告中并排对比 naive 与 memoized 的 DAG；
- 在 JupyterLab 中渲染自包含的 HTML/SVG，不需要 Graphviz、原生库、外部 JavaScript 或 CDN；
- 导出带版本号的 JSON，便于复现分析与测试。

## 安装

RecursionLens 需要 Python 3.9 或更高版本。

从 PyPI 安装：

```bash
python -m pip install recursionlens
```

本地开发：

```bash
git clone https://github.com/ZiyuJiang07/recursionlens.git
cd recursionlens
python -m pip install -e ".[dev]"
```

包没有运行时依赖。

## JupyterLab 快速开始

```python
from recursionlens import trace

@trace
def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)

naive = fib.run(5)
naive  # 在 notebook 输出区显示可展开的调用树
```

把同一份 trace 切换成压缩子问题 DAG：

```python
naive.show(mode="dag")
```

或者一次性展开全部调用，画成一张紧凑的 SVG 树，不折叠任何节点：

```python
naive.show(mode="expanded")
```

开启 memoization 再运行一次，并对比证据：

```python
memoized = fib.with_options(memoize=True).run(5)
comparison = naive.compare(memoized)
comparison
```

对比会确认两者返回值一致，并报告实测变化，其中包括 **函数体执行次数由 15 降到 6**。

函数原本的行为不受影响：

```python
assert fib(5) == 5
assert fib.last_report.total_calls == 15
```

## 导出报告

```python
naive.export_html("fib-tree.html")
naive.export_html("fib-dag.html", mode="dag")
naive.export_json("fib-trace.json")
comparison.export_html("fib-comparison.html")
```

HTML 报告是独立文件，不需要 notebook 服务器就能打开。JSON 包含调用树、DAG 节点与边、指标、警告以及 schema 版本。

## 适用范围

0.1 版本面向同步、确定性的教学示例，例如阶乘、斐波那契和纯数学递归。

- memoization 要求绑定参数可哈希；参数不可哈希时给出警告，而不是崩溃。
- 对有副作用或依赖外部状态的函数，相同参数并不一定意味着重复劳动。
- `max_calls` 限制保存的树规模，但不改变函数返回值。被截断的报告会明确标记树与 DAG 指标为部分结果。
- RecursionLens 会真实执行你的函数，**它不是运行不可信代码的沙箱**。
- 异步函数、生成器、自动推断 Big-O、自动改写代码，都不属于 0.1 的范围。

## 文档与示例

- [已执行的 JupyterLab 教程](https://github.com/ZiyuJiang07/recursionlens/blob/main/docs/RecursionLens_Tutorial.ipynb) — 每个公开命令一个示例：装饰器、报告对象、三种视图、指标、memoization、对比、导出与错误处理
- [静态 HTML 教程预览](https://github.com/ZiyuJiang07/recursionlens/raw/main/docs/RecursionLens_Tutorial.html) — 同一份教程，所有可视化报告已渲染，不需要 Jupyter
- [可直接运行的示例 notebook](https://github.com/ZiyuJiang07/recursionlens/blob/main/examples/demo.ipynb)

## 开发与测试

```bash
python -m pytest tests -v
python -m build
python -m twine check dist/*
```

测试覆盖 trace 不变量、缓存行为、签名、异常、截断、JSON、HTML 转义、DAG 渲染与对比报告。贡献时应保持公共 API、测试与 README 同步。

## 许可证

MIT © 2026 Ziyu JIANG、Xinyue CAI、Kehan CAO、Ruoxi LYU、Haobo MA。
