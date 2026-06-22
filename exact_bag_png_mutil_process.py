# -*- coding: utf-8 -*-
# 使用命令：python .\exact_bag_png_mutil_process.py --mode single --path "xxx.bag" --save-dir ".\out" --use-lidar-timestamp --lidar-topic "/sensor/lidar_ml/multi_scan" --match-strategy index

import cv2
import numpy as np
import os
import subprocess
import argparse
import threading
import time
import shutil
import tempfile
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    import rosbag as rosbag_py
except Exception:
    rosbag_py = None

if rosbag_py is None:
    from rosbags.rosbag1 import Reader as RosbagsReader
    from rosbags.typesys import Stores, get_types_from_msg, get_typestore

    _TYPESTORE = get_typestore(Stores.ROS1_NOETIC)

# ===================== 配置项（无需频繁修改）=====================
DEFAULT_BAG_DIR = "./bags"              # 默认bag文件夹路径
BASE_SAVE_SUBDIR = "Images_resize"      # 固定子目录名（不可改）
DEFAULT_THREADS = 8                     # 默认线程数（根据CPU核心调整）
# 多话题配置：{话题名: 保存子目录}
TOPIC_CONFIG = {
    "/sensor/camera_front_wide/video": "camera_forward_wide",
    "/sensor/camera_front_far/video": "camera_forward_far",
    "/sensor/camera_right_front/video": "camera_right_front",
    "/sensor/camera_left_front/video": "camera_left_front"
}
# 相机配置（若不同话题参数不同，可改为字典映射）
CAMERA_CONFIG = {
    "width": 3840,        # 相机宽度
    "height": 2160,       # 相机高度
    "frame_rate": 10      # 帧率
}

RUN_MODE = "single"  #batch为解文件夹下所有bag包，single为解单个包
RUN_PATH = None
RUN_SAVE_DIR = "."
RUN_THREADS = DEFAULT_THREADS
RUN_TIMESTAMP_SOURCE = "header"
RUN_USE_LIDAR_TIMESTAMP = False
RUN_LIDAR_TOPIC = None
RUN_MATCH_STRATEGY = "index"
RUN_FFMPEG = None
RUN_PNG_COMPRESSION = 3
RUN_EXPECTED_PER_CAMERA = None
RUN_ENFORCE_FIXED_COUNT = False
RUN_PAD_LIDAR_IF_SHORT = False
RUN_PAD_DEFAULT_STEP_SEC = 0.1
RUN_TOPIC_CONFIG_OVERRIDE = {}
RUN_SAMPLE_ENABLE = False
RUN_SAMPLE_MODE = "frame"
RUN_SAMPLE_INTERVAL = 1.0
RUN_PREFERRED_LIDAR_TOPICS = [
    "/redundancy/sensor/lidar_ml/multi_scan",
    "/sensor/lidar_ml/multi_scan",
]
# =====================================================================

# 全局锁：避免多线程打印混乱
print_lock = threading.Lock()

def log_print(msg):
    """线程安全的打印函数"""
    with print_lock:
        print(msg)

def _format_sec_nsec(sec, nsec):
    sec_i = int(sec)
    nsec_i = max(0, int(nsec))
    sec_i += nsec_i // 1_000_000_000
    nsec_i %= 1_000_000_000
    micro = (nsec_i + 500) // 1000
    sec_i += micro // 1_000_000
    micro %= 1_000_000
    return f"{sec_i:010d}.{micro:06d}"

def _sec_nsec_to_float(sec, nsec):
    try:
        return float(sec) + float(nsec) / 1e9
    except Exception:
        return 0.0

