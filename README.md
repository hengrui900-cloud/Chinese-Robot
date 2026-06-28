# 中国象棋人机博弈机器人系统

一套完整的线下中国象棋人机对弈系统，集成视觉识别、AI 引擎、机械臂控制和 Web 管理界面。

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Web 管理界面 (Flask)                          │
│                   http://localhost:5000                              │
└──────────┬──────────────────┬──────────────────┬────────────────────┘
           │                  │                  │
     ┌─────▼─────┐    ┌──────▼──────┐    ┌──────▼──────┐
     │  视觉识别  │    │   AI 引擎   │    │  机械臂控制  │
     │  vision/   │    │    ai/      │    │   robot/    │
     └─────┬─────┘    └──────┬──────┘    └──────┬──────┘
           │                  │                  │
     ┌─────▼─────┐    ┌──────▼──────┐    ┌──────▼──────┐
     │ ONNX 模型  │    │  Pikafish   │    │   STM32     │
     │ RTMPose +  │    │  UCI 引擎   │    │  下位机     │
     │ 分类器     │    │             │    │  (TCP)      │
     └───────────┘    └─────────────┘    └─────────────┘
```

### 数据流

```
摄像头画面 (USB / 网络摄像头)
    ↓
棋盘关键点检测 (RTMPose ONNX)
    ↓
棋子分类识别 (Full Classifier ONNX)
    ↓
多帧稳定化 + 动态追踪
    ↓
棋盘状态 → FEN 生成
    ↓
Pikafish AI 引擎思考 (UCI 协议)
    ↓
UCI 走法 → 机械臂坐标转换
    ↓
TCP 发送至 STM32 下位机执行
```

## 功能特性

- **实时棋盘识别**: ONNX 模型推理，支持 USB 摄像头和网络摄像头（MJPEG/RTSP 流）
- **动态走子检测**: `DynamicBoardTracker` 基于占用差异自动推断走法，内置容错和中国象棋规则合法性校验
- **多帧稳定化**: `StableBoardBuffer` 通过投票机制消除检测抖动
- **AI 对弈**: 集成 Pikafish（皮卡鱼）引擎，UCI 协议通信，支持深度/时间控制
- **机械臂控制**: 支持仿真模式和真实 STM32 机械臂（TCP 五值指令协议）
- **Web 管理界面**: Flask 后端 + 前端页面，提供摄像头预览、棋盘识别、AI 对弈、机械臂状态监控
- **硬件/仿真双模式**: 启动时可选择 `hardware`（真实机械臂）或 `simulation`（纯软件模拟）
- **Homing 握手**: 硬件模式启动时自动发送归位指令，等待 STM32 确认后才开始对弈

## 硬件需求

| 组件 | 要求 | 说明 |
|------|------|------|
| **摄像头** | USB 摄像头 720p+ 或网络摄像头 | 用于拍摄棋盘画面 |
| **机械臂** | 6 自由度机械臂 + STM32 控制板 | 通过 TCP 控制，可选 |
| **计算机** | Windows/Linux，CPU 支持 AVX2 | 运行主程序和 AI 引擎 |
| **棋盘** | 标准中国象棋棋盘 | 建议固定位置和角度 |

## 快速开始

本节按“说明书”方式描述一次完整部署。默认主控电脑运行 Web 后端、视觉识别和 Pikafish；香橙派/树莓派只作为网络摄像头控制板，且默认控制板可以访问 Internet。

### 1. 下载代码包

#### 方式 A：Git 克隆（推荐）

在主控电脑上执行：

```bash
git clone https://github.com/hengrui900-cloud/Chinese-Robot.git
cd Chinese-Robot
```

如果已经克隆过，更新到最新版：

```bash
cd Chinese-Robot
git pull
```

#### 方式 B：下载 ZIP

也可以在 GitHub 页面点击 `Code -> Download ZIP`，解压后进入项目根目录。后续命令都默认在 `Chinese-Robot/` 根目录下执行。

### 2. 安装依赖

建议使用 Python 3.10 或 3.11。Windows 示例：

```powershell
cd Chinese-Robot
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Linux 示例：

