// Web仿真环境前端逻辑

class ChessSimulation {
    constructor() {
        this.apiBase = 'http://localhost:5000/api';
        this.currentState = null;
        this.moveHistory = [];
        this.currentInputSource = 'camera'; // 当前输入源
        this.selectedCameraIndex = 1;
        this.selectedCameraIndex = 1;
        this.networkCameraUrl = '';
        this.localImageBase64 = null;
        this.boardState = {}; // 用于可视化棋盘的状态 {"col,row": "piece_char"}
        this.selectedSquare = null; // 当前选中的格子
        this.playerColor = 'red'; // 玩家执红
        this.aiColor = 'black';   // AI执黑
        this.firstPlayer = 'red'; // 默认红方先手
        this.playerColor = 'red';
        this.isGameRunning = false;
        this.isPlayerTurn = true; // 是否轮到玩家
        this.useManualBoardState = false; // 是否使用手动维护的棋盘状态
        this.dynamicRecognizeTimer = null;
        this.dynamicRecognizeTimer = null;
        this.dynamicRecognizeBusy = false;
        this.dynamicRecognitionEnabled = false;
        this.dynamicRecognizeIntervalMs = 250;
        this.cameraFrameTimer = null;
        this.cameraFrameBusy = false;
        this.cameraFrameIntervalMs = 70;
        this.lastCameraFrameErrorAt = 0;
        this.lastAiBestMoveHandled = null;
        this.lastAiBoardApplied = null;
        this.robotResumeTimer = null;
        this.robotPauseMs = 15000;
        this.lastDynamicEvent = '';
        this.logPaused = false;
        this.pausedLogCount = 0;
        this.init();
    }

    async init() {
        this.bindEvents();
        this.log('系统初始化...', 'info');
        await this.checkConnection();
        await this.loadLocalCameras();
        this.updateStatus();
    }

    // 绑定事件
    bindEvents() {
        const bind = (id, event, handler) => {
            const el = document.getElementById(id);
            if (el) el.addEventListener(event, handler);
        };

        bind('btn-capture', 'click', () => this.captureImage());
        bind('btn-recognize', 'click', () => this.toggleRecognition());
        bind('btn-start-hardware-game', 'click', () => this.startHardwareGame());
        bind('btn-start-simulation-game', 'click', () => this.startSimulationGame());
        bind('btn-reset-game', 'click', () => this.resetGame());
        bind('btn-ai-move', 'click', () => this.getAIMove());
        bind('btn-simulate-move', 'click', () => this.simulateRobotMove());
        bind('btn-test-sequence', 'click', () => this.testRobotSequence());
        bind('btn-toggle-log-pause', 'click', () => this.toggleLogPause());
        
        // 网络摄像头连接按钮
        bind('btn-connect-network', 'click', () => this.connectNetworkCamera());
        
        // 可视化棋盘点击事件
        bind('visual-board', 'click', (e) => this.handleBoardClick(e));
        
        // 本地摄像头由实时视频流按需启动，避免后台轮询反复抢占设备。
    }
    
    // 启用/禁用识别按钮
    setRecognizeButtonEnabled(enabled) {
        const btn = document.getElementById('btn-recognize');
        if (enabled) {
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.style.cursor = 'pointer';
        } else {
            btn.disabled = true;
            btn.style.opacity = '0.5';
            btn.style.cursor = 'not-allowed';
        }
    }

    setGameSettingControlsEnabled(enabled) {
        ['ai-color', 'first-player'].forEach((id) => {
            const el = document.getElementById(id);
            if (el) el.disabled = !enabled;
        });
    }

    getGameSettings() {
        const aiColor = document.getElementById('ai-color')?.value || 'black';
        const firstPlayer = document.getElementById('first-player')?.value || 'red';
        return {
            aiColor,
            playerColor: aiColor === 'red' ? 'black' : 'red',
            firstPlayer
        };
    }

    colorName(color) {
        return color === 'red' ? '红方' : '黑方';
    }

    turnCharToColor(turnChar) {
        return turnChar === 'w' ? 'red' : 'black';
    }

    currentTurnFromFen(fen) {
        const parts = (fen || '').split(' ');
        return this.turnCharToColor(parts[1] || 'w');
    }

    // 加载本地摄像头列表
    async loadLocalCameras() {
        const select = document.getElementById('input-source');

        try {
            const response = await fetch(`${this.apiBase}/cameras`);
            const data = await response.json();
            const cameras = data.success ? data.cameras : [];
            const selectedValue = select.dataset.loaded === 'true'
                ? select.value
                : `camera:${data.current_camera_index ?? this.selectedCameraIndex}`;

            select.innerHTML = '';

            if (cameras.length > 0) {
                cameras.forEach((camera) => {
                    const option = document.createElement('option');
                    option.value = `camera:${camera.index}`;
                    const size = camera.width && camera.height ? ` (${camera.width}x${camera.height})` : '';
                    option.textContent = `${camera.label}${size}`;
                    select.appendChild(option);
                });
                this.log(`检测到 ${cameras.length} 个本地摄像头`, 'info');
            } else {
                const option = document.createElement('option');
                option.value = `camera:${this.selectedCameraIndex}`;
                option.textContent = `本地摄像头 ${this.selectedCameraIndex}`;
                select.appendChild(option);
                this.log('未检测到可用摄像头，保留默认摄像头 0', 'warning');
            }

            const networkOption = document.createElement('option');
            networkOption.value = 'network';
            networkOption.textContent = '网络摄像头';
            select.appendChild(networkOption);

            const localOption = document.createElement('option');
            localOption.value = 'local';
            localOption.textContent = '本地图片';
            select.appendChild(localOption);

            if ([...select.options].some((option) => option.value === selectedValue)) {
                select.value = selectedValue;
            } else {
                const usbOption = [...select.options].find((option) => option.value === `camera:${this.selectedCameraIndex}`);
                const localOptions = [...select.options].filter((option) => option.value.startsWith('camera:'));
                if (usbOption) select.value = usbOption.value;
                else if (localOptions.length > 0) select.value = localOptions[0].value;
            }

            select.dataset.loaded = 'true';
            this.changeInputSource();
        } catch (error) {
            this.log(`加载摄像头列表失败: ${error.message}`, 'error');
        }
    }

    // 切换输入源
    changeInputSource() {
        const source = document.getElementById('input-source').value;
        const img = document.getElementById('camera-feed');
        if (source.startsWith('camera:')) {
            this.currentInputSource = 'camera';
            this.selectedCameraIndex = parseInt(source.split(':')[1], 10);
            if (Number.isNaN(this.selectedCameraIndex)) this.selectedCameraIndex = 1;
        } else {
            this.currentInputSource = source;
        }
        
        // 隐藏所有输入组
        document.getElementById('network-camera-input').style.display = 'none';
        document.getElementById('local-image-input').style.display = 'none';
        
        // 显示对应的输入组
        if (source === 'network') {
            document.getElementById('network-camera-input').style.display = 'flex';
            if (this.networkCameraUrl) {
                this.startLocalCameraStream();
            } else {
                this.stopLocalCameraFrames();
                img.src = '';
            }
            this.stopDynamicRecognition();
            this.setRecognitionMode(false);
            this.log('切换到网络摄像头模式', 'info');
        } else if (source === 'local') {
            document.getElementById('local-image-input').style.display = 'flex';
            this.stopLocalCameraFrames();
            img.src = this.localImageBase64 || '';
            this.stopDynamicRecognition();
            this.setRecognitionMode(false);
            this.log('切换到本地图片模式', 'info');
        } else {
            this.log(`切换到本地摄像头 ${this.selectedCameraIndex}`, 'info');
            this.startLocalCameraStream();
            this.stopDynamicRecognition();
            this.setRecognitionMode(false);
            this.log('实时画面已打开。摆好棋后点击“开始识别”。', 'info');
        }
    }

