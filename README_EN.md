# ROS Bag Video Frame Extractor

[Chinese](README.md) | [English](README_EN.md)

Extract H.264 camera topics from ROS 1 bags, transcode them, and export PNG frames named with camera or LiDAR timestamps. The tool supports single-bag and batch processing, multiple camera topics, LiDAR timestamp matching, frame sampling, and a local web interface.

> This project currently targets ROS 1 bags. ROS 2 bags and MCAP are not supported. Never publish real vehicle data, customer bags, or frames containing identifiable personal information without proper authorization and anonymization.

The included `.gitignore` excludes common bag, MCAP, image, video, point-cloud, log, database, environment, and certificate files. Always review `git status` and `git diff --cached` before committing.

## Requirements

- Python 3.9+
- FFmpeg available on `PATH`, or provided by `imageio-ffmpeg`
- One of:
  - `rosbag` from a ROS 1 Python environment
  - The PyPI `rosbags` package, included in the default dependencies

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

## CLI usage

Process one bag:

```bash
python exact_bag_png_mutil_process.py \
  --mode single \
  --path /path/to/input.bag \
  --save-dir ./output
```

Process a directory:

```bash
python exact_bag_png_mutil_process.py \
  --mode batch \
  --path ./bags \
  --save-dir ./output \
  --threads 4
```

Use LiDAR timestamps:

```bash
python exact_bag_png_mutil_process.py \
  --mode single \
  --path ./example.bag \
  --save-dir ./output \
  --use-lidar-timestamp \
  --lidar-topic /sensor/lidar_ml/multi_scan \
  --match-strategy nearest
```

List all options:

```bash
python exact_bag_png_mutil_process.py --help
```

## Adapting to your bags

Configure default camera topics, output subdirectories, resolution, and frame rate in `TOPIC_CONFIG` and `CAMERA_CONFIG` near the top of the script. Repeat `--camera-topic` to select a subset of configured camera topics.

## Local web interface

```bash
python backend_server.py
```

Open <http://127.0.0.1:8765>. The backend listens on localhost only and should not be exposed publicly. The native file picker uses macOS `osascript`; on other operating systems, enter paths manually or use the CLI.

## Output layout

```text
output/
└── <bag-name>/
    └── Images_resize/
        ├── camera_forward_wide/
        ├── camera_forward_far/
        ├── camera_right_front/
        └── camera_left_front/
```

`--clean-bag-dir` recursively removes the existing output directory for the selected bag before processing. Use it carefully.

## Development and testing

```bash
python -m unittest discover -s tests -v
```

Do not commit large bags as test fixtures. Use small anonymized samples and distribute them separately through Git LFS or release assets when needed.

## License

[MIT](LICENSE)