```bash
cd Chinese-Robot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

如果没有 NVIDIA GPU 或 `onnxruntime-gpu` 安装失败，可以将 `requirements.txt` 中的 `onnxruntime-gpu` 临时改为 `onnxruntime` 后重新安装。

### 3. 下载 Pikafish 引擎

从 [Pikafish 官方发布页](https://github.com/official-pikafish/Pikafish/releases) 下载对应平台的引擎文件，解压到项目根目录的 `Pikafish/` 文件夹。

Windows 默认配置：

```text
Chinese-Robot/
└── Pikafish/
    └── pikafish-avx2.exe
```

如文件名或路径不同，请修改 `config.py`：

```python
ENGINE_PATH = "./Pikafish/pikafish-avx2.exe"
ENGINE_DEPTH = 15
```

### 4. 香橙派/树莓派创建摄像头服务器并生成 URL

主控电脑可以直接使用 USB 摄像头；如果摄像头插在香橙派或树莓派上，则需要先在控制板上启动摄像头服务器，再把生成的 URL 输入到 Web 页面。

#### 推荐方案：HTTP MJPEG 摄像头服务

这个方案生成 `http://<控制板IP>:8080`，可直接填入 Web 页面的“网络摄像头”输入框。香橙派和树莓派都可以先按这套方式尝试。

在香橙派/树莓派上执行：

```bash
sudo apt update
sudo apt install -y git python3 python3-pip v4l-utils

git clone --depth 1 https://github.com/hengrui900-cloud/Chinese-Robot.git
cd Chinese-Robot/raspberry_pi_zero2w_usb_camera_offline

bash start_usb_camera_server.sh
```

另开一个 SSH 终端查看控制板 IP：

```bash
hostname -I
```

假设输出的 IP 是 `192.168.1.24`，则摄像头 URL 为：

```text
http://192.168.1.24:8080
```

浏览器也可以先打开预览页确认画面：

```text
http://192.168.1.24:8080/
```

手动启动确认正常后，可以设置开机自启：

```bash
cd ~/Chinese-Robot/raspberry_pi_zero2w_usb_camera_offline
bash install_service.sh
systemctl status chro-usb-camera --no-pager
```

查看服务日志：

```bash
journalctl -u chro-usb-camera -f
```

#### 香橙派旧版 WebSocket 服务

项目也保留了香橙派 WebSocket 摄像头服务，会生成 `ws://<香橙派IP>:8765`。它主要用于 `orange-pi-camera/test_network_camera.py` 和 `vision/network_camera.py` 这一套客户端流程；Web 页面默认更推荐输入上面的 HTTP URL。

在香橙派上执行：

```bash
sudo apt update
sudo apt install -y git python3 python3-pip python3-opencv

git clone --depth 1 https://github.com/hengrui900-cloud/Chinese-Robot.git
cd Chinese-Robot/orange-pi-camera

python3 -m pip install -r requirements.txt
bash start_server.sh
```

启动脚本会打印类似：

```text
WebSocket地址: ws://192.168.1.100:8765
```

### 5. 运行指南

#### 启动 Web 系统（推荐）

在主控电脑的项目根目录执行：

```bash
python web_simulation/app.py
```

启动时终端会询问是否修改棋盘横向/纵向格距、楚河汉界间距和下位机 IP。正式使用机械臂时，按实际下位机地址填写；只做网页模拟时可以直接回车使用默认值。

如果希望跳过启动询问：

```powershell
$env:CHRO_SKIP_STARTUP_PROMPT="1"
python web_simulation/app.py
```

Linux/macOS：

```bash
CHRO_SKIP_STARTUP_PROMPT=1 python web_simulation/app.py
```

启动成功后，主控电脑浏览器打开：

```text
http://127.0.0.1:5000
```

同一局域网其他设备访问时，把 `127.0.0.1` 换成主控电脑 IP：

```text
http://<主控电脑IP>:5000
```

#### 命令行模式

```bash
python main.py
```

常用测试命令：

```bash
python main.py --demo           # 演示模式
python main.py --test-camera    # 测试摄像头
python main.py --test-engine    # 测试 Pikafish 引擎
```

### 6. 网页介绍

Web 页面是项目的主要操作台，分为三类区域：

#### 左侧：对局控制与输入源

