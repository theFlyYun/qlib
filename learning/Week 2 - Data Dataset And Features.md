# Week 2 - Data Dataset And Features

## 学习目标

本周理解 Qlib 的数据层：行情数据如何进入 Qlib，如何被组织成训练数据，`Alpha158` 这类 handler 到底做了什么。

完成后你应该能说清楚：

- `provider_uri` 指向什么。
- `DataLoader`、`DataHandler`、`DatasetH` 的分工。
- `Alpha158` 和 `Alpha360` 为什么是常用起点。
- 如果以后接入自有数据，应该优先从哪里扩展。

## 必懂概念

Qlib 的数据链路可以先记成：

`Provider -> DataLoader -> DataHandler/DataHandlerLP -> DatasetH -> Model`

简单理解：

- `Provider` 负责从 Qlib 数据目录读取基础行情。
- `DataLoader` 负责把字段和表达式加载成 DataFrame。
- `DataHandler` 负责特征、标签、处理器和数据切片。
- `DatasetH` 把 handler 包装成模型训练需要的 train/valid/test。
- `Model` 只关心 dataset 准备好的输入。

## 本项目对应源码/配置

- `scripts/get_data.py`：下载示例数据。
- `scripts/dump_bin.py`：把 CSV/Parquet 转成 Qlib `.bin` 数据。
- `qlib/data/data.py`：数据 provider 入口。
- `qlib/data/dataset/loader.py`：数据加载器。
- `qlib/data/dataset/handler.py`：handler 基类与数据处理。
- `qlib/data/dataset/processor.py`：标准化、缺失处理等 processor。
- `qlib/contrib/data/handler.py`：`Alpha158`、`Alpha360` 等内置 handler。
- `examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml`：本周重点读 `data_handler_config` 和 `task.dataset`。

## 必跑命令

检查数据目录是否存在：

```bash
ls ~/.qlib/qlib_data/cn_data
```

重新下载简版数据：

```bash
python scripts/get_data.py qlib_data --name qlib_data_simple --target_dir ~/.qlib/qlib_data/cn_data --interval 1d --region cn
```

查看 LightGBM 配置里的 dataset 部分：

```bash
sed -n '1,90p' examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml
```

## 输出任务

- 写出 `task.dataset` 里每一层配置的含义。
- 比较 `train`、`valid`、`test` 三个 segment 的日期范围。
- 找到 `Alpha158` 的类定义，记录它默认生成哪类特征。
- 在 [[Qlib Learning Log]] 写下：如果你有自己的 CSV 行情数据，会选择 `dump_bin.py` 还是自定义 loader，为什么。

## 常见问题

- 不要一开始就改 provider 底层。先通过 handler、processor、loader 扩展。
- `.bin` 是 Qlib 的高效本地数据格式，不等于机器学习模型文件。
- `fit_start_time`、`fit_end_time` 通常用于拟合标准化参数，不一定等于训练集全流程。

## 下一步链接

[[Week 3 - Model Workflow And Experiment Tracking]]
[[Qlib Commands]]
[[Qlib Source Map]]
[[Qlib Learning Log]]
