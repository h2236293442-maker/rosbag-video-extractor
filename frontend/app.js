(() => {
  const API_BASE = window.location.origin;

  const inputModeRadios = Array.from(document.querySelectorAll('input[name="input-mode"]'));
  const selectSingleBagBtn = document.getElementById("select-single-bag-btn");
  const singleBagPathDisplay = document.getElementById("single-bag-path-display");
  const bagTagList = document.getElementById("bag-tag-list");
  const singleBagGroup = document.getElementById("single-bag-group");
  const uploadFolderGroup = document.getElementById("upload-folder-group");
  const pathHelpText = document.getElementById("path-help-text");

  const topicGrid = document.getElementById("topic-checkbox-grid");
  const topicTagList = document.getElementById("topic-tag-list");
  const customTopicInput = document.getElementById("custom-topic-input");
  const addCustomTopicBtn = document.getElementById("add-custom-topic-btn");
  const customTopicHint = document.getElementById("topic-custom-hint");

  const samplingEnabledInput = document.getElementById("sampling-enabled");
  const samplingDetailGroup = document.getElementById("sampling-detail-group");
  const sampleRateInput = document.getElementById("sample-rate");
  const samplingStatus = document.getElementById("sampling-status");

  const uploadPathDisplay = document.getElementById("upload-path-display");
  const exportPathDisplay = document.getElementById("export-path-display");

  const runButton = document.getElementById("run-btn");
  const stopButton = document.getElementById("stop-btn");

  const previewChip = document.getElementById("preview-chip");
  const previewHint = document.getElementById("preview-empty-hint");
  const previewBagName = document.getElementById("preview-bag-name");
  const previewTopicCount = document.getElementById("preview-topic-count");
  const previewSamplingMode = document.getElementById("preview-sampling-mode");
  const previewFrameImage = document.getElementById("preview-frame-image");
  const previewNoImage = document.getElementById("preview-no-image");
  const previewTopicSelect = document.getElementById("preview-topic-select");
  const previewBagSelect = document.getElementById("preview-bag-select");
  const previewPrevBtn = document.getElementById("preview-prev-btn");
  const previewPlayBtn = document.getElementById("preview-play-btn");
  const previewNextBtn = document.getElementById("preview-next-btn");
  const previewFrameSlider = document.getElementById("preview-frame-slider");
  const previewFrameCounter = document.getElementById("preview-frame-counter");
  const previewFrameName = document.getElementById("preview-frame-name");

  const timelineCard = document.getElementById("timeline-card");
  const timelineStatusChip = document.getElementById("timeline-status-chip");
  const timelineCurrentText = document.getElementById("timeline-current-text");
  const timelineStepSample = document.getElementById("timeline-step-sample");
  const timelineSteps = Array.from(document.querySelectorAll(".timeline-step"));
  const timelineDots = Array.from(document.querySelectorAll(".line-dot[data-step]"));

  const validationModal = document.getElementById("validation-modal");
  const validationModalTitle = document.getElementById("validation-modal-title");
  const validationModalDesc = document.getElementById("validation-modal-desc");
  const validationModalList = document.getElementById("validation-modal-list");
  const validationModalClose = document.getElementById("validation-modal-close");
  const validationModalConfirm = document.getElementById("validation-modal-confirm");

  const clearLogBtn = document.getElementById("clear-log-btn");
  const logPanel = document.getElementById("log-panel");
  const folderButtons = document.querySelectorAll("[data-folder-type]");

  const defaultTopics = [
    "/sensor/camera_front_wide/video",
    "/sensor/camera_front_far/video",
    "/sensor/camera_right_front/video",
    "/sensor/camera_left_front/video",
  ];

  const state = {
    singleBagPath: "",
    bagFiles: [],
    uploadPath: "",
    exportPath: "",
    selectedTopics: [],
    customTopics: [],
    isRunning: false,
    pendingRunConfirm: false,
    logOffset: 0,
    logPollTimer: null,
    stopRequested: false,
    currentStep: 0,
    tracebackFoldNotified: false,
    permissionHintShown: false,
    processedBags: new Set(),
    framesByBag: {}, // Structured as { bagName: { topicKey: [frames] } }
    previewBagKey: "",
    previewTopicKey: "",
    previewFrameIndex: 0,
    previewPlaying: false,
    previewTimer: null,
    previewUnlocked: false,
  };

  const pathBaseName = (path) => (path || "").split(/[\\/]/).pop() || "";
  const getInputMode = () => inputModeRadios.find((item) => item.checked)?.value || "single";
  const isFolderMode = () => getInputMode() === "multi";
  const hasSourceInput = () => (isFolderMode() ? Boolean(state.uploadPath) : Boolean(state.singleBagPath));
  const isTopicValid = (topic) => topic.startsWith("/") && !/\s/.test(topic);

  const requestJson = async (path, init = {}) => {
    const response = await fetch(`${API_BASE}${path}`, init);
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || `请求失败: ${response.status}`);
    }
    return data;
  };

  const appendLog = (level, message, ts) => {
    const now = new Date();
    const timeText =
      ts ||
      `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:${String(
        now.getSeconds()
      ).padStart(2, "0")}`;
    const item = document.createElement("div");
    item.className = "log-item";
    item.innerHTML = `
      <span class="log-time">${timeText}</span>
      <span class="log-level ${level === "ERROR" ? "error" : level === "WARN" ? "warn" : ""}">${level}</span>
      <span class="log-msg">${message}</span>
    `;
    logPanel.appendChild(item);
    logPanel.scrollTop = logPanel.scrollHeight;
  };

  const renderTagList = (container, items, emptyText) => {
    container.innerHTML = "";
    if (!items.length) {
      const empty = document.createElement("li");
      empty.className = "tag tag-empty";
      empty.textContent = emptyText;
      container.appendChild(empty);
      return;
    }
    items.forEach((item) => {
      const tag = document.createElement("li");
      tag.className = "tag";
      tag.textContent = item;
      container.appendChild(tag);
    });
  };

  const getTopicCheckboxes = () => Array.from(topicGrid.querySelectorAll('input[type="checkbox"]'));

  const syncTopicEnabledState = () => {
    const enabled = hasSourceInput();
    topicGrid.classList.toggle("is-disabled", !enabled);
    getTopicCheckboxes().forEach((checkbox) => {
      // 不再禁用 checkbox 的原生 disabled 属性，让它可以被点击
      // checkbox.disabled = !enabled; 
      if (!enabled) {
        checkbox.checked = false;
      }
    });
    if (!enabled) {
      state.selectedTopics = [];
    }
  };

  const renderTopicOptions = () => {
    const allTopics = [...defaultTopics, ...state.customTopics];
    const selectedSet = new Set(state.selectedTopics);
    topicGrid.innerHTML = "";
    allTopics.forEach((topic) => {
      const label = document.createElement("label");
      const checkedAttr = selectedSet.has(topic) ? "checked" : "";
      label.innerHTML = `<input type="checkbox" value="${topic}" ${checkedAttr} /> ${topic}`;
      topicGrid.appendChild(label);
    });
    syncTopicEnabledState();
  };

  const validateSampleRate = (strict) => {
    if (!samplingEnabledInput.checked) {
      return true;
    }
    const raw = sampleRateInput.value.trim();
    if (!raw) {
      sampleRateInput.classList.toggle("input-error", Boolean(strict));
      samplingStatus.textContent = "请输入抽帧帧数";
      samplingStatus.className = strict ? "status status-alert" : "status status-muted";
      return !strict;
    }
    const n = Number(raw);
    const ok = Number.isInteger(n) && n > 0;
    sampleRateInput.classList.toggle("input-error", !ok);
    samplingStatus.textContent = ok ? `抽帧已开启，帧数：${n}` : "请输入大于 0 的整数帧数";
    samplingStatus.className = ok ? "status status-muted" : "status status-alert";
    return ok;
  };

  const updateSamplingUI = () => {
    const enabled = samplingEnabledInput.checked;
    samplingDetailGroup.classList.toggle("is-hidden", !enabled);
    sampleRateInput.disabled = !enabled;
    if (!enabled) {
      sampleRateInput.classList.remove("input-error");
      sampleRateInput.value = "";
      samplingStatus.textContent = "抽帧默认关闭";
      samplingStatus.className = "status status-muted";
      return;
    }
    validateSampleRate(false);
  };

  const syncSourceModeUI = () => {
    const folderMode = isFolderMode();
    singleBagGroup.classList.toggle("is-hidden", folderMode);
    uploadFolderGroup.classList.toggle("is-hidden", !folderMode);
    state.singleBagPath = "";
    state.bagFiles = [];
    pathHelpText.textContent = folderMode
      ? "多包模式：选择输入目录和导出目录。"
      : "单包模式：选择 Bag 文件和导出目录。";
  };

  const setTimelineState = (text, ready = false, failed = false, stopping = false) => {
    timelineStatusChip.textContent = text;
    timelineStatusChip.classList.toggle("ready", ready);
    timelineStatusChip.classList.toggle("failed", failed);
    timelineStatusChip.classList.toggle("stopping", stopping);
  };

  const setTimelineCurrentText = (text) => {
    if (timelineCurrentText) {
      timelineCurrentText.textContent = text;
    }
  };

  const getCurrentFrames = () => {
    if (!state.previewBagKey || !state.previewTopicKey) return [];
    return state.framesByBag[state.previewBagKey]?.[state.previewTopicKey] || [];
  };

  const stopPreviewPlayback = () => {
    if (state.previewTimer) {
      clearInterval(state.previewTimer);
      state.previewTimer = null;
    }
    state.previewPlaying = false;
    if (previewPlayBtn) {
      previewPlayBtn.textContent = "播放";
    }
  };

  const renderPreviewFrame = () => {
    if (!state.previewUnlocked) {
      previewFrameSlider.max = "0";
      previewFrameSlider.value = "0";
      previewFrameSlider.disabled = true;
      previewPrevBtn.disabled = true;
      previewNextBtn.disabled = true;
      previewPlayBtn.disabled = true;
      previewFrameCounter.textContent = "0 / 0";
      previewFrameName.textContent = "-";
      previewFrameImage.src = "";
      previewFrameImage.classList.add("is-hidden");
      previewNoImage.classList.remove("is-hidden");
      stopPreviewPlayback();
      return;
    }
    const frames = getCurrentFrames();
    const total = frames.length;
    const hasFrame = total > 0;
    previewFrameSlider.max = String(Math.max(0, total - 1));
    previewFrameSlider.value = String(Math.min(state.previewFrameIndex, Math.max(0, total - 1)));
    previewFrameSlider.disabled = !hasFrame;
    previewPrevBtn.disabled = !hasFrame;
    previewNextBtn.disabled = !hasFrame;
    previewPlayBtn.disabled = total <= 1;
    previewFrameCounter.textContent = hasFrame ? `${state.previewFrameIndex + 1} / ${total}` : "0 / 0";

    if (!hasFrame) {
      previewFrameImage.src = "";
      previewFrameImage.classList.add("is-hidden");
      previewNoImage.classList.remove("is-hidden");
      previewFrameName.textContent = "-";
      stopPreviewPlayback();
      return;
    }

    const current = frames[state.previewFrameIndex];
    previewFrameImage.src = current.url;
    previewFrameImage.classList.remove("is-hidden");
    previewNoImage.classList.add("is-hidden");
    previewFrameName.textContent = current.name;
  };

  const setPreviewTopic = (topicKey) => {
    state.previewTopicKey = topicKey;
    state.previewFrameIndex = 0;
    renderPreviewFrame();
    refreshView();
  };

  const setPreviewBag = (bagKey) => {
    state.previewBagKey = bagKey;
    state.previewFrameIndex = 0;
    
    // Update topic options based on selected bag
    const topicsForBag = state.framesByBag[bagKey] || {};
    const topicKeys = Object.keys(topicsForBag);
    
    previewTopicSelect.innerHTML = "";
    if (!topicKeys.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "该 Bag 下暂无 Topic";
      previewTopicSelect.appendChild(option);
      previewTopicSelect.disabled = true;
      state.previewTopicKey = "";
    } else {
      topicKeys.forEach((key) => {
        const option = document.createElement("option");
        option.value = key;
        option.textContent = key;
        previewTopicSelect.appendChild(option);
      });
      
      // Only enable the topic selector if there are multiple topics
      previewTopicSelect.disabled = topicKeys.length <= 1;
      
      // Try to keep the same topic selected if it exists in the new bag
      const nextTopicKey = topicKeys.includes(state.previewTopicKey) ? state.previewTopicKey : topicKeys[0];
      previewTopicSelect.value = nextTopicKey;
      state.previewTopicKey = nextTopicKey;
    }
    
    renderPreviewFrame();
    refreshView();
  };

  const stepPreviewFrame = (delta) => {
    const frames = getCurrentFrames();
    if (!frames.length) {
      return;
    }
    const total = frames.length;
    state.previewFrameIndex = (state.previewFrameIndex + delta + total) % total;
    renderPreviewFrame();
  };

  const togglePreviewPlayback = () => {
    const frames = getCurrentFrames();
    if (frames.length <= 1) {
      return;
    }
    if (state.previewPlaying) {
      stopPreviewPlayback();
      return;
    }
    state.previewPlaying = true;
    previewPlayBtn.textContent = "暂停";
    state.previewTimer = setInterval(() => stepPreviewFrame(1), 180);
  };

  const loadPreviewFramesFromBackend = async () => {
    if (!state.exportPath) {
      return;
    }
    try {
      const q = encodeURIComponent(state.exportPath);
      const res = await requestJson(`/api/preview/list?dir=${q}`);
      state.framesByBag = {};
      
      // The backend returns a flat list of parent_folder -> frames
      (res.topics || []).forEach((topic) => {
        (topic.frames || []).forEach((f) => {
          let bagName = null;
          
          if (!isFolderMode() && state.bagFiles.length > 0) {
            const expectedBag = state.bagFiles[0].name.replace(/\.bag$/, "");
            if (f.path.includes(expectedBag)) {
              bagName = expectedBag;
            }
          } else {
            // Batch mode: check if the path belongs to any of the bags we just processed
            for (const pb of state.processedBags) {
              if (f.path.includes(pb)) {
                bagName = pb;
                break;
              }
            }
          }
          
          if (!bagName) return; // Skip frames that don't belong to the current run
          
          // Since the frame belongs to the bag we just processed, it must be valid.
          // We no longer do strict topic string matching because the backend might rename them 
          // (e.g., camera_front_far -> camera_forward_far).
          
          if (!state.framesByBag[bagName]) {
             state.framesByBag[bagName] = {};
          }
          if (!state.framesByBag[bagName][topic.key]) {
             state.framesByBag[bagName][topic.key] = [];
          }
          
          state.framesByBag[bagName][topic.key].push({
            name: f.name,
            url: `${API_BASE}/api/preview/file?path=${encodeURIComponent(f.path)}`,
          });
        });
      });
      
      // Clean up empty bags/topics that might have been created
      Object.keys(state.framesByBag).forEach(bag => {
        Object.keys(state.framesByBag[bag]).forEach(topic => {
          if (state.framesByBag[bag][topic].length === 0) {
            delete state.framesByBag[bag][topic];
          }
        });
        if (Object.keys(state.framesByBag[bag]).length === 0) {
          delete state.framesByBag[bag];
        }
      });
      
      const bagKeys = Object.keys(state.framesByBag);
      previewBagSelect.innerHTML = "";
      
      if (!bagKeys.length) {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "暂无可预览 Bag";
        previewBagSelect.appendChild(option);
        previewBagSelect.disabled = true;
        
        previewTopicSelect.innerHTML = "<option value=''>暂无可预览 Topic</option>";
        previewTopicSelect.disabled = true;
        
        state.previewBagKey = "";
        state.previewTopicKey = "";
        state.previewFrameIndex = 0;
        renderPreviewFrame();
        return;
      }
      
      bagKeys.forEach((key) => {
        const option = document.createElement("option");
        option.value = key;
        option.textContent = key;
        previewBagSelect.appendChild(option);
      });
      
      // Only enable the bag selector if there are multiple bags
      previewBagSelect.disabled = bagKeys.length <= 1;
      const nextBagKey = bagKeys[0];
      previewBagSelect.value = nextBagKey;
      
      // setPreviewBag will handle populating the topics for this bag
      setPreviewBag(nextBagKey);
      
      appendLog("INFO", `已加载预览帧：找到 ${bagKeys.length} 个 Bag 的数据`);
    } catch (error) {
      appendLog("WARN", `预览加载失败: ${error.message}`);
    }
  };

  const syncTimelineSampleStep = () => {
    if (!timelineStepSample) {
      return;
    }
    const showSample = Boolean(samplingEnabledInput.checked);
    timelineStepSample.classList.toggle("is-hidden", !showSample);
  };

  const markTimelineStep = (stepIndex, status = "active") => {
    state.currentStep = Math.max(state.currentStep, stepIndex);
    const visibleSteps = timelineSteps.filter((item) => !item.classList.contains("is-hidden"));
    visibleSteps.forEach((item, idx) => {
      const itemStep = idx + 1;
      item.classList.remove("is-pending", "is-active", "is-done", "is-failed");
      if (status === "failed" && itemStep === stepIndex) {
        item.classList.add("is-failed");
        return;
      }
      if (itemStep < state.currentStep) {
        item.classList.add("is-done");
      } else if (itemStep === state.currentStep) {
        item.classList.add(status === "done" ? "is-done" : "is-active");
      } else {
        item.classList.add("is-pending");
      }
    });
    const visibleDots = visibleSteps.map((item) => item.querySelector(".line-dot")).filter(Boolean);
    visibleDots.forEach((dot, idx) => {
      dot.classList.toggle("done", idx < state.currentStep || (status === "done" && idx + 1 === state.currentStep));
    });
  };

  const refreshView = () => {
    const bagNames = isFolderMode()
      ? state.uploadPath
        ? [`目录：${state.uploadPath}`]
        : []
      : state.bagFiles.map((f) => f.name);
    renderTagList(bagTagList, bagNames, "暂无已选文件");
    renderTagList(topicTagList, state.selectedTopics, "暂无已选 Topic");

    singleBagPathDisplay.textContent = state.singleBagPath || "未选择路径";
    uploadPathDisplay.textContent = state.uploadPath || "未选择路径";
    exportPathDisplay.textContent = state.exportPath || "未选择路径";
    
    // Update the bag name display to show the currently previewed bag if available
    previewBagName.textContent = state.previewBagKey || bagNames[0] || "未选择";
    previewBagName.title = state.previewBagKey || bagNames[0] || "未选择"; // Update hover title as well
    
    // Calculate total frames for the currently selected preview topic within the selected bag
    const currentTopicFrames = state.previewUnlocked && state.previewBagKey && state.previewTopicKey 
      ? (state.framesByBag[state.previewBagKey]?.[state.previewTopicKey]?.length || 0) 
      : 0;
    previewTopicCount.textContent = String(currentTopicFrames);
    
    previewSamplingMode.textContent = samplingEnabledInput.checked ? "开启" : "关闭";
    const hasFrames = state.previewUnlocked && Object.keys(state.framesByBag).length > 0;

    if (hasSourceInput() && state.selectedTopics.length && hasFrames) {
      previewChip.textContent = "可预览";
      previewChip.classList.add("ready");
      previewHint.textContent = "已加载导出目录图片，可逐帧查看。";
    } else if (hasSourceInput() && state.selectedTopics.length) {
      previewChip.textContent = "待生成";
      previewChip.classList.remove("ready");
      previewHint.textContent = "解析完成后会自动加载导出目录图片。";
    } else if (hasSourceInput()) {
      previewChip.textContent = "待选择 Topic";
      previewChip.classList.remove("ready");
      previewHint.textContent = "已选择输入源，请继续勾选 Topic。";
    } else {
      previewChip.textContent = "待配置";
      previewChip.classList.remove("ready");
      previewHint.textContent = "请选择输入源与 Topic。";
    }
  };

  const openValidationModal = ({ title, desc, messages, success }) => {
    validationModalTitle.textContent = title;
    validationModalDesc.textContent = desc;
    validationModalList.innerHTML = "";
    messages.forEach((text) => {
      const li = document.createElement("li");
      li.className = success ? "status status-success" : "status status-alert";
      li.textContent = text;
      validationModalList.appendChild(li);
    });
    validationModalConfirm.textContent = success ? "开始处理" : "返回修改";
    validationModal.classList.add("is-open");
    validationModal.setAttribute("aria-hidden", "false");
  };

  const closeValidationModal = () => {
    validationModal.classList.remove("is-open");
    validationModal.setAttribute("aria-hidden", "true");
  };

  const updateTimelineByLog = (message) => {
    const text = String(message || "");
    if (/(读取|扫描|开始处理)/.test(text)) {
      markTimelineStep(1);
      setTimelineCurrentText("正在读取 Bag 文件");
    }
    if (/(topic|话题|解析|解码)/i.test(text)) {
      markTimelineStep(2);
      setTimelineCurrentText("正在解析 Topic 数据");
    }
    if (samplingEnabledInput.checked && /(抽帧|sample|采样)/i.test(text)) {
      markTimelineStep(3);
      setTimelineCurrentText("正在执行抽帧策略");
    }
    if (/(保存PNG|导出|完成|最终根目录|saved)/i.test(text)) {
      markTimelineStep(samplingEnabledInput.checked ? 4 : 3, "done");
      setTimelineCurrentText("正在导出 PNG 结果");
    }
  };

  const shouldIgnoreBackendLog = (line) => {
    const raw = String(line?.message || "");
    const msg = raw.toLowerCase();
    const trimmed = raw.trim();
    return (
      msg.includes("non-existing pps") ||
      msg.includes("decode_slice_header error") ||
      msg.includes("no frame!") ||
      msg.includes("last message repeated") ||
      /^traceback \(most recent call last\):$/i.test(trimmed) ||
      /^file ".+", line \d+, in .+$/i.test(trimmed) ||
      /^[a-z_][a-z0-9_]*\(\)$/i.test(trimmed) ||
      trimmed === "^"
    );
  };

  const pollLogs = async () => {
    try {
      const result = await requestJson(`/api/logs?offset=${state.logOffset}`);
      (result.lines || []).forEach((line) => {
        const msg = String(line?.message || "");

        // 智能捕获当前正在处理的 Bag 名称，用于后续过滤预览图片
        const bagMatch = msg.match(/开始处理[:：]\s*([^\s=]+)/);
        if (bagMatch) {
          state.processedBags.add(bagMatch[1].trim());
        }

        if (!state.tracebackFoldNotified && /^traceback \(most recent call last\):$/i.test(msg.trim())) {
          state.tracebackFoldNotified = true;
          appendLog("ERROR", "脚本报错堆栈已折叠，仅显示关键错误。");
        }
        if (shouldIgnoreBackendLog(line)) {
          return;
        }
        appendLog(line.level || "INFO", msg, line.ts);
        updateTimelineByLog(msg);
        if ((line.level || "").toUpperCase() === "ERROR" && state.isRunning) {
          setTimelineState("异常告警", false, true, false);
        }
        if (!state.permissionHintShown && /permissionerror:/i.test(msg)) {
          state.permissionHintShown = true;
          appendLog("WARN", "当前目录无写权限。请手动选择一个可写的导出目录。");
        }
      });
      state.logOffset = Number(result.new_offset || state.logOffset);
      if (!result.running && state.isRunning) {
        state.isRunning = false;
        stopButton.disabled = true;
        if (state.logPollTimer) {
          clearInterval(state.logPollTimer);
          state.logPollTimer = null;
        }
        if (state.stopRequested) {
          state.stopRequested = false;
          setTimelineState("已停止", false, false, false);
          setTimelineCurrentText("任务已停止，进程已退出");
          appendLog("WARN", "停止已确认：后端进程已结束。");
          return;
        }
        const success = Number(result.exit_code) === 0;
        setTimelineState(success ? "已完成" : "失败", success, !success, false);
        setTimelineCurrentText(success ? "处理完成，结果可查看" : "处理失败，请查看错误日志");
        if (!success) {
          markTimelineStep(Math.max(state.currentStep || 1, 1), "failed");
        } else {
          markTimelineStep(samplingEnabledInput.checked ? 4 : 3, "done");
          state.previewUnlocked = true;
          await loadPreviewFramesFromBackend();
          refreshView();
        }
      }
    } catch (error) {
      appendLog("ERROR", `日志轮询失败: ${error.message}`);
      state.isRunning = false;
      stopButton.disabled = true;
      if (state.logPollTimer) {
        clearInterval(state.logPollTimer);
        state.logPollTimer = null;
      }
      setTimelineState("连接失败", false, true, false);
      setTimelineCurrentText("日志连接中断，请检查后端服务");
    }
  };

  const runBackendTask = async () => {
    const payload = {
      mode: isFolderMode() ? "batch" : "single",
      path: isFolderMode() ? state.uploadPath : state.singleBagPath,
      save_dir: state.exportPath,
      topics: state.selectedTopics,
      sample_enable: samplingEnabledInput.checked,
      sample_mode: "frame",
      sample_interval: Number(sampleRateInput.value || 1),
    };

    timelineCard.classList.remove("is-collapsed");
    timelineDots.forEach((dot) => dot.classList.remove("done"));
    syncTimelineSampleStep();
    state.currentStep = 1;
    markTimelineStep(1);
    setTimelineState("进行中", true, false, false);
    setTimelineCurrentText("任务已启动，等待脚本输出");
    state.isRunning = true;
    state.stopRequested = false;
    state.tracebackFoldNotified = false;
    state.permissionHintShown = false;
    state.processedBags.clear();
    state.logOffset = 0;
    logPanel.innerHTML = "";
    state.previewUnlocked = false;
    state.framesByBag = {};
    state.previewBagKey = "";
    state.previewTopicKey = "";
    state.previewFrameIndex = 0;
    previewBagSelect.innerHTML = "";
    previewBagSelect.disabled = true;
    previewTopicSelect.innerHTML = "";
    previewTopicSelect.disabled = true;
    renderPreviewFrame();
    stopPreviewPlayback();
    stopButton.disabled = false;

    try {
      await requestJson("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      appendLog("INFO", "任务已提交，开始接收真实日志。");
      await pollLogs();
      state.logPollTimer = setInterval(pollLogs, 1000);
    } catch (error) {
      state.isRunning = false;
      stopButton.disabled = true;
      setTimelineState("启动失败", false, true, false);
      setTimelineCurrentText("任务启动失败");
      appendLog("ERROR", `任务启动失败: ${error.message}`);
    }
  };

  const validateBeforeRun = () => {
    const issues = [];
    if (!hasSourceInput()) {
      issues.push(isFolderMode() ? "请先选择输入目录（多包模式）" : "请先选择 Bag 文件（单包模式）");
    }
    if (!state.selectedTopics.length) {
      issues.push("请至少选择一个 Topic");
    }
    if (state.selectedTopics.some((topic) => !isTopicValid(topic))) {
      issues.push("存在非法 Topic：需以 / 开头，且不能包含空格");
    }

    if (!state.exportPath) {
      if (isFolderMode() && state.uploadPath) {
        state.exportPath = state.uploadPath;
        appendLog("WARN", "未选择导出目录，已默认使用输入目录。");
      } else if (!isFolderMode() && state.singleBagPath) {
        const parts = state.singleBagPath.split(/[\\/]/);
        parts.pop();
        state.exportPath = parts.join("/") || state.singleBagPath;
        appendLog("WARN", "未选择导出目录，已默认设置为 Bag 同目录。");
      } else {
        issues.push("请先选择导出目录");
      }
    }
    if (!validateSampleRate(true)) {
      issues.push("抽帧参数不合法，请输入大于 0 的整数");
    }

    if (issues.length) {
      openValidationModal({
        title: "校验未通过",
        desc: "请先修正以下配置项，再提交执行：",
        messages: issues,
        success: false,
      });
      refreshView();
      return;
    }
    runBackendTask();
  };

  const stopExecutionFlow = async () => {
    if (!state.isRunning) {
      appendLog("WARN", "当前没有运行中的任务。");
      return;
    }
    state.stopRequested = true;
    stopButton.disabled = true;
    setTimelineState("停止中", false, false, true);
    setTimelineCurrentText("正在等待后端进程安全退出");
    try {
      await requestJson("/api/stop", { method: "POST" });
      appendLog("WARN", "已发送停止请求，等待进程退出确认...");
      if (!state.logPollTimer) {
        state.logPollTimer = setInterval(pollLogs, 800);
      }
    } catch (error) {
      state.stopRequested = false;
      appendLog("ERROR", `停止失败: ${error.message}`);
      setTimelineState("停止失败", false, true, false);
      setTimelineCurrentText("停止请求失败");
    }
  };

  const pickDirectory = async (type) => {
    try {
      const result = await requestJson("/api/select?kind=dir&multi=0");
      const picked = result.paths || [];
      if (!picked.length) {
        appendLog("WARN", "用户取消了目录选择。");
        return;
      }
      state[`${type}Path`] = picked[0];
      appendLog("INFO", `${type === "upload" ? "输入目录" : "导出目录"}已选择: ${picked[0]}`);

      if (type === "upload" && !state.exportPath) {
        state.exportPath = picked[0];
        appendLog("INFO", `已自动设置导出目录: ${state.exportPath}`);
      }

      if (type === "export") {
        state.previewUnlocked = false;
        state.framesByTopic = {};
        state.previewTopicKey = "";
        state.previewFrameIndex = 0;
        previewTopicSelect.innerHTML = "";
        previewTopicSelect.disabled = true;
        renderPreviewFrame();
      }
      refreshView();
    } catch (error) {
      appendLog("ERROR", `目录选择失败: ${error.message}`);
    }
  };

  const handleAddCustomTopic = () => {
    const topic = customTopicInput.value.trim();
    if (!topic) {
      customTopicHint.textContent = "请输入自定义 Topic。";
      customTopicHint.className = "help-text status-muted";
      return;
    }
    if (!isTopicValid(topic)) {
      customTopicHint.textContent = "格式不正确：需以 / 开头，且不能包含空格。";
      customTopicHint.className = "help-text status-alert";
      return;
    }
    const allTopics = [...defaultTopics, ...state.customTopics];
    if (allTopics.includes(topic)) {
      customTopicHint.textContent = "该 Topic 已存在，请勿重复添加。";
      customTopicHint.className = "help-text status-alert";
      return;
    }
    state.customTopics.push(topic);
    state.selectedTopics.push(topic);
    customTopicInput.value = "";
    customTopicHint.textContent = "已添加自定义 Topic。";
    customTopicHint.className = "help-text status-muted";
    appendLog("INFO", `已添加自定义 Topic: ${topic}`);
    renderTopicOptions();
    refreshView();
  };

  const remindSelectSourceFirst = () => {
    const msg = "请先选择需要解析的文件，再选择 Topic。";
    customTopicHint.textContent = msg;
    customTopicHint.className = "help-text status-alert";
    appendLog("WARN", msg);
  };

  inputModeRadios.forEach((radio) => {
    radio.addEventListener("change", () => {
      syncSourceModeUI();
      syncTopicEnabledState();
      refreshView();
    });
  });

  selectSingleBagBtn.addEventListener("click", async () => {
    try {
      const result = await requestJson("/api/select?kind=file&multi=0");
      const picked = result.paths || [];
      if (!picked.length) {
        appendLog("WARN", "用户取消了 Bag 选择。");
        return;
      }
      state.singleBagPath = picked[0];
      state.bagFiles = [{ name: pathBaseName(picked[0]) || picked[0] }];
      appendLog("INFO", `已选择 Bag: ${picked[0]}`);

      if (!state.exportPath) {
        const parts = picked[0].split(/[\\/]/);
        parts.pop();
        state.exportPath = parts.join("/") || picked[0];
        appendLog("INFO", `已自动设置导出目录: ${state.exportPath}`);
      }

      syncTopicEnabledState();
      refreshView();
    } catch (error) {
      appendLog("ERROR", `选择 Bag 失败: ${error.message}`);
    }
  });

  folderButtons.forEach((button) => {
    button.addEventListener("click", () => pickDirectory(button.dataset.folderType));
  });

  previewBagSelect.addEventListener("change", (event) => {
    setPreviewBag(event.target.value);
  });
  previewTopicSelect.addEventListener("change", (event) => {
    setPreviewTopic(event.target.value);
  });
  previewPrevBtn.addEventListener("click", () => stepPreviewFrame(-1));
  previewNextBtn.addEventListener("click", () => stepPreviewFrame(1));
  previewPlayBtn.addEventListener("click", togglePreviewPlayback);
  previewFrameSlider.addEventListener("input", (event) => {
    state.previewFrameIndex = Number(event.target.value || 0);
    renderPreviewFrame();
  });

  topicGrid.addEventListener("change", () => {
    if (!hasSourceInput()) {
      getTopicCheckboxes().forEach((checkbox) => {
        checkbox.checked = false;
      });
      state.selectedTopics = [];
      remindSelectSourceFirst();
      refreshView();
      return;
    }
    state.selectedTopics = getTopicCheckboxes()
      .filter((checkbox) => checkbox.checked)
      .map((checkbox) => checkbox.value);
    refreshView();
  });

  addCustomTopicBtn.addEventListener("click", handleAddCustomTopic);
  customTopicInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      handleAddCustomTopic();
    }
  });

  samplingEnabledInput.addEventListener("change", updateSamplingUI);
  samplingEnabledInput.addEventListener("change", syncTimelineSampleStep);
  sampleRateInput.addEventListener("input", () => validateSampleRate(false));

  runButton.addEventListener("click", validateBeforeRun);
  stopButton.addEventListener("click", stopExecutionFlow);

  validationModalClose.addEventListener("click", closeValidationModal);
  validationModalConfirm.addEventListener("click", closeValidationModal);
  validationModal.addEventListener("click", (event) => {
    if (event.target === validationModal) {
      closeValidationModal();
    }
  });

  clearLogBtn.addEventListener("click", () => {
    logPanel.innerHTML = "";
    appendLog("INFO", "日志已清空。");
  });

  requestJson("/api/health")
    .then((res) => {
      appendLog("INFO", `后端连接成功（script_exists=${Boolean(res.script_exists)}）`);
    })
    .catch((error) => {
      appendLog("ERROR", `后端未启动，请先运行 python3 backend_server.py (${error.message})`);
    });

  renderTopicOptions();
  syncSourceModeUI();
  updateSamplingUI();
  syncTimelineSampleStep();
  renderPreviewFrame();
  refreshView();
})();