- `正式使用（连接下位机）`：连接 STM32/机械臂，AI 走法会转换成机械臂 TCP 指令。
- `模拟测试（无下位机）`：不连接真实机械臂，只在网页中模拟走棋流程，适合调试视觉识别和 AI。
- `重置游戏`：清空当前局面和走法历史。
- `程序执色`：默认程序执黑，玩家执红。
- `搜索深度`：控制 Pikafish 思考深度，数值越大思考越慢但质量更高。

#### 画面输入

在 `画面输入 -> 输入源` 中选择：

- `USB 摄像头`：摄像头直接插在主控电脑上。
- `网络摄像头`：摄像头插在香橙派/树莓派上，通过 URL 取流。
- `本地图片`：上传单张棋盘图片进行静态识别。

使用网络摄像头时：

1. 选择 `网络摄像头`。
2. 在弹出的输入框中输入控制板生成的 URL，例如：

```text
http://192.168.1.24:8080
```

3. 点击 `连接`。
4. 看到真实画面后，再点击 `模拟测试（无下位机）` 或 `正式使用（连接下位机）`。

#### 中间：真实画面与虚拟棋盘

- `真实画面`：显示摄像头画面，并叠加棋盘识别结果。
- `虚拟识别画面`：把识别到的棋子同步成网页棋盘。
- `FEN`：后端内部会将识别状态转换成中国象棋 FEN，供 Pikafish 分析。

#### 右侧：走法历史、AI 分析、系统日志

- `走法历史`：记录玩家和 AI 的 UCI 走法。
- `AI 分析`：显示 Pikafish 当前推荐走法、分数、深度和主变。
- `系统日志`：显示摄像头连接、动态识别、AI 思考、机械臂执行和错误信息。

### 7. 典型使用流程

#### 只做网页模拟

1. 启动 `python web_simulation/app.py`。
2. 打开 `http://127.0.0.1:5000`。
3. 选择 USB 摄像头、网络摄像头或本地图片。
4. 如果是网络摄像头，在输入框填入 `http://<控制板IP>:8080` 并点击 `连接`。
5. 点击 `模拟测试（无下位机）`。
6. 摆好棋盘后，系统进入动态识别；玩家走红棋，系统识别走法后自动触发 AI。

#### 连接真实机械臂

1. 确认 STM32 下位机已经上电，并在局域网内监听 TCP `8086`。
2. 启动 Web 后端时填写下位机 IP，或在 `config.py` 中修改：

```python
ROBOT_NETWORK_HOST = "192.168.0.102"
ROBOT_NETWORK_PORT = 8086
```

3. 打开网页并连接摄像头。
4. 点击 `正式使用（连接下位机）`。
5. 系统会先发送 Homing 归位指令，收到下位机确认后进入正式对弈。
6. 玩家走棋后，视觉模块检测走法；AI 思考后，机械臂执行 AI 走法。

### 8. 其他说明

- 主控电脑、香橙派/树莓派、STM32 下位机需要在同一局域网。
- 网络摄像头 URL 优先使用 `http://<控制板IP>:8080`；如果直接填 `/stream.mjpg` 也可以，但根地址更方便后端自动选择 `/snapshot.jpg` 或 `/stream.mjpg`。
- 树莓派 Zero 2 W 性能有限，推荐 `640x480`、`8 fps`，清晰稳定比高帧率更重要。
- 真实棋盘使用前应固定相机位置、光照和棋盘位置，避免识别基线频繁变化。
- 模型文件位于 `model/`，Pikafish 引擎不随仓库自动安装，需要单独下载。
- 日志文件默认为 `chchess.log`，遇到摄像头、AI 或机械臂问题时优先查看终端日志和该文件。
- 本项目面向可信局域网使用，摄像头服务和 Web 服务不要直接暴露到公网。

## 项目结构