    // 显示本地或网络摄像头实时画面
    startLocalCameraStream() {
        this.stopLocalCameraFrames();
        const img = document.getElementById('camera-feed');
        const canvas = document.getElementById('camera-view');
        if (canvas) canvas.style.display = 'block';
        if (img) {
            img.style.display = 'none';
            img.onload = null;
            img.onerror = () => {
                this.log(`${this.currentInputSource === 'network' ? '网络摄像头' : `本地摄像头 ${this.selectedCameraIndex}`} 视频流连接中断，正在等待后端自动恢复`, 'warning');
            };
            img.onerror = null;
            img.src = '';
        }
        this.cameraFrameTimer = setInterval(() => this.refreshCameraFrame(), this.cameraFrameIntervalMs);
        this.refreshCameraFrame();
    }

    stopLocalCameraFrames() {
        if (this.cameraFrameTimer) {
            clearInterval(this.cameraFrameTimer);
            this.cameraFrameTimer = null;
        }
        this.cameraFrameBusy = false;
        const img = document.getElementById('camera-feed');
        if (img && (this.currentInputSource === 'camera' || this.currentInputSource === 'network')) {
            img.src = '';
        }
    }

    cameraRequestPayload() {
        if (this.currentInputSource === 'network') {
            return { camera_source: 'network' };
        }
        return { camera_index: this.selectedCameraIndex };
    }

    cameraFrameQuery() {
        if (this.currentInputSource === 'network') {
            return `camera_source=network`;
        }
        return `camera_index=${this.selectedCameraIndex}`;
    }

    refreshCameraFrame() {
        if (!['camera', 'network'].includes(this.currentInputSource) || this.cameraFrameBusy) {
            return;
        }

        this.cameraFrameBusy = true;
        const img = new Image();
        const canvas = document.getElementById('camera-view');
        const frameUrl = `${this.apiBase}/camera/frame?${this.cameraFrameQuery()}&t=${Date.now()}`;

        img.onload = () => {
            if (canvas) {
                const ctx = canvas.getContext('2d');
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                const scale = Math.min(canvas.width / img.naturalWidth, canvas.height / img.naturalHeight);
                const drawWidth = img.naturalWidth * scale;
                const drawHeight = img.naturalHeight * scale;
                const x = (canvas.width - drawWidth) / 2;
                const y = (canvas.height - drawHeight) / 2;
                ctx.drawImage(img, x, y, drawWidth, drawHeight);
            }
            this.cameraFrameBusy = false;
        };
        img.onerror = () => {
            this.cameraFrameBusy = false;
            this.log(`${this.currentInputSource === 'network' ? '网络摄像头' : `本地摄像头 ${this.selectedCameraIndex}`} 实时画面加载失败`, 'error');
        };
        img.src = frameUrl;
    }

    pauseForRobotMove(durationMs = this.robotPauseMs, options = {}) {
        const autoResume = options.autoResume !== false;
        this.stopDynamicRecognition();
        this.stopLocalCameraFrames();
        this.setRecognitionMode(false);

        if (this.robotResumeTimer) {
            clearTimeout(this.robotResumeTimer);
            this.robotResumeTimer = null;
        }

        if (!autoResume) {
            this.log('AI已给出走法，暂停摄像头采集与动态识别，等待下位机回传 STATE:5,RESULT:1...', 'warning');
            return;
        }

        this.log(`AI已给出走法，暂停摄像头采集与动态识别 ${Math.round(durationMs / 1000)} 秒，等待机械臂执行完成...`, 'warning');
        this.robotResumeTimer = setTimeout(() => {
            this.robotResumeTimer = null;
            this.resumeRecognitionAfterRobotAck(false);
        }, durationMs);
    }

    resumeRecognitionAfterRobotAck(fromController = true) {
        if (this.robotResumeTimer) {
            clearTimeout(this.robotResumeTimer);
            this.robotResumeTimer = null;
        }

        if (['camera', 'network'].includes(this.currentInputSource)) {
            this.startLocalCameraStream();
        }
        if (this.isGameRunning && ['camera', 'network'].includes(this.currentInputSource)) {
            this.setRecognitionMode(true);
            this.startDynamicRecognition();
            this.log(
                fromController
                    ? '已收到下位机 STATE:5,RESULT:1，恢复红方走子识别'
                    : '机械臂执行暂停结束，恢复红方走子识别',
                'info'
            );
        }
    }

    setRecognitionMode(enabled) {
        this.dynamicRecognitionEnabled = enabled;
        const btn = document.getElementById('btn-recognize');
        if (btn) {
            btn.textContent = enabled ? '停止识别' : '开始识别';
            btn.classList.toggle('btn-warning', enabled);
            btn.classList.toggle('btn-success', !enabled);
        }
        const canvas = document.getElementById('board-canvas');
        if (canvas && !enabled) {
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        }
    }

    toggleRecognition() {
        if (!['camera', 'network'].includes(this.currentInputSource)) {
            this.recognizeBoard();
            return;
        }

        if (this.dynamicRecognitionEnabled) {
            this.stopDynamicRecognition();
            this.setRecognitionMode(false);
            this.log('识别已停止，保留实时摄像头画面', 'info');
        } else {
            this.setRecognitionMode(true);
            this.startDynamicRecognition();
        }
    }

    // 自动动态识别当前摄像头画面
    startDynamicRecognition() {
        this.stopDynamicRecognition();
        this.lastDynamicEvent = '';
        this.dynamicRecognizeTimer = setInterval(() => this.pollDynamicRecognition(), this.dynamicRecognizeIntervalMs);
        this.pollDynamicRecognition();
        this.log('动态识别已启动，等待棋盘稳定...', 'info');
    }

    stopDynamicRecognition() {
        if (this.dynamicRecognizeTimer) {
            clearInterval(this.dynamicRecognizeTimer);
            this.dynamicRecognizeTimer = null;
        }
        this.dynamicRecognizeBusy = false;
    }