def _pad_lidar_series(timestamps, times, expected, default_step_sec=0.1):
    if not timestamps or not times or expected is None:
        return timestamps, times
    expected = int(expected)
    if expected <= 0:
        return timestamps, times
    n = len(timestamps)
    if n >= expected:
        return timestamps[:expected], times[:expected]

    step = None
    if len(times) >= 3:
        diffs = [times[i] - times[i - 1] for i in range(1, len(times)) if (times[i] - times[i - 1]) > 0]
        if diffs:
            diffs.sort()
            step = diffs[len(diffs) // 2]
    if step is None or step <= 0:
        step = float(default_step_sec)

    last = float(times[-1])
    while len(timestamps) < expected:
        last += step
        sec = int(last)
        nsec = int(round((last - sec) * 1e9))
        if nsec >= 1_000_000_000:
            sec += 1
            nsec -= 1_000_000_000
        timestamps.append(_format_sec_nsec(sec, nsec))
        times.append(float(sec) + float(nsec) / 1e9)
    return timestamps, times

def _get_stamp_sec_nsec(stamp):
    if stamp is None:
        return None, None
    if hasattr(stamp, 'sec'):
        sec = stamp.sec
    elif hasattr(stamp, 'secs'):
        sec = stamp.secs
    else:
        sec = None
    if hasattr(stamp, 'nsec'):
        nsec = stamp.nsec
    elif hasattr(stamp, 'nsecs'):
        nsec = stamp.nsecs
    elif hasattr(stamp, 'nanosec'):
        nsec = stamp.nanosec
    elif hasattr(stamp, 'nanosecs'):
        nsec = stamp.nanosecs
    else:
        nsec = None
    return sec, nsec

def _get_bag_time_sec_nsec(bag_time):
    if bag_time is None:
        return None, None
    if isinstance(bag_time, int):
        sec = int(bag_time // 1_000_000_000)
        nsec = int(bag_time % 1_000_000_000)
        return sec, nsec
    if hasattr(bag_time, 'to_sec'):
        t = float(bag_time.to_sec())
        sec = int(t)
        nsec = int(round((t - sec) * 1e9))
        return sec, nsec
    if hasattr(bag_time, 'sec') and hasattr(bag_time, 'nsec'):
        return bag_time.sec, bag_time.nsec
    if hasattr(bag_time, 'secs') and hasattr(bag_time, 'nsecs'):
        return bag_time.secs, bag_time.nsecs
    return None, None

def get_timestamp(msg, bag_time=None, source="header"):
    if source == "bag":
        sec, nsec = _get_bag_time_sec_nsec(bag_time)
    else:
        stamp = getattr(getattr(msg, "header", None), "stamp", None)
        sec, nsec = _get_stamp_sec_nsec(stamp)
        if sec is None or nsec is None:
            sec, nsec = _get_bag_time_sec_nsec(bag_time)
    if sec is None or nsec is None:
        sec, nsec = 0, 0
    return _format_sec_nsec(sec, nsec), _sec_nsec_to_float(sec, nsec)

def _iter_messages(bag_path, topics=None):
    if rosbag_py is not None:
        bag = rosbag_py.Bag(bag_path, 'r')
        try:
            for topic, msg, t in bag.read_messages(topics=topics):
                yield topic, msg, t
        finally:
            bag.close()
        return

    with RosbagsReader(Path(bag_path)) as reader:
        topics_set = set(topics) if topics else None
        conns = [c for c in reader.connections if (topics_set is None or c.topic in topics_set)]
        for c in conns:
            msgdef = getattr(c, 'msgdef', None)
            msgdef_text = None
            if msgdef is not None:
                msgdef_text = getattr(msgdef, 'data', None)
                if msgdef_text is None and isinstance(msgdef, str):
                    msgdef_text = msgdef
            if msgdef_text:
                try:
                    _TYPESTORE.register(get_types_from_msg(msgdef_text, c.msgtype))
                except Exception:
                    pass
        for c, t, rawdata in reader.messages(conns):
            try:
                msg = _TYPESTORE.deserialize_ros1(rawdata, c.msgtype)
            except Exception:
                continue
            yield c.topic, msg, int(t)

def _list_topics(bag_path):
    if rosbag_py is not None:
        bag = rosbag_py.Bag(bag_path, 'r')
        try:
            _, topics_info = bag.get_type_and_topic_info()
            return list(topics_info.keys())
        finally:
            bag.close()
    with RosbagsReader(Path(bag_path)) as reader:
        return sorted({c.topic for c in reader.connections})

def _resolve_ffmpeg_path(ffmpeg_path=None):
    if ffmpeg_path and os.path.isfile(ffmpeg_path):
        return ffmpeg_path
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        exe2 = imageio_ffmpeg.get_ffmpeg_exe()
        if exe2 and os.path.isfile(exe2):
            return exe2
    except Exception:
        pass
    return None

def detect_lidar_topic(bag_path):
    try:
        topics = _list_topics(bag_path)
    except Exception:
        return None
    for t in RUN_PREFERRED_LIDAR_TOPICS:
        if t in topics:
            return t

    candidates = []
    for t in topics:
        lt = t.lower()
        score = 0
        if "lidar" in lt:
            score += 100
        if "velodyne" in lt:
            score += 80
        if "points" in lt:
            score += 20
        if "scan" in lt:
            score += 10
        if score > 0:
            candidates.append((score, t))

    if not candidates:
        return None
    candidates.sort(key=lambda x: (-x[0], x[1]))
    return candidates[0][1]

def extract_topic_data(bag_path, topic, timestamp_source="header"):
    """提取单个话题的H264流和时间戳列表"""
    if not os.path.exists(bag_path):
        log_print(f"❌ 错误：找不到bag文件 {bag_path}")
        return None, None, None
    
    # bytearray 避免大量 bytes 反复拼接导致的额外内存拷贝。
    h264_stream = bytearray()
    timestamp_list = []
    time_sec_list = []
    
    try:
        msg_count = 0
        for _, msg, t in _iter_messages(bag_path, topics=[topic]):
            data = getattr(msg, 'data', None)
            if data is None:
                continue
            h264_stream.extend(data)
            ts_str, ts_sec = get_timestamp(msg, t, source=timestamp_source)
            timestamp_list.append(ts_str)
            time_sec_list.append(ts_sec)
            msg_count += 1
        log_print(f"✅ 提取 [{os.path.basename(bag_path)}][{topic}] 消息数：{msg_count}")
        return h264_stream, timestamp_list, time_sec_list
    except Exception as e:
        log_print(f"❌ 提取 [{os.path.basename(bag_path)}][{topic}] 失败：{str(e)}")
        return None, None, None

def extract_timestamps_only(bag_path, topic, timestamp_source="header"):
    if not os.path.exists(bag_path):
        log_print(f"❌ 错误：找不到bag文件 {bag_path}")
        return None, None
    timestamps = []
    times = []
    try:
        msg_count = 0
        for _, msg, t in _iter_messages(bag_path, topics=[topic]):
            ts_str, ts_sec = get_timestamp(msg, t, source=timestamp_source)
            timestamps.append(ts_str)
            times.append(ts_sec)
            msg_count += 1
        log_print(f"✅ 提取 [{os.path.basename(bag_path)}][{topic}] 消息数：{msg_count}")
        return timestamps, times
    except Exception as e:
        log_print(f"❌ 提取 [{os.path.basename(bag_path)}][{topic}] 失败：{str(e)}")
        return None, None

def _match_lidar_timestamps(camera_times, lidar_timestamps, lidar_times, strategy="index"):
    if not camera_times or not lidar_timestamps or not lidar_times:
        return None
    if strategy == "nearest":
        matched = []
        lidar_idx = 0
        lidar_n = len(lidar_times)
        for ct in camera_times:
            while (lidar_idx + 1 < lidar_n) and (abs(lidar_times[lidar_idx + 1] - ct) <= abs(lidar_times[lidar_idx] - ct)):
                lidar_idx += 1
            matched.append(lidar_timestamps[lidar_idx])
        return matched

    n = min(len(camera_times), len(lidar_timestamps))
    return lidar_timestamps[:n]


def _sample_timestamp_series(timestamp_list, mode, interval, return_indices=False):
    if not timestamp_list:
        return (timestamp_list, []) if return_indices else timestamp_list
    try:
        iv = float(interval)
    except Exception:
        iv = 1.0
    if iv <= 1:
        indices = list(range(len(timestamp_list)))
        return (timestamp_list, indices) if return_indices else timestamp_list
    mode = "time" if str(mode) == "time" else "frame"
    if mode == "frame":
        step = max(1, int(round(iv)))
        indices = list(range(0, len(timestamp_list), step))
        sampled = [timestamp_list[i] for i in indices]
        return (sampled, indices) if return_indices else sampled
    sampled = []
    indices = []
    last_t = None
    for idx, ts in enumerate(timestamp_list):
        try:
            t = float(str(ts).split("_")[0])
        except Exception:
            t = None
        if not sampled:
            sampled.append(ts)
            indices.append(idx)
            last_t = t
            continue
        if t is None or last_t is None:
            sampled.append(ts)
            indices.append(idx)
            last_t = t
            continue
        if (t - last_t) >= iv:
            sampled.append(ts)
            indices.append(idx)
            last_t = t
    if not sampled:
        sampled = timestamp_list
        indices = list(range(len(timestamp_list)))
    return (sampled, indices) if return_indices else sampled

def decode_topic_to_png(h264_stream, timestamp_list, root_save_dir, bag_name, sub_dir, width, height, fps, ffmpeg_path=None, png_compression=3, on_exist="suffix", frame_indices=None):
    """
    解码单个话题为PNG，保存路径：root_save_dir/bag_name/Images_resize/sub_dir
    """
    # 核心路径拼接：根目录 → bag名 → Images_resize → 子目录
    full_save_dir = os.path.join(root_save_dir, bag_name, BASE_SAVE_SUBDIR, sub_dir)
    os.makedirs(full_save_dir, exist_ok=True)
    
    # 使用系统临时目录，避免并发任务同名冲突或污染仓库目录。
    temp_dir = tempfile.mkdtemp(prefix="rosbag-video-extractor-")
    temp_h264 = os.path.join(temp_dir, "input.h264")
    temp_mp4 = os.path.join(temp_dir, "output.mp4")
    
    # 写入H264数据
    with open(temp_h264, 'wb') as f:
        f.write(h264_stream)
    
    if not ffmpeg_path:
        log_print(f"❌ [{bag_name}][{sub_dir}] 未找到ffmpeg，无法转码（可通过 --ffmpeg 指定路径，或安装 imageio-ffmpeg）")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return 0
    if os.path.exists(temp_mp4):
        os.remove(temp_mp4)
    cmd_transcode = [
        ffmpeg_path, "-y",
        "-hide_banner",
        "-loglevel", "warning",
        "-fflags", "+genpts+discardcorrupt",
        "-err_detect", "ignore_err",
        "-analyzeduration", "100M",
        "-probesize", "100M",
        "-framerate", str(fps),
        "-i", temp_h264,
        "-an",
        "-vsync", "0",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        temp_mp4
    ]
    try:
        result = subprocess.run(
            cmd_transcode,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stderr_lines = [ln.strip() for ln in (result.stderr or "").splitlines() if ln.strip()]
        noisy = [ln for ln in stderr_lines if ("h264" in ln.lower() or "decode" in ln.lower() or "error" in ln.lower())]
        if noisy:
            log_print(f"⚠️  [{bag_name}][{sub_dir}] 检测到坏帧/解码告警 {len(noisy)} 条，已按容错模式尽量继续。")
            for ln in noisy[:5]:
                log_print(f"   ↳ {ln}")
    except FileNotFoundError:
        log_print(f"❌ [{bag_name}][{sub_dir}] 未找到ffmpeg可执行文件：{ffmpeg_path}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return 0
    except subprocess.CalledProcessError as e:
        err_txt = (e.stderr or "").strip()
        log_print(f"❌ [{bag_name}][{sub_dir}] 转码失败：{str(e)}")
        if err_txt:
            for ln in err_txt.splitlines()[-8:]:
                ln = ln.strip()
                if ln:
                    log_print(f"   ↳ {ln}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return 0
    
    # 逐帧提取保存
    cap = cv2.VideoCapture(temp_mp4)
    if not cap.isOpened():
        log_print(f"❌ [{bag_name}][{sub_dir}] 无法打开视频文件")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return 0
    
    source_frame_idx = 0
    output_idx = 0
    total_frames = len(timestamp_list)
    target_indices = list(frame_indices) if frame_indices is not None else list(range(total_frames))
    if len(target_indices) != total_frames:
        raise ValueError("frame_indices 数量必须与 timestamp_list 一致")
    saved_count = 0
    last_frame = None
    
    while cap.isOpened() and output_idx < total_frames:
        ret, frame = cap.read()
        if not ret:
            break
        last_frame = frame
        if source_frame_idx < target_indices[output_idx]:
            source_frame_idx += 1
            continue
        
        # 保存PNG
        timestamp = timestamp_list[output_idx]
        png_path = os.path.join(full_save_dir, f"{timestamp}.png")
        if os.path.exists(png_path):
            if on_exist == "skip":
                source_frame_idx += 1
                output_idx += 1
                continue
            if on_exist == "suffix":
                png_path = os.path.join(full_save_dir, f"{timestamp}_f{source_frame_idx:06d}.png")
        ok = cv2.imwrite(png_path, frame, [cv2.IMWRITE_PNG_COMPRESSION, int(png_compression)])
        if ok:
            saved_count += 1
        source_frame_idx += 1
        output_idx += 1

    if output_idx < total_frames:
        if last_frame is not None:
            filler = last_frame
        else:
            filler = np.zeros((int(height), int(width), 3), dtype=np.uint8)
        while output_idx < total_frames:
            timestamp = timestamp_list[output_idx]
            png_path = os.path.join(full_save_dir, f"{timestamp}.png")
            if os.path.exists(png_path):
                if on_exist == "skip":
                    output_idx += 1
                    continue
                if on_exist == "suffix":
                    png_path = os.path.join(full_save_dir, f"{timestamp}_f{target_indices[output_idx]:06d}.png")
            ok = cv2.imwrite(png_path, filler, [cv2.IMWRITE_PNG_COMPRESSION, int(png_compression)])
            if ok:
                saved_count += 1
            output_idx += 1
    
    # 清理资源
    cap.release()
    shutil.rmtree(temp_dir, ignore_errors=True)
    
    log_print(f"✅ [{bag_name}][{sub_dir}] 保存完成：{saved_count} 帧 | 路径：{full_save_dir}")
    return saved_count

def process_single_bag(bag_file, root_save_dir="."):
    """
    处理单个bag文件的所有话题
    :param bag_file: bag文件路径
    :param root_save_dir: 根保存目录（默认当前目录）
    """
    if not bag_file.endswith('.bag'):
        log_print(f"⚠️  跳过非bag文件：{bag_file}")
        return 0
    
    # 获取bag文件名（不含后缀）
    bag_name = os.path.splitext(os.path.basename(bag_file))[0]
    log_print(f"\n========== 开始处理：{bag_name} ==========")
    log_print(f"📁 根保存目录：{os.path.abspath(root_save_dir)}")
    
    total_saved = 0
    lidar_timestamps = None
    lidar_times = None
    timestamp_source = getattr(process_single_bag, "_timestamp_source", "header")
    use_lidar_timestamp = getattr(process_single_bag, "_use_lidar_timestamp", False)
    lidar_topic = getattr(process_single_bag, "_lidar_topic", None)
    match_strategy = getattr(process_single_bag, "_match_strategy", "index")
    ffmpeg_path = getattr(process_single_bag, "_ffmpeg_path", None)
    png_compression = getattr(process_single_bag, "_png_compression", 3)
    on_exist = getattr(process_single_bag, "_on_exist", "suffix")
    clean_bag_dir = getattr(process_single_bag, "_clean_bag_dir", False)
    expected_per_camera = getattr(process_single_bag, "_expected_per_camera", None)
    enforce_fixed_count = getattr(process_single_bag, "_enforce_fixed_count", False)
    pad_lidar_if_short = getattr(process_single_bag, "_pad_lidar_if_short", False)
    pad_step_sec = getattr(process_single_bag, "_pad_step_sec", RUN_PAD_DEFAULT_STEP_SEC)
    sample_enable = bool(getattr(process_single_bag, "_sample_enable", False))
    sample_mode = getattr(process_single_bag, "_sample_mode", "frame")
    sample_interval = float(getattr(process_single_bag, "_sample_interval", 1.0))
    topic_config = getattr(process_single_bag, "_topic_config", TOPIC_CONFIG)

    if clean_bag_dir:
        bag_out_dir = os.path.join(root_save_dir, bag_name)
        if os.path.isdir(bag_out_dir):
            try:
                shutil.rmtree(bag_out_dir)
                log_print(f"🧹 已清理输出目录：{bag_out_dir}")
            except Exception as e:
                log_print(f"⚠️  清理输出目录失败：{bag_out_dir} | {str(e)}")

    if use_lidar_timestamp:
        timestamp_source = "header"
        lidar_candidates = []
        if lidar_topic:
            lidar_candidates.append(lidar_topic)
        for t in RUN_PREFERRED_LIDAR_TOPICS:
            if t not in lidar_candidates:
                lidar_candidates.append(t)
        auto_lidar_topic = detect_lidar_topic(bag_file)
        if auto_lidar_topic and auto_lidar_topic not in lidar_candidates:
            lidar_candidates.append(auto_lidar_topic)
        for candidate_topic in lidar_candidates:
            log_print(f"🧭 尝试lidar基准话题：{candidate_topic} | 匹配方式：{match_strategy}")
            lidar_timestamps, lidar_times = extract_timestamps_only(bag_file, candidate_topic, timestamp_source=timestamp_source)
            if lidar_timestamps:
                break
        if not lidar_timestamps:
            wide_topic = "/sensor/camera_front_wide/video"
            log_print("⚠️  未找到可用lidar话题，回退使用wide话题时间戳作为基准")
            lidar_timestamps, lidar_times = extract_timestamps_only(bag_file, wide_topic, timestamp_source=timestamp_source)
        if not lidar_timestamps:
            log_print("❌ lidar与wide均未提取到时间戳，改用各相机原始时间戳命名")
            use_lidar_timestamp = False
        elif enforce_fixed_count and expected_per_camera and expected_per_camera > 0:
            if len(lidar_timestamps) >= int(expected_per_camera):
                lidar_timestamps = lidar_timestamps[: int(expected_per_camera)]
                lidar_times = lidar_times[: int(expected_per_camera)]
            else:
                log_print(f"⚠️  [{bag_name}] 基准帧数不足：{len(lidar_timestamps)} < {int(expected_per_camera)}")
                if pad_lidar_if_short:
                    lidar_timestamps, lidar_times = _pad_lidar_series(
                        list(lidar_timestamps),
                        list(lidar_times),
                        expected=int(expected_per_camera),
                        default_step_sec=float(pad_step_sec),
                    )
                    log_print(f"🧩 [{bag_name}] 已补齐基准时间戳到 {int(expected_per_camera)}")

    # 处理当前bag的所有配置话题
    for topic, sub_dir in topic_config.items():
        # 提取数据
        h264_stream, cam_timestamp_list, cam_time_list = extract_topic_data(bag_file, topic, timestamp_source=timestamp_source)
        if not h264_stream or not cam_timestamp_list:
            continue

        if use_lidar_timestamp:
            if enforce_fixed_count and lidar_timestamps:
                timestamp_list = lidar_timestamps
            else:
                matched = _match_lidar_timestamps(cam_time_list, lidar_timestamps, lidar_times, strategy=match_strategy)
                if not matched:
                    timestamp_list = cam_timestamp_list
                else:
                    timestamp_list = matched
        else:
            timestamp_list = cam_timestamp_list
        frame_indices = None
        if sample_enable:
            timestamp_list, frame_indices = _sample_timestamp_series(
                timestamp_list, sample_mode, sample_interval, return_indices=True
            )
        
        # 解码保存
        saved = decode_topic_to_png(
            h264_stream=h264_stream,
            timestamp_list=timestamp_list,
            root_save_dir=root_save_dir,
            bag_name=bag_name,
            sub_dir=sub_dir,
            width=CAMERA_CONFIG["width"],
            height=CAMERA_CONFIG["height"],
            fps=CAMERA_CONFIG["frame_rate"],
            ffmpeg_path=ffmpeg_path,
            png_compression=png_compression,
            on_exist=on_exist,
            frame_indices=frame_indices,
        )
        if saved != len(timestamp_list):
            log_print(f"⚠️  [{bag_name}][{sub_dir}] 期望{len(timestamp_list)}帧，实际写入{saved}帧")
        total_saved += saved
    
    log_print(f"========== 完成处理：{bag_name} | 总计保存：{total_saved} 帧 ==========")
    return total_saved

def process_bag_folder(bag_dir, root_save_dir, thread_num):
    """多线程处理文件夹下所有bag文件（强制指定根保存目录）"""
    # 校验根保存目录：不存在则创建
    if not os.path.exists(root_save_dir):
        os.makedirs(root_save_dir)
        log_print(f"📁 根保存目录不存在，已创建：{os.path.abspath(root_save_dir)}")
    
    # 获取文件夹下所有bag文件
    bag_files = [
        os.path.join(bag_dir, f) 
        for f in os.listdir(bag_dir) 
        if f.endswith('.bag')
    ]
    if not bag_files:
        log_print(f"❌ 文件夹 {bag_dir} 中未找到任何bag文件")
        return 0
    
    log_print(f"\n===== 开始批量处理文件夹：{bag_dir} =====")
    log_print(f"📂 共发现 {len(bag_files)} 个bag文件")
    log_print(f"🔧 使用 {thread_num} 个线程并行处理")
    log_print(f"📁 所有文件将保存至根目录：{os.path.abspath(root_save_dir)}")
    
    total_saved_all = 0
    start_time = time.time()
    
    # 多线程执行
    with ThreadPoolExecutor(max_workers=thread_num) as executor:
        # 提交所有任务（传递根保存目录）
        future_to_bag = {
            executor.submit(process_single_bag, bag_file, root_save_dir): bag_file
            for bag_file in bag_files
        }
        
        # 追踪完成状态
        completed = 0
        for future in as_completed(future_to_bag):
            bag_file = future_to_bag[future]
            completed += 1
            try:
                saved = future.result()
                total_saved_all += saved
                log_print(f"\n📊 进度：{completed}/{len(bag_files)} | 累计保存：{total_saved_all} 帧")
            except Exception as e:
                log_print(f"❌ 处理 {os.path.basename(bag_file)} 时发生未捕获异常：{str(e)}")
    
    # 统计耗时
    elapsed_time = time.time() - start_time
    log_print(f"\n===== 批量处理完成 =====")
    log_print(f"⏱️  总耗时：{elapsed_time:.2f} 秒")
    log_print(f"📈 总计保存PNG帧：{total_saved_all} 个")
    log_print(f"📁 所有文件最终根目录：{os.path.abspath(root_save_dir)}")
    
    return total_saved_all

def main():
    # 命令行参数解析
    parser = argparse.ArgumentParser(description='ROS Bag视频帧提取工具（支持单文件/批量文件夹）')
    parser.add_argument('--mode', type=str, default=RUN_MODE, choices=['single', 'batch'],
                        help='运行模式：single（单个bag）/ batch（文件夹批量）')
    parser.add_argument('--path', type=str, default=RUN_PATH,
                        help='文件/文件夹路径：single模式填bag文件路径，batch模式填文件夹路径')
    parser.add_argument('--save-dir', type=str, default=RUN_SAVE_DIR,
                        help='根保存目录（batch模式必填，single模式可选，默认当前目录）')
    parser.add_argument('--threads', type=int, default=RUN_THREADS,
                        help=f'批量模式线程数（默认：{DEFAULT_THREADS}）')
    parser.add_argument('--timestamp-source', type=str, default=RUN_TIMESTAMP_SOURCE, choices=['header', 'bag'],
                        help='时间戳来源：header=msg.header.stamp（默认）/ bag=bag记录时间')
    parser.add_argument('--use-lidar-timestamp', action='store_true', default=RUN_USE_LIDAR_TIMESTAMP,
                        help='导出图片按lidar时间戳命名（默认按相机话题时间戳命名）')
    parser.add_argument('--lidar-topic', type=str, default=RUN_LIDAR_TOPIC,
                        help='lidar话题名（不填则自动识别，识别失败会回退到相机时间戳）')
    parser.add_argument('--match-strategy', type=str, default=RUN_MATCH_STRATEGY, choices=['index', 'nearest'],
                        help='相机帧与lidar帧匹配：index=按顺序对齐/ nearest=按最近时间匹配')
    parser.add_argument('--ffmpeg', type=str, default=RUN_FFMPEG,
                        help='ffmpeg可执行文件路径（不填则自动从PATH或imageio-ffmpeg查找）')
    parser.add_argument('--png-compression', type=int, default=RUN_PNG_COMPRESSION,
                        help='PNG压缩等级0-9（0最大最快，9最小最慢，默认3）')
    parser.add_argument('--expected-per-camera', type=int, default=RUN_EXPECTED_PER_CAMERA,
                        help='期望每个相机导出的帧数（按lidar命名时用于截断/补齐）')
    parser.add_argument('--enforce-fixed-count', action='store_true', default=RUN_ENFORCE_FIXED_COUNT,
                        help='按lidar时间戳强制每个相机输出固定数量图片（不足则用占位帧补齐）')
    parser.add_argument('--pad-lidar-if-short', action='store_true', default=RUN_PAD_LIDAR_IF_SHORT,
                        help='当lidar帧数不足expected时，用固定步长外推补齐时间戳数量')
    parser.add_argument('--pad-step-sec', type=float, default=RUN_PAD_DEFAULT_STEP_SEC,
                        help='补齐lidar时间戳时的默认步长（秒），默认0.1')
    parser.add_argument(
        "--on-exist",
        choices=["suffix", "overwrite", "skip"],
        default="suffix",
        help="输出PNG已存在时：suffix=添加_f后缀保留两份 / overwrite=覆盖 / skip=跳过",
    )
    parser.add_argument(
        "--clean-bag-dir",
        action="store_true",
        help="处理bag前先删除该bag对应的输出目录（避免重复解包产生_f文件）",
    )
    parser.add_argument("--camera-topic", action="append", default=None)
    parser.add_argument("--sample-enable", action="store_true", default=RUN_SAMPLE_ENABLE)
    parser.add_argument("--sample-mode", type=str, default=RUN_SAMPLE_MODE, choices=["frame", "time"])
    parser.add_argument("--sample-interval", type=float, default=RUN_SAMPLE_INTERVAL)
    
    args = parser.parse_args()
    process_single_bag._timestamp_source = args.timestamp_source
    process_single_bag._use_lidar_timestamp = args.use_lidar_timestamp
    process_single_bag._lidar_topic = args.lidar_topic
    process_single_bag._match_strategy = args.match_strategy
    process_single_bag._ffmpeg_path = _resolve_ffmpeg_path(args.ffmpeg)
    process_single_bag._png_compression = args.png_compression
    process_single_bag._expected_per_camera = args.expected_per_camera
    process_single_bag._enforce_fixed_count = args.enforce_fixed_count
    process_single_bag._pad_lidar_if_short = args.pad_lidar_if_short
    process_single_bag._pad_step_sec = args.pad_step_sec
    process_single_bag._on_exist = args.on_exist
    process_single_bag._clean_bag_dir = bool(args.clean_bag_dir)
    selected_topics = args.camera_topic if args.camera_topic else []
    if selected_topics:
        process_single_bag._topic_config = {k: v for k, v in TOPIC_CONFIG.items() if k in selected_topics}
    else:
        process_single_bag._topic_config = RUN_TOPIC_CONFIG_OVERRIDE if RUN_TOPIC_CONFIG_OVERRIDE else TOPIC_CONFIG
    process_single_bag._sample_enable = bool(args.sample_enable)
    process_single_bag._sample_mode = args.sample_mode
    process_single_bag._sample_interval = float(args.sample_interval) if float(args.sample_interval) > 0 else 1.0
    
    # 执行对应模式
    if args.mode == 'single':
        # 单文件模式：save-dir可选，默认当前目录
        root_save_dir = args.save_dir if args.save_dir else "."
        if not args.path or not os.path.exists(args.path):
            log_print(f"❌ 错误：找不到文件 {args.path}")
            return
        process_single_bag(args.path, root_save_dir)
    
    elif args.mode == 'batch':
        # 批量模式：强制检查save-dir参数
        if not args.save_dir:
            log_print(f"❌ 批量模式必须指定 --save-dir 参数！")
            parser.print_help()
            return
        if not os.path.isdir(args.path):
            log_print(f"❌ 错误：{args.path} 不是有效文件夹")
            return
        process_bag_folder(args.path, args.save_dir, args.threads)

if __name__ == "__main__":
    main()
