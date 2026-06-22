# ROS Bag Video Extractor

从 ROS 1 bag 中提取 H.264 相机话题，转码后按相机或雷达时间戳导出 PNG。支持单个 bag、批量处理、多相机话题、雷达时间戳匹配与简单抽帧。

> 本工具目前面向 ROS 1 bag，不支持 ROS 2 bag/MCAP。不要将真实车辆数据、客户 bag 或可识别个人的画面提交到公开仓库。

`.gitignore` 默认排除 bag/MCAP、视频图像、点云、日志、本地数据库、环境变量和证书。提交前仍应执行 `git status` 和 `git diff --cached` 人工复核；忽略规则不能替代数据脱敏和授权确认。

## 环境要求

- Python 3.9+
- FFmpeg（系统 `PATH` 中可用，或由 `imageio-ffmpeg` 提供）
- 以下二选一：
  - ROS 1 Python 环境中的 `rosbag`
  - PyPI 上的 `rosbags`（默认依赖）

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

## 命令行用法

单个 bag：

```bash
python exact_bag_png_mutil_process.py \
  --mode single \
  --path /path/to/input.bag \
  --save-dir ./output
```

批量处理：

```bash
python exact_bag_png_mutil_process.py \
  --mode batch \
  --path ./bags \
  --save-dir ./output \
  --threads 4
```

按雷达时间戳命名：

```bash
python exact_bag_png_mutil_process.py \
  --mode single \
  --path ./example.bag \
  --save-dir ./output \
  --use-lidar-timestamp \
  --lidar-topic /sensor/lidar_ml/multi_scan \
  --match-strategy nearest
```

查看完整参数：

```bash
python exact_bag_png_mutil_process.py --help
```

## 适配自己的 bag

默认相机话题、导出目录名与分辨率在脚本顶部的 `TOPIC_CONFIG` 和 `CAMERA_CONFIG` 中配置。`--camera-topic` 可重复传入，用于从已配置话题中选择部分相机。

## 本地 Web 界面

仓库包含一个实验性本地界面：

```bash
python backend_server.py
```

然后访问 <http://127.0.0.1:8765>。后端只监听本机，不应暴露到公网。文件选择器使用 macOS `osascript`；其他系统请直接在界面输入路径，或使用 CLI。

## 输出结构

```text
output/
└── <bag-name>/
    └── Images_resize/
        ├── camera_forward_wide/
        ├── camera_forward_far/
        ├── camera_right_front/
        └── camera_left_front/
```

`--clean-bag-dir` 会在处理前递归删除对应 bag 的旧输出目录，请谨慎使用。

## 开发与测试

```bash
python -m unittest discover -s tests -v
```

不建议将大型 bag 作为测试样本提交。如果需要集成测试，请使用已脱敏的小型样本，并通过 Git LFS 或 release asset 单独分发。

## License

[MIT](LICENSE)