```
Chinese-Robot/
├── main.py                     # 命令行入口
├── game_manager.py             # 游戏流程管理器
├── config.py                   # 全局配置
├── utils.py                    # FEN/坐标/记谱法工具函数
├── requirements.txt            # Python 依赖
│
├── vision/                     # 视觉识别模块
│   ├── camera.py               # 摄像头管理（USB + 网络摄像头）
│   ├── detector.py             # ONNX 检测器封装
│   ├── mapper.py               # 透视变换和坐标映射
│   ├── stabilizer.py           # 多帧稳定化 + 动态走子追踪
│   ├── network_camera.py       # 网络摄像头工具
│   └── recognizer.py           # 高层识别 API
│
├── ai/                         # AI 引擎模块
│   └── engine.py               # Pikafish UCI 协议通信
│
├── robot/                      # 机械臂控制模块
│   ├── controller.py           # 仿真控制器
│   ├── protocol.py             # 五值指令协议 + TCP 传输
│   └── tcp_client.py           # STM32 TCP 客户端
│
├── core/                       # 底层 ONNX 推理
│   ├── chessboard_detector.py  # 棋盘检测核心
│   ├── helper_4_kpt.py         # 关键点辅助
│   └── runonnx/                # ONNX 推理封装
│
├── web_simulation/             # Web 管理界面
│   ├── app.py                  # Flask 后端
│   ├── templates/index.html    # 前端页面
│   └── static/                 # CSS/JS 静态资源
│
├── model/                      # ONNX 模型文件
│   ├── pose/                   # 姿态估计模型
│   └── layout_recognition/     # 棋子分类模型
│
├── stm32-robot/                # STM32 下位机固件 (C)
│   ├── main.c
│   ├── robot_control.c/h       # 机械臂运动控制
│   ├── robot_tcp_server.c/h    # TCP 服务器
│   ├── json_parser.c/h         # JSON 解析
│   ├── Makefile
│   └── PROTOCOL.md             # 通信协议文档
│
├── orange-pi-camera/           # Orange Pi 网络摄像头服务
│   └── camera_server.py
│
├── raspberry_pi_zero2w_usb_camera_offline/  # 树莓派摄像头服务
│   └── usb_mjpeg_server.py
│
├── dataset/                    # 训练数据集
└── tests/                      # 单元测试
```

## 核心模块详解

### 视觉识别 (`vision/`)

**摄像头管理** (`camera.py`):
- 支持 USB 本地摄像头和网络摄像头（HTTP MJPEG / RTSP / RTMP）
- 后台线程持续读取帧，自动检测故障并恢复
- `HttpSnapshotCapture` 专门处理 HTTP 快照/MJPEG 流

**棋盘检测** (`detector.py`):
- 懒加载 ONNX 模型（首次推理时加载，避免重复创建会话）
- 线程安全的推理锁
- 输出：棋盘关键点 + 90 格棋子分类

**动态追踪** (`stabilizer.py`):
- `StableBoardBuffer`: 多帧投票稳定化
- `DynamicBoardTracker`: 连续帧对比，自动推断走法
- `infer_one_move_from_occupancy()`: 从占用差异推断走法，支持容错（噪声点容忍）
- `_is_legal_xiangqi_move()`: 中国象棋规则合法性校验（车马炮象士将卒）

**识别器** (`recognizer.py`):
- `recognize_board()`: 静态识别，返回稳定棋盘状态
- `recognize_dynamic_frame()`: 动态识别，返回事件（`move` / `unchanged` / `initial_locked`）
- `sync_dynamic_baseline()`: 同步游戏状态基线到追踪器

### AI 引擎 (`ai/`)

- 通过子进程启动 Pikafish，UCI 协议通信
- 设置 `UCI_Variant = xiangqi` 启用中国象棋模式
- `set_position()`: 同步 FEN 和走法历史
- `get_best_move()`: 获取引擎最佳走法
- `analyze_position()`: 分析局面（分数、深度、主变）
- `get_current_fen_after_moves()`: 通过引擎 `d` 命令获取当前 FEN

### 机械臂控制 (`robot/`)

**五值指令协议** (`protocol.py`):
```
startX, startY, endX, endY, signal
```
- `signal = 0`: 普通移动
- `signal = 1`: 吃子序列

**坐标转换**:
- `BoardToArmConfig`: UCI 方格 → 机械臂坐标（毫米）
- 原点在棋盘右上角（黑方右侧车位置）
- 横向间距 34mm，纵向间距 30mm，楚河汉界 32mm

**TCP 通信** (`protocol.py` 中的 `RobotPersistentClient`):
- 持久 TCP 连接，发送五值指令后等待 STM32 确认
- 确认条件：收到 `STATE:5,RESULT:1`
- 支持 Homing 归位指令（`m1_angle,m2_angle,0,0,99`）