    async pollDynamicRecognition() {
        if (!this.dynamicRecognitionEnabled || !['camera', 'network'].includes(this.currentInputSource) || this.dynamicRecognizeBusy) {
            return;
        }

        this.dynamicRecognizeBusy = true;
        try {
            const response = await fetch(`${this.apiBase}/recognize/dynamic`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(this.cameraRequestPayload())
            });

            const data = await response.json();
            if (!data.success) {
                if (this.lastDynamicEvent !== 'error') {
                    this.log(`动态识别失败: ${data.error}`, 'error');
                    this.lastDynamicEvent = 'error';
                }
                return;
            }

            const recognizedPieceCount = data.recognized_piece_count ?? data.piece_count ?? 0;
            const eventKey = `${data.event}:${data.message}:${recognizedPieceCount}`;
            if (data.event !== 'unchanged' && eventKey !== this.lastDynamicEvent) {
                this.log(`动态识别: ${data.message || data.event}（${recognizedPieceCount}子）`, data.stable ? 'info' : 'warning');
                this.lastDynamicEvent = eventKey;
            }

            if (data.event === 'paused') {
                return;
            }

            if (data.stable && data.board_state && Object.keys(data.board_state).length > 0) {
                this.isGameRunning = Boolean(data.is_game_running);
                if (data.ai_color) this.aiColor = data.ai_color;
                if (data.player_color) this.playerColor = data.player_color;
                if (data.first_player) this.firstPlayer = data.first_player;

                this.boardState = data.board_state;
                if (data.current_fen || data.fen) {
                    document.getElementById('fen-display').value = data.current_fen || data.fen;
                }
                document.getElementById('piece-count').textContent = data.piece_count || 0;
                this.drawVisualBoard();
                this.drawBoard(data.board_state);

                if (data.event === 'move' && data.move) {
                    this.log(`自动检测到走子: ${data.move.code}`, 'info');
                    
                    // 强制同步后端状态到前端
                    if (data.display_history) this.moveHistory = data.display_history;
                    else if (data.move_history) this.moveHistory = data.move_history;
                    this.updateMoveList();
                    if (data.current_fen) document.getElementById('fen-display').value = data.current_fen;
                    
                    if (data.move.source === 'ai_confirmed') {
                        this.log('已确认机械臂完成AI落子，等待红方下一步', 'info');
                    } else if (data.move.source === 'player') {
                        // 红方走完后才触发AI；AI/机械臂确认不会再次触发AI。
                        this.lastAiBestMoveHandled = null;
                        this.lastAiBoardApplied = null;
                        this.checkAutoTriggerAI(data.current_fen);
                    }
                } else if (this.isGameRunning && data.event === 'unchanged' && data.stable) {
                    // 即使没有 move 事件，如果 FEN 显示该轮到 AI 了，也要尝试触发
                    this.checkAutoTriggerAI(data.current_fen || data.fen);
                }
            }
        } catch (error) {
            if (this.lastDynamicEvent !== 'network-error') {
                this.log(`动态识别请求错误: ${error.message}`, 'error');
                this.lastDynamicEvent = 'network-error';
            }
        } finally {
            this.dynamicRecognizeBusy = false;
        }
    }

    // 连接网络摄像头
    async connectNetworkCamera() {
        const url = document.getElementById('network-camera-url').value.trim();
        
        if (!url) {
            this.log('请输入网络摄像头URL', 'warning');
            return;
        }
        
        this.log(`正在连接网络摄像头: ${url}`, 'info');

        try {
            const response = await fetch(`${this.apiBase}/network_camera/connect`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            });
            const data = await response.json();

            if (data.success) {
                this.networkCameraUrl = url;
                this.currentInputSource = 'network';
                const select = document.getElementById('input-source');
                if (select) select.value = 'network';
                this.log(`网络摄像头连接成功: ${data.source_label}`, 'info');
                if (data.width && data.height) {
                    this.log(`网络摄像头画面: ${data.width}x${data.height}`, 'info');
                }
                this.startLocalCameraStream();
            } else {
                this.log(`网络摄像头连接失败: ${data.error}`, 'error');
            }
        } catch (error) {
            this.log(`网络摄像头连接错误: ${error.message}`, 'error');
        }
    }

    // 处理本地图片上传
    handleLocalImageUpload(event) {
        const file = event.target.files[0];
        
        if (!file) {
            return;
        }
        
        // 检查文件类型
        if (!file.type.startsWith('image/')) {
            this.log('请选择图片文件', 'error');
            return;
        }
        
        const reader = new FileReader();
        
        reader.onload = (e) => {
            this.localImageBase64 = e.target.result;
            
            // 显示图片
            const img = document.getElementById('camera-feed');
            img.src = this.localImageBase64;
            
            this.log(`已加载本地图片: ${file.name}`, 'info');
        };
        
        reader.readAsDataURL(file);
    }

    // 检查连接
    async checkConnection() {
        try {
            const response = await fetch(`${this.apiBase}/status`);
            if (response.ok) {
                this.updateConnectionStatus(true);
                this.log('连接到服务器成功', 'info');
            } else {
                this.updateConnectionStatus(false);
            }
        } catch (error) {
            this.updateConnectionStatus(false);
            this.log(`连接失败: ${error.message}`, 'error');
        }
    }

    async checkRobotConnection() {
        try {
            const response = await fetch(`${this.apiBase}/robot/status`);
            const data = await response.json();
            const target = `${data.host || '192.168.0.102'}:${data.port || 8086}`;

            if (data.status === 'not_probed') {
                this.log(`STM32目标已配置：${target}，正式使用将通过 Homing 回传确认连接`, 'info');
                return true;
            }

            if (response.ok && data.connected) {
                this.log(`STM32连接确认成功：${target}`, 'info');
                return true;
            }

            this.log(`STM32未连接：${target}${data.error ? `（${data.error}）` : ''}`, 'error');
            return false;
        } catch (error) {
            this.log(`STM32连接检查失败：${error.message}`, 'error');
            return false;
        }
    }

    // 检查摄像头状态
    async checkCameraStatus() {
        if (!['camera', 'network'].includes(this.currentInputSource)) {
            return;
        }

        try {
            const response = await fetch(`${this.apiBase}/camera/status?${this.cameraFrameQuery()}`);
            const data = await response.json();
            
            if (data.success) {
                if (!data.camera_opened) {
                    this.log('摄像头未打开，尝试自动启动...', 'warning');
                    await this.startCamera();
                }
            }
        } catch (error) {
            // 静默失败，不干扰用户
        }
    }

    // 启动摄像头
    async startCamera() {
        try {
            const response = await fetch(`${this.apiBase}/camera/start`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(this.cameraRequestPayload())
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.log('摄像头启动成功', 'info');
            } else {
                this.log(`摄像头启动失败: ${data.error}`, 'error');
            }
        } catch (error) {
            this.log(`启动摄像头错误: ${error.message}`, 'error');
        }
    }

    // 更新连接状态
    updateConnectionStatus(connected) {
        const statusEl = document.getElementById('connection-status');
        if (connected) {
            statusEl.textContent = '● 已连接';
            statusEl.className = 'status-indicator connected';
        } else {
            statusEl.textContent = '● 未连接';
            statusEl.className = 'status-indicator disconnected';
        }
    }

    // 捕获图像
    async captureImage() {
        this.log('正在捕获图像...', 'info');
        
        // 如果是本地图片，直接使用已加载的图片
        if (this.currentInputSource === 'local') {
            if (this.localImageBase64) {
                this.log('使用已加载的本地图片', 'info');
                return;
            } else {
                this.log('请先上传本地图片', 'warning');
                return;
            }
        }
        
        // 本地/网络摄像头模式
        try {
            const response = await fetch(`${this.apiBase}/capture`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(this.cameraRequestPayload())
            });

            const data = await response.json();
            
            if (data.success) {
                const img = document.getElementById('camera-feed');
                img.src = `data:image/jpeg;base64,${data.image}`;
                this.log('图像捕获成功', 'info');
            } else {
                this.log(`捕获失败: ${data.error}`, 'error');
                // 如果是摄像头问题，尝试重启
                if (data.error.includes('摄像头') || data.error.includes('无法捕获')) {
                    this.log('尝试重新启动摄像头...', 'warning');
                    await this.startCamera();
                }
            }
        } catch (error) {
            this.log(`捕获图像错误: ${error.message}`, 'error');
        }
    }

    // 识别棋盘
    async recognizeBoard() {
        // 如果游戏正在进行中，禁止识别
        if (this.moveHistory.length > 0) {
            this.log('⛔ 游戏进行中，禁止手动识别棋盘！', 'error');
            this.log('系统已通过UCI走法自动维护棋盘状态', 'info');
            alert('游戏已开始，不能手动识别棋盘！\n\n棋盘状态由系统通过UCI走法自动维护，手动识别会破坏游戏状态。');
            return;
        }
        
        this.log('正在识别棋盘...', 'info');
        
        let imageData = null;
        
        // 如果是本地图片，发送base64数据
        if (this.currentInputSource === 'local') {
            if (!this.localImageBase64) {
                this.log('请先上传本地图片', 'warning');
                return;
            }
            // 移除 data:image/jpeg;base64, 前缀
            imageData = this.localImageBase64.split(',')[1];
            this.log('使用本地图片进行识别', 'info');
        }
        
        try {
            const response = await fetch(`${this.apiBase}/recognize`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    image: imageData,
                    ...this.cameraRequestPayload()
                })
            });

            const data = await response.json();
            
            if (data.success) {
                document.getElementById('fen-display').value = data.fen || '';
                document.getElementById('piece-count').textContent = data.piece_count || 0;
                this.log(`识别成功: 检测到 ${data.piece_count} 个棋子`, 'info');
                
                // 更新可视化棋盘
                this.boardState = data.board_state;
                this.drawVisualBoard();
                this.updateGameStatus();
                
                // 绘制原始棋盘检测结果
                this.drawBoard(data.board_state);
            } else {
                this.log(`识别失败: ${data.error}`, 'error');
            }
        } catch (error) {
            this.log(`识别错误: ${error.message}`, 'error');
        }
    }

    // 开始游戏
    async startHardwareGame() {
        return this.startGame('hardware');
    }

    async startSimulationGame() {
        const simulationPayload = { mode: 'simulation' };
        void simulationPayload;
        return this.startGame('simulation');
    }

    async startGame(mode = 'hardware') {
        this.aiColor = 'black';
        this.playerColor = 'red';
        this.firstPlayer = 'red';
        document.getElementById('ai-color').value = this.aiColor;
        document.getElementById('first-player').value = this.firstPlayer;

        const isHardwareMode = mode === 'hardware';
        const startButton = document.getElementById(
            isHardwareMode ? 'btn-start-hardware-game' : 'btn-start-simulation-game'
        );
        startButton.disabled = true;
        startButton.textContent = isHardwareMode ? '机械臂归零中...' : '启动模拟中...';

        if (isHardwareMode) {
            this.log('正在发送 Homing 指令：-17.1848,-55.6304,0,0,99', 'info');
            this.log('等待 STM32 完成机械臂归零并回传 STATE:5...', 'info');
        } else {
            this.log('模拟测试模式：不连接 STM32，不发送 Homing 或走子指令', 'info');
        }
        try {
            const response = await fetch(`${this.apiBase}/game/start`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    use_recognized_board: false,
                    board_state: {},
                    ai_color: 'black',
                    first_player: 'red',
                    mode
                })
            });

            const data = await response.json();
            
            if (data.success) {
                if (isHardwareMode) {
                    this.log(`Homing 完成：${data.homing_response || 'STATE:5,RESULT:1'}`, 'info');
                }
                this.log(`开始新游戏：${isHardwareMode ? '正式使用' : '模拟测试'}，程序固定执黑方，红方先手`, 'info');
                this.isGameRunning = true;
                this.robotMode = data.robot_mode || mode;
                this.aiColor = data.ai_color || this.aiColor;
                this.playerColor = data.player_color || this.playerColor;
                this.firstPlayer = data.first_player || this.firstPlayer;
                this.moveHistory = [];
                this.lastAiBestMoveHandled = null;
                this.lastAiBoardApplied = null;
                this.isPlayerTurn = (data.current_turn || this.firstPlayer) === this.playerColor;
                this.updateMoveList();
                if (data.current_fen || data.fen) {
                    document.getElementById('fen-display').value = data.current_fen || data.fen;
                }
                this.updateGameStatus();
                
                // 游戏中仍允许停止/继续摄像头走子识别；只锁定对局设置。
                this.setRecognizeButtonEnabled(true);
                this.setGameSettingControlsEnabled(false);
                this.log('对局设置已锁定，开始监听红方走子', 'info');
                
                // 每局固定从标准初始棋盘开始，摄像头只负责识别之后的走子变化。
                if (data.board_state) {
                    this.boardState = data.board_state;
                    this.log('✅ 标准初始布局已加载，棋子数量: ' + Object.keys(this.boardState).length, 'info');
                } else {
                    this.initStandardBoard();
                }
                document.getElementById('piece-count').textContent = Object.keys(this.boardState).length;
                this.drawVisualBoard();
                
                this.log('✅ 棋盘状态:', 'info');
                this.log(JSON.stringify(this.boardState), 'info');
                if (['camera', 'network'].includes(this.currentInputSource) && !this.dynamicRecognitionEnabled) {
                    this.setRecognitionMode(true);
                    this.startDynamicRecognition();
                }
                this.checkAutoTriggerAI(data.current_fen || data.fen);
            } else {
                this.isGameRunning = false;
                this.log(`开始失败: ${data.error}`, 'error');
                if (data.homing_response) {
                    this.log(`STM32回传: ${data.homing_response}`, 'error');
                }
            }
        } catch (error) {
            this.isGameRunning = false;
            this.log(`开始游戏错误: ${error.message}`, 'error');
        } finally {
            startButton.disabled = false;
            startButton.textContent = isHardwareMode ? '正式使用（连接下位机）' : '模拟测试（无下位机）';
        }
    }

    // 重置游戏
    async resetGame() {
        this.log('重置游戏...', 'info');
        try {
            const response = await fetch(`${this.apiBase}/game/reset`, {
                method: 'POST'
            });

            const data = await response.json();
            
            if (data.success) {
                this.log('游戏已重置', 'info');
                if (this.robotResumeTimer) {
                    clearTimeout(this.robotResumeTimer);
                    this.robotResumeTimer = null;
                }
                this.stopDynamicRecognition();
                this.setRecognitionMode(false);
                document.getElementById('game-status').textContent = '等待开始';
                document.getElementById('fen-display').value = '';
                document.getElementById('piece-count').textContent = '0';
                this.moveHistory = [];
                this.lastAiBestMoveHandled = null;
                this.lastAiBoardApplied = null;
                this.isGameRunning = false;
                this.aiColor = 'black';
                this.playerColor = 'red';
                this.firstPlayer = 'red';
                document.getElementById('ai-color').value = this.aiColor;
                document.getElementById('first-player').value = this.firstPlayer;
                this.updateMoveList();
                
                // 重新启用识别按钮
                this.setRecognizeButtonEnabled(true);
                this.setGameSettingControlsEnabled(true);
                this.log('✅ 已启用识别按钮', 'info');
            } else {
                this.log(`重置失败: ${data.error}`, 'error');
            }
        } catch (error) {
            this.log(`重置游戏错误: ${error.message}`, 'error');
        }
    }

    // 获取AI走法
    async getAIMove() {
        const aiColor = 'black';
        this.aiColor = aiColor;
        this.playerColor = 'red';
        const depth = parseInt(document.getElementById('ai-depth').value) || 8;
        this.log(`启动 AI 思考 (执色: ${aiColor === 'red' ? '红' : '黑'}, 深度: ${depth})...`, 'info');
        
        try {
            const response = await fetch(`${this.apiBase}/ai_move`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ depth, ai_color: aiColor })
            });

            const data = await response.json();
            
            if (data.success) {
                this.startAIStatusPolling();
            } else {
                this.log(`启动 AI 失败: ${data.error}`, 'error');
            }
        } catch (error) {
            this.log(`获取 AI 走法错误: ${error.message}`, 'error');
        }
    }

    syncAIMoveBoardFromStatus(data, bestMove) {
        this.moveHistory = data.display_history || data.move_history || this.moveHistory;
        this.updateMoveList();

        if (data.current_fen) {
            document.getElementById('fen-display').value = data.current_fen;
        }

        if (data.board_state) {
            this.boardState = data.board_state;
            document.getElementById('piece-count').textContent = data.piece_count || Object.keys(this.boardState).length;
            this.drawVisualBoard();
            this.drawBoard(this.boardState);
        } else {
            this.updateBoardFromUCIMove(bestMove, true);
        }
    }

    aiMoveToken(data, bestMove) {
        return data.analysis?.ai_move_token || `${(data.move_history || []).length}:${bestMove}`;
    }

    predisplayAIMoveFromStatus(data, bestMove) {
        const moveToken = this.aiMoveToken(data, bestMove);
        if (!data.analysis?.ai_move_applied || this.lastAiBoardApplied === moveToken) {
            return false;
        }

        this.lastAiBoardApplied = moveToken;
        this.syncAIMoveBoardFromStatus(data, bestMove);
        this.isPlayerTurn = true;
        this.updateGameStatus();

        const serverPauseMs = Math.ceil((data.vision_pause_remaining || 0) * 1000);
        const isHardwareMode = (data.robot_mode || this.robotMode) === 'hardware';
        this.pauseForRobotMove(
            Math.max(this.robotPauseMs, serverPauseMs),
            { autoResume: !isHardwareMode }
        );
        this.log(`AI走法已预显示: ${bestMove}，等待${isHardwareMode ? '下位机 STATE:5,RESULT:1' : '模拟机械臂'}执行结果`, 'warning');
        return true;
    }

    // 轮询 AI 思考状态
    startAIStatusPolling() {
        if (this.aiPollingTimer) return;
        
        const statusEl = document.getElementById('game-status');
        statusEl.textContent = 'AI 正在思考...';
        
        this.aiPollingTimer = setInterval(async () => {
            try {
                const response = await fetch(`${this.apiBase}/ai_status`);
                const data = await response.json();
                
                if (!data.success) return;
                
                // 更新分析面板
                if (data.analysis) {
                    this.showAnalysis(data.analysis);
                }

                const bestMove = data.analysis?.best_move;
                if (bestMove) {
                    this.predisplayAIMoveFromStatus(data, bestMove);
                }
                
                // 检查是否思考完成
                if (!data.ai_thinking) {
                    clearInterval(this.aiPollingTimer);
                    this.aiPollingTimer = null;
                    
                    if (bestMove) {
                        const isHardwareMode = (data.robot_mode || this.robotMode) === 'hardware';
                        const moveToken = this.aiMoveToken(data, bestMove);
                        const boardAlreadyApplied = this.lastAiBoardApplied === moveToken;
                        if (this.lastAiBestMoveHandled === moveToken) {
                            return;
                        }
                        this.lastAiBestMoveHandled = moveToken;
                        this.log(`AI 思考完成，选择走法: ${bestMove}`, 'info');
                        const robotMessages = data.analysis.robot_log_messages || [];
                        robotMessages.forEach((message) => {
                            const type = message.includes('失败') ? 'error' : (message.includes('未收到') ? 'warning' : 'info');
                            this.log(message, type);
                        });

                        if (!boardAlreadyApplied) {
                            this.lastAiBoardApplied = moveToken;
                            this.syncAIMoveBoardFromStatus(data, bestMove);
                            this.pauseForRobotMove(this.robotPauseMs, { autoResume: !isHardwareMode });
                        }

                        if (data.analysis.robot_send_success === false) {
                            this.log(`机器人执行失败：${data.analysis.robot_send_error || '未收到下位机完成回传'}`, 'error');
                            this.isPlayerTurn = false;
                            this.updateGameStatus();
                            return;
                        }
                        
                        // 切换回玩家回合
                        this.isPlayerTurn = true;
                        this.updateGameStatus();
                        if (isHardwareMode && data.analysis.robot_send_success === true && data.analysis.robot_send_acknowledged !== false) {
                            this.resumeRecognitionAfterRobotAck(true);
                        }
                    } else {
                        this.log('AI 未能给出有效走法', 'error');
                        this.isPlayerTurn = false;
                        this.updateGameStatus();
                    }
                }
            } catch (error) {
                this.log(`获取 AI 状态失败: ${error.message}`, 'error');
                clearInterval(this.aiPollingTimer);
                this.aiPollingTimer = null;
            }
        }, 250);
    }

    // 执行机械臂移动
    async executeRobotMove(move) {
        this.log(`机械臂执行AI走法: ${move}`, 'info');
        const robotState = document.getElementById('robot-state');
        if (robotState) robotState.textContent = '移动中...';
        
        try {
            const response = await fetch(`${this.apiBase}/simulate_robot`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ move })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.log('机械臂移动完成', 'info');
                if (robotState) robotState.textContent = '空闲';
                
                // 解析UCI走法并更新可视化棋盘
                this.updateBoardFromUCIMove(move, true);  // AI走法
                
                this.animateRobotMove(move);
            } else {
                this.log(`移动失败: ${data.error}`, 'error');
                if (robotState) robotState.textContent = '错误';
            }
        } catch (error) {
            this.log(`机械臂移动错误: ${error.message}`, 'error');
            if (robotState) robotState.textContent = '错误';
        }
    }

    // 根据UCI走法更新棋盘状态
    updateBoardFromUCIMove(uciMove, isAIMove = false) {
        if (uciMove.length < 4) return;
            
        const files = 'abcdefghi';
        // 尝试两种UCI坐标系统：
        // 方案1: UCI排名0=红方底线, 9=黑方底线 → array_row = 9 - uci_rank
        // 方案2: UCI排名0=黑方底线, 9=红方底线 → array_row = uci_rank
        
        const fromFile = uciMove.charAt(0);
        const fromRank = uciMove.charAt(1);
        const toFile = uciMove.charAt(2);
        const toRank = uciMove.charAt(3);
            
        const fromCol = files.indexOf(fromFile);
        const toCol = files.indexOf(toFile);
        
        // 先尝试方案1（反转）
        let fromRow = 9 - parseInt(fromRank);
        let toRow = 9 - parseInt(toRank);
        
        let fromKey = `${fromCol},${fromRow}`;
        let toKey = `${toCol},${toRow}`;
        
        this.log(`🔍 调试: UCI=${uciMove}, 方案1(反转): (${fromCol},${fromRow}) -> (${toCol},${toRow})`, 'info');
        this.log(`🔍 方案1起始位置棋子: ${this.boardState[fromKey] || '空'}`, 'info');
        
        // 检查起始位置是否有棋子
        if (!this.boardState[fromKey]) {
            // 方案1失败，尝试方案2（不反转）
            fromRow = parseInt(fromRank);
            toRow = parseInt(toRank);
            fromKey = `${fromCol},${fromRow}`;
            toKey = `${toCol},${toRow}`;
            
            this.log(`⚠️ 方案1失败，尝试方案2(不反转): ${uciMove} -> (${fromCol},${fromRow}) -> (${toCol},${toRow})`, 'warning');
            this.log(`🔍 方案2起始位置棋子: ${this.boardState[fromKey] || '空'}`, 'info');
            
            // 如果方案2也失败，输出所有棋子位置供调试
            if (!this.boardState[fromKey]) {
                this.log(`❌ 两种方案都失败！列出所有棋子位置:`, 'error');
                Object.entries(this.boardState).forEach(([key, piece]) => {
                    const [c, r] = key.split(',');
                    this.log(`   (${c},${r}): ${piece}`, 'info');
                });
            }
        } else {
            this.log(`✅ 使用方案1（反转）`, 'info');
        }
            
        if (fromCol === -1 || fromRow < 0 || fromRow > 9 || toCol === -1 || toRow < 0 || toRow > 9) {
            this.log(`❌ 无效的UCI走法: ${uciMove}`, 'error');
            return;
        }
            
        this.log(`UCI解析: ${uciMove} -> (${fromCol},${fromRow}) -> (${toCol},${toRow})`, 'info');
        
        // 检查目标位置是否有棋子（吃子）
        const capturedPiece = this.boardState[toKey];
        if (capturedPiece) {
            this.log(`⚔️ 吃子！${capturedPiece} 在 (${toCol},${toRow}) 被吃掉`, 'warning');
            
            // 检查是否是将/帅被吃
            if (capturedPiece === 'K' || capturedPiece === 'k') {
                this.log(`🏆 游戏结束！${capturedPiece === 'K' ? '红方' : '黑方'}被将死！`, 'error');
                alert(`游戏结束！${capturedPiece === 'K' ? '红方（你）' : '黑方（AI）'}被将死！`);
                return;
            }
        }
            
        // 获取移动的棋子
        const piece = this.boardState[fromKey];
        if (!piece) {
            this.log(`❌ 起始位置没有棋子: ${fromKey}`, 'error');
            this.log(`当前棋盘状态:`, 'info');
            this.log(JSON.stringify(this.boardState), 'info');
            this.log(`期望的棋子应该在 (${fromCol},${fromRow})，但实际不存在`, 'error');
            return;
        }
        
        // 执行移动
        delete this.boardState[fromKey];
        this.boardState[toKey] = piece;
            
        this.log(`✅ 棋盘更新: ${piece} ${fromKey} -> ${toKey}`, 'info');
        this.drawVisualBoard();
    }

    // 模拟机械臂移动
    async simulateRobotMove() {
        if (this.moveHistory.length === 0) {
            this.log('没有可执行的走法', 'warning');
            return;
        }

        const lastMove = this.moveHistory[this.moveHistory.length - 1];
        await this.executeRobotMove(lastMove);
    }

    // 测试机械臂序列
    async testRobotSequence() {
        this.log('执行机械臂测试序列...', 'info');
        const robotState = document.getElementById('robot-state');
        if (robotState) robotState.textContent = '测试中...';
        
        // 简单模拟
        setTimeout(() => {
            this.log('测试序列完成', 'info');
            if (robotState) robotState.textContent = '空闲';
            this.drawRobotVisualization();
        }, 2000);
    }

    // 更新走法列表
    updateMoveList() {
        const moveList = document.getElementById('move-list');
        moveList.innerHTML = '';
        
        this.moveHistory.forEach((move, index) => {
            const moveItem = document.createElement('div');
            moveItem.className = 'move-item';
            moveItem.textContent = `${Math.floor(index / 2) + 1}. ${move}`;
            moveList.appendChild(moveItem);
        });
        
        moveList.scrollTop = moveList.scrollHeight;
    }

    // 显示AI分析
    showAnalysis(analysis) {
        const analysisDiv = document.getElementById('ai-analysis');
        let html = '<h4>AI分析结果</h4>';
        
        if (analysis.best_move) {
            html += `<p><strong>最佳走法:</strong> ${analysis.best_move}</p>`;
        }
        if (analysis.score !== null && analysis.score !== undefined) {
            html += `<p><strong>评估分数:</strong> ${analysis.score}</p>`;
        }
        if (analysis.depth) {
            html += `<p><strong>搜索深度:</strong> ${analysis.depth}</p>`;
        }
        if (analysis.pv) {
            html += `<p><strong>PV线:</strong> ${analysis.pv.substring(0, 50)}...</p>`;
        }
        
        analysisDiv.innerHTML = html;
    }

    // 绘制棋盘
    drawBoard(boardState) {
        const canvas = document.getElementById('board-canvas');
        const ctx = canvas.getContext('2d');
        
        // 清空画布
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        if (!boardState) return;
        
        // 绘制棋子
        const cellWidth = canvas.width / 9;
        const cellHeight = canvas.height / 10;
        
        Object.entries(boardState).forEach(([posKey, side]) => {
            // posKey 格式: "col,row"
            const [col, row] = posKey.split(',').map(Number);
            const x = col * cellWidth + cellWidth / 2;
            const y = row * cellHeight + cellHeight / 2;
            
            // 绘制棋子圆圈
            ctx.beginPath();
            ctx.arc(x, y, 18, 0, Math.PI * 2);
            ctx.fillStyle = side === 'red' ? '#fee2e2' : '#d1d5db';
            ctx.fill();
            ctx.strokeStyle = side === 'red' ? '#ef4444' : '#000000';
            ctx.lineWidth = 2;
            ctx.stroke();
            
            // 绘制标签
            ctx.fillStyle = side === 'red' ? '#dc2626' : '#ffffff';
            ctx.font = 'bold 14px Arial';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(side === 'red' ? 'R' : 'B', x, y);
        });
    }

    // 绘制机械臂可视化
    drawRobotVisualization() {
        const canvas = document.getElementById('robot-canvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        // 绘制简化的机械臂
        ctx.strokeStyle = '#667eea';
        ctx.lineWidth = 3;
        
        // 基座
        ctx.beginPath();
        ctx.arc(200, 350, 30, 0, Math.PI * 2);
        ctx.stroke();
        
        // 臂段1
        ctx.beginPath();
        ctx.moveTo(200, 350);
        ctx.lineTo(200, 250);
        ctx.stroke();
        
        // 臂段2
        ctx.beginPath();
        ctx.moveTo(200, 250);
        ctx.lineTo(250, 200);
        ctx.stroke();
        
        // 夹爪
        ctx.beginPath();
        ctx.moveTo(250, 200);
        ctx.lineTo(260, 190);
        ctx.moveTo(250, 200);
        ctx.lineTo(260, 210);
        ctx.stroke();
    }

    // 绘制可视化棋盘
    drawVisualBoard() {
        const canvas = document.getElementById('visual-board');
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        const width = canvas.width;
        const height = canvas.height;
        
        // 清空画布
        ctx.clearRect(0, 0, width, height);
        
        // 绘制棋盘背景
        ctx.fillStyle = '#e5c9a8';
        ctx.fillRect(0, 0, width, height);
        
        // 计算格子大小
        const cellWidth = (width - 40) / 8; // 留出边距
        const cellHeight = (height - 40) / 9;
        const offsetX = 20;
        const offsetY = 20;
        
        // 绘制网格线
        ctx.strokeStyle = '#8b5a2b';
        ctx.lineWidth = 1;
        
        // 横线
        for (let i = 0; i <= 9; i++) {
            const y = offsetY + i * cellHeight;
            ctx.beginPath();
            ctx.moveTo(offsetX, y);
            ctx.lineTo(width - offsetX, y);
            ctx.stroke();
        }
        
        // 竖线
        for (let i = 0; i <= 8; i++) {
            const x = offsetX + i * cellWidth;
            ctx.beginPath();
            ctx.moveTo(x, offsetY);
            ctx.lineTo(x, offsetY + 4 * cellHeight); // 上半部分
            ctx.stroke();
            
            ctx.beginPath();
            ctx.moveTo(x, offsetY + 5 * cellHeight);
            ctx.lineTo(x, offsetY + 9 * cellHeight); // 下半部分
            ctx.stroke();
        }
        
        // 九宫格斜线
        ctx.beginPath();
        ctx.moveTo(offsetX + 3 * cellWidth, offsetY);
        ctx.lineTo(offsetX + 5 * cellWidth, offsetY + 2 * cellHeight);
        ctx.moveTo(offsetX + 5 * cellWidth, offsetY);
        ctx.lineTo(offsetX + 3 * cellWidth, offsetY + 2 * cellHeight);
        ctx.stroke();
        
        ctx.beginPath();
        ctx.moveTo(offsetX + 3 * cellWidth, offsetY + 7 * cellHeight);
        ctx.lineTo(offsetX + 5 * cellWidth, offsetY + 9 * cellHeight);
        ctx.moveTo(offsetX + 5 * cellWidth, offsetY + 7 * cellHeight);
        ctx.lineTo(offsetX + 3 * cellWidth, offsetY + 9 * cellHeight);
        ctx.stroke();
        
        // 楚河汉界
        ctx.fillStyle = '#8b5a2b';
        ctx.font = 'bold 16px Arial';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('楚 河', offsetX + 2 * cellWidth, offsetY + 4.5 * cellHeight);
        ctx.fillText('汉 界', offsetX + 6 * cellWidth, offsetY + 4.5 * cellHeight);
        
        // 棋子字符映射到中文名称
        const pieceNames = {
            'r': '車', 'n': '馬', 'b': '象', 'a': '士', 'k': '將', 'c': '砲', 'p': '卒',
            'R': '车', 'N': '马', 'B': '相', 'A': '仕', 'K': '帅', 'C': '炮', 'P': '兵'
        };
        
        // 绘制棋子
        const pieceRadius = Math.min(cellWidth, cellHeight) * 0.35;
        
        Object.entries(this.boardState).forEach(([posKey, pieceChar]) => {
            const [col, row] = posKey.split(',').map(Number);
            const x = offsetX + col * cellWidth;
            const y = offsetY + row * cellHeight;
            
            // 判断红黑方（大写=红方，小写=黑方）
            const isRed = pieceChar === pieceChar.toUpperCase();
            const pieceName = pieceNames[pieceChar] || '?';
            
            // 绘制棋子圆圈
            ctx.beginPath();
            ctx.arc(x, y, pieceRadius, 0, Math.PI * 2);
            ctx.fillStyle = isRed ? '#fff5f5' : '#f0f0f0';
            ctx.fill();
            ctx.strokeStyle = isRed ? '#dc2626' : '#1f2937';
            ctx.lineWidth = 2;
            ctx.stroke();
            
            // 如果是选中状态，添加高亮
            if (this.selectedSquare && this.selectedSquare.col === col && this.selectedSquare.row === row) {
                ctx.beginPath();
                ctx.arc(x, y, pieceRadius + 4, 0, Math.PI * 2);
                ctx.strokeStyle = '#3b82f6';
                ctx.lineWidth = 3;
                ctx.stroke();
            }
            
            // 绘制棋子文字
            ctx.fillStyle = isRed ? '#dc2626' : '#1f2937';
            ctx.font = `bold ${pieceRadius * 0.9}px "Microsoft YaHei", Arial`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(pieceName, x, y);
        });
    }

    // 处理棋盘点击
    handleBoardClick(event) {
        if (!this.isPlayerTurn) {
            this.log('当前是AI回合，请等待', 'warning');
            return;
        }
        
        const canvas = event.target;
        const rect = canvas.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        
        // 计算点击的格子
        const cellWidth = (canvas.width - 40) / 8;
        const cellHeight = (canvas.height - 40) / 9;
        const offsetX = 20;
        const offsetY = 20;
        
        const col = Math.round((x - offsetX) / cellWidth);
        const row = Math.round((y - offsetY) / cellHeight);
        
        // 检查是否在棋盘范围内
        if (col < 0 || col > 8 || row < 0 || row > 9) return;
        
        const posKey = `${col},${row}`;
        
        if (!this.selectedSquare) {
            // 第一次点击：选择棋子（只能选红方）
            const piece = this.boardState[posKey];
            if (piece && piece === piece.toUpperCase()) { // 大写=红方
                this.selectedSquare = { col, row, key: posKey, piece };
                this.log(`选中棋子: ${piece} (${col}, ${row})`, 'info');
                this.drawVisualBoard();
            } else if (piece) {
                this.log('只能选择红方棋子', 'warning');
            }
        } else {
            // 第二次点击：移动棋子
            if (this.selectedSquare.key !== posKey) {
                const fromCol = this.selectedSquare.col;
                const fromRow = this.selectedSquare.row;
                const toCol = col;
                const toRow = row;
                
                // 转换为UCI格式走法
                const files = 'abcdefghi';
                // UCI排名：0=红方底线, 9=黑方底线
                // 我们的数组索引：0=黑方底线, 9=红方底线
                // 所以需要转换：array_row -> 9 - array_row
                const uciFromRow = 9 - fromRow;
                const uciToRow = 9 - toRow;
                const uciMove = `${files[fromCol]}${uciFromRow}${files[toCol]}${uciToRow}`;
                
                this.log(`玩家走法: ${this.selectedSquare.piece} (${fromCol},${fromRow}) -> (${toCol},${toRow})`, 'info');
                this.log(`UCI走法: ${uciMove}`, 'info');
                
                // 调用后端API执行玩家走法
                this.executePlayerMove(uciMove);
            } else {
                // 取消选择
                this.selectedSquare = null;
                this.drawVisualBoard();
            }
        }
    }

    // 执行玩家走法
    async executePlayerMove(uciMove) {
        try {
            const response = await fetch(`${this.apiBase}/player_move`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ move: uciMove })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.log(`玩家走法已确认: ${uciMove}`, 'info');
                
                // 添加到走法历史
                this.moveHistory = data.display_history || [...this.moveHistory, `红方 ${uciMove}`];
                this.updateMoveList();
                
                // 更新FEN显示
                if (data.fen) {
                    document.getElementById('fen-display').value = data.fen;
                    this.log(`新FEN: ${data.fen}`, 'info');
                }
                
                // 更新回合状态
                this.isPlayerTurn = data.is_player_turn || false;
                this.updateGameStatus();
                
                // 清除选择状态
                this.selectedSquare = null;
                
                // 解析UCI走法并更新可视化棋盘（玩家走棋不需要机械臂）
                this.updateBoardFromUCIMove(uciMove, false);  // 玩家走法
                
                this.lastAiBestMoveHandled = null;
                this.lastAiBoardApplied = null;
                this.checkAutoTriggerAI(data.fen);
            } else {
                this.log(`走法失败: ${data.error}`, 'error');
                // 恢复选择状态
                this.drawVisualBoard();
            }
        } catch (error) {
            this.log(`执行走法错误: ${error.message}`, 'error');
            this.drawVisualBoard();
        }
    }

    // 更新游戏状态显示
    updateGameStatus() {
        const statusEl = document.getElementById('game-status');
        const turnColor = this.isPlayerTurn ? this.playerColor : this.aiColor;
        const owner = this.isPlayerTurn ? '玩家' : '程序';
        statusEl.textContent = `轮到${this.colorName(turnColor)}（${owner}）`;
        statusEl.style.color = turnColor === 'red' ? '#dc2626' : '#1f2937';
    }

    updateGameStatusFromTurn(turnColor) {
        this.isPlayerTurn = turnColor === this.playerColor;
        const statusEl = document.getElementById('game-status');
        const owner = this.isPlayerTurn ? '玩家' : '程序';
        statusEl.textContent = `轮到${this.colorName(turnColor)}（${owner}）`;
        statusEl.style.color = turnColor === 'red' ? '#dc2626' : '#1f2937';
    }

    // 初始化标准棋盘布局
    initStandardBoard() {
        this.log('🔧 initStandardBoard() 被调用', 'info');
        
        // 中国象棋初始布局
        const initial = {
            '0,0': 'r', '1,0': 'n', '2,0': 'b', '3,0': 'a', '4,0': 'k', '5,0': 'a', '6,0': 'b', '7,0': 'n', '8,0': 'r',
            '1,2': 'c', '7,2': 'c',
            '0,3': 'p', '2,3': 'p', '4,3': 'p', '6,3': 'p', '8,3': 'p',
            '0,6': 'P', '2,6': 'P', '4,6': 'P', '6,6': 'P', '8,6': 'P',
            '1,7': 'C', '7,7': 'C',
            '0,9': 'R', '1,9': 'N', '2,9': 'B', '3,9': 'A', '4,9': 'K', '5,9': 'A', '6,9': 'B', '7,9': 'N', '8,9': 'R'
        };
        
        this.log('⚙️ 设置 boardState 为标准布局...', 'info');
        this.boardState = {...initial};
        
        this.log('✅ 标准布局已设置，棋子数量: ' + Object.keys(this.boardState).length, 'info');
        this.log('📍 红炮位置: 1,7=' + this.boardState['1,7'] + ', 7,7=' + this.boardState['7,7'], 'info');
        this.log('📍 黑炮位置: 1,2=' + this.boardState['1,2'] + ', 7,2=' + this.boardState['7,2'], 'info');
        
        this.drawVisualBoard();
    }

    // 动画机械臂移动
    animateRobotMove(move) {
        // 简化动画
        this.drawRobotVisualization();
    }

    // 更新状态
    async updateStatus() {
        try {
            const response = await fetch(`${this.apiBase}/status`);
            const data = await response.json();
            
            if (data.success) {
                this.currentState = data.state;
            }
        } catch (error) {
            // 静默失败
        }
    }

    // 检查是否需要自动触发 AI
    checkAutoTriggerAI(fen) {
        if (!this.isGameRunning || !fen || this.aiPollingTimer) return;
        
        const turnColor = this.currentTurnFromFen(fen);
        const aiColor = this.aiColor || document.getElementById('ai-color').value;
        
        // 更新 UI 上的回合显示
        this.updateGameStatusFromTurn(turnColor);
        
        if (turnColor === aiColor) {
            this.log(`检测到当前是 ${this.colorName(aiColor)}（程序）回合，自动开始思考...`, 'info');
            this.getAIMove();
        }
    }

    // 日志输出
    toggleLogPause() {
        this.logPaused = !this.logPaused;
        const btn = document.getElementById('btn-toggle-log-pause');
        if (btn) {
            btn.textContent = this.logPaused ? '恢复日志' : '暂停日志';
            btn.classList.toggle('btn-warning', this.logPaused);
            btn.classList.toggle('btn-secondary', !this.logPaused);
        }

        if (!this.logPaused) {
            const skipped = this.pausedLogCount;
            this.pausedLogCount = 0;
            if (skipped > 0) {
                this.log(`日志已恢复，暂停期间省略 ${skipped} 条页面日志`, 'warning');
            }
        }
    }

    log(message, type = 'info') {
        console.log(`[${type.toUpperCase()}] ${message}`);

        if (this.logPaused) {
            this.pausedLogCount += 1;
            return;
        }

        const logOutput = document.getElementById('log-output');
        const time = new Date().toLocaleTimeString('zh-CN');

        const entry = document.createElement('div');
        entry.className = `log-entry log-${type}`;
        entry.innerHTML = `<span class="log-time">[${time}]</span>${message}`;

        logOutput.appendChild(entry);
        logOutput.scrollTop = logOutput.scrollHeight;
    }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    window.simulation = new ChessSimulation();
    
    // 将函数暴露到全局作用域
    window.changeInputSource = () => window.simulation.changeInputSource();
    window.handleLocalImageUpload = (event) => window.simulation.handleLocalImageUpload(event);
});