**STM32 下位机** (`stm32-robot/`):
- C 语言固件，TCP 服务器监听端口
- JSON 格式指令解析
- 电机控制、夹爪控制、运动规划

### Web 管理界面 (`web_simulation/`)

**后端 API** (`app.py`):

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/status` | GET | 获取游戏状态 |
| `/api/cameras` | GET | 列出可用摄像头 |
| `/api/camera/stream` | GET | MJPEG 实时视频流 |
| `/api/camera/frame` | GET | 单帧 JPEG |
| `/api/camera/start` | POST | 启动摄像头 |
| `/api/camera/status` | GET | 摄像头状态 |
| `/api/network_camera/connect` | POST | 连接网络摄像头 |
| `/api/network_camera/disconnect` | POST | 断开网络摄像头 |
| `/api/recognize` | POST | 静态识别棋盘 |
| `/api/recognize/dynamic` | POST | 动态识别（追踪走子） |
| `/api/ai_move` | POST | 启动 AI 思考（异步） |
| `/api/ai_status` | GET | AI 分析状态 |
| `/api/player_move` | POST | 提交玩家走法 |
| `/api/robot/status` | GET | 机械臂连接状态 |
| `/api/game/start` | POST | 开始新游戏 |
| `/api/game/reset` | POST | 重置游戏 |

**游戏流程**:
1. 选择机械臂模式（hardware / simulation）
2. 硬件模式自动发送 Homing 归位指令
3. 使用标准初始布局作为识别基准
4. 玩家走棋（红方）→ 视觉动态检测 → 后端同步记录
5. AI 走棋（黑方）→ 引擎思考 → 机械臂执行 → 视觉暂停后恢复
6. 循环直到游戏结束

**关键机制**:
- **视觉暂停**: AI 走棋后暂停视觉识别，等待机械臂完成
- **物理基线确认**: 硬件模式下，机械臂落子后需连续 N 帧识别一致才解锁
- **防重复**: 基于 `ai_command_token` 和 `last_player_move` 防止重复走法

## 网络摄像头部署

快速部署流程见上文“快速开始 -> 香橙派/树莓派创建摄像头服务器并生成 URL”。

常用 URL：

- Web 页面推荐输入：`http://<控制板IP>:8080`
- HTTP 预览页：`http://<控制板IP>:8080/`
- MJPEG 流地址：`http://<控制板IP>:8080/stream.mjpg`
- 单帧快照地址：`http://<控制板IP>:8080/snapshot.jpg`
- 香橙派旧版 WebSocket 地址：`ws://<香橙派IP>:8765`

更详细的树莓派说明见 `docs/raspberry_pi_zero2w_camera.md` 和 `raspberry_pi_zero2w_usb_camera_offline/README_FIRST.md`。

## 运行测试

```bash
# 运行全部测试
python -m pytest tests/ -v

# 运行单个测试文件
python -m pytest tests/test_stabilizer.py -v

# 运行特定测试
python -m pytest tests/test_robot_protocol.py -v -k "test_homing"
```

测试文件说明：
- `test_stabilizer.py` — 动态追踪器和走法推断
- `test_robot_protocol.py` — 五值指令协议和坐标转换
- `test_camera_source.py` — 摄像头源规范化
- `test_detector_runtime.py` — 检测器运行时
- `test_recognizer_concurrency.py` — 识别器并发安全
- `test_robot_backend_loop.py` — 机械臂后端循环
- `test_frontend_homing_contract.py` — 前端 Homing 契约
- `test_stm32_homing_contract.py` — STM32 Homing 契约
- `test_usb_camera_server.py` — USB 摄像头服务

## FEN 编码说明

标准中国象棋 FEN 格式：
```
rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1
```

- 大写字母 = 红方（R车 N马 B相 A仕 K帅 C炮 P兵）
- 小写字母 = 黑方（r车 n马 b象 a士 k将 c炮 p卒）
- 数字 = 连续空位数
- `w` = 红方走棋，`b` = 黑方走棋

UCI 走法格式：`h0h2`（从 h0 移动到 h2）

## 日志

日志文件：`./chchess.log`

配置日志级别（`config.py`）：
```python
LOG_LEVEL = "INFO"          # DEBUG, INFO, WARNING, ERROR
SAVE_LOG_TO_FILE = True
```

## 许可证

本项目采用 GPL v3.0 许可证。
