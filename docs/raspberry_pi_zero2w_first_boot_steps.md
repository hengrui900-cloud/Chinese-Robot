# 树莓派 Zero 2 W 首次启动与 USB 网络摄像头步骤

本文按你的当前条件写：

- 使用 USB 摄像头。
- 路由器只提供局域网，不能让树莓派联网下载。
- 电脑端 CH-RO 已支持输入网络摄像头 URL。
- MobaXterm 在桌面文件夹中。
- 当前检测到的存储卡是 `F:`，约 32GB，烧录前必须再次确认。

## 已准备好的文件

系统镜像：

```text
C:\CodexWork\CH-RO\raspios_images\2026-04-21-raspios-trixie-armhf-lite.img
```

压缩版镜像：

```text
C:\CodexWork\CH-RO\raspios_images\2026-04-21-raspios-trixie-armhf-lite.img.xz
```

官方 Raspberry Pi Imager 安装包：

```text
C:\CodexWork\CH-RO\raspios_images\raspberry_pi_imager_latest.exe
```

Pi 端 USB 摄像头离线服务包：

```text
C:\CodexWork\CH-RO\chch-robot-main\raspberry_pi_zero2w_usb_camera_offline
```

同一服务包压缩文件：

```text
C:\CodexWork\CH-RO\chro_pi_usb_camera_offline_pack.zip
```

当前已经复制到 `F:` 的临时副本：

```text
F:\CHRO_PI_USB_CAMERA_OFFLINE
```

注意：真正烧录系统镜像会清空 `F:`，所以烧录后需要重新复制服务包。

## 第 1 步：烧录系统镜像

推荐使用 Raspberry Pi Imager，不推荐只用 Win32DiskImager。原因是 Imager
可以在烧录时直接设置 Wi-Fi、SSH、用户名和密码，避免树莓派无显示器时连不上。

1. 打开：

```text
C:\CodexWork\CH-RO\raspios_images\raspberry_pi_imager_latest.exe
```

2. 安装并运行 Raspberry Pi Imager。
3. 设备选择：`Raspberry Pi Zero 2 W`，如果没有该项，选 `Raspberry Pi Zero 2 W / 3 / 4` 对应项。
4. 系统选择：`Use custom`，选择本地镜像：

```text
C:\CodexWork\CH-RO\raspios_images\2026-04-21-raspios-trixie-armhf-lite.img
```

5. 存储卡选择：确认是约 32GB 的 SD 卡，不要选电脑硬盘。
6. 进入系统自定义设置：
   - hostname: `raspberrypi`
   - username: `pi`
   - password: 设置英文密码，至少 7 位，不要全数字
   - enable SSH: 打开
   - Wi-Fi SSID: 填无 Internet 路由器的无线名称
   - Wi-Fi password: 填该无线密码
   - Wi-Fi country: `CN`
   - timezone: `Asia/Shanghai`
7. 点击写入。写入会清空 SD 卡。
8. 写完后安全弹出 SD 卡。

## 第 2 步：树莓派开机

1. 把烧录好的 SD 卡插入树莓派。
2. 把 USB 摄像头接到树莓派 USB 口。
3. 让电脑连接同一个无 Internet 路由器的 Wi-Fi。
4. 给树莓派上电。
5. 等 1 到 2 分钟。

## 第 3 步：找到树莓派 IP

优先方法：

- 进入路由器管理页面，看已连接设备。
- 设备名通常是 `raspberrypi`。

如果有 IP 扫描器，也可以扫描当前网段，找新出现的设备。

如果能 ping 到主机名，也可以在 Windows 终端尝试：

```powershell
ping raspberrypi.local
```

## 第 4 步：用 MobaXterm SSH 连接

MobaXterm 路径：

```text
C:\Users\Henry Lau\Desktop\MobaXterm_Portable_v22.2\MobaXterm_Personal_22.2.exe
```

连接信息：

- Session: SSH
- Remote host: 树莓派 IP，例如 `192.168.1.24`
- Port: `22`
- Username: `pi`
- Password: 烧录时设置的密码

首次连接如果提示是否信任主机，选 yes。

## 第 5 步：检查 USB 摄像头

SSH 登录后输入：

```bash
lsusb
ls /dev/video*
groups
```

如果能看到 `/dev/video0`，说明系统识别到了 USB 摄像头。

如果 `groups` 里没有 `video`：

```bash
sudo usermod -a -G video $USER
sudo reboot
```

重启后重新 SSH 登录。

## 第 6 步：复制摄像头服务包到树莓派

用 MobaXterm 左侧/右侧的 SFTP 文件面板，把这个文件夹复制到树莓派：

```text
C:\CodexWork\CH-RO\chch-robot-main\raspberry_pi_zero2w_usb_camera_offline
```

目标位置建议：

```text
/home/pi/chro-usb-camera
```

也可以复制压缩包 `chro_pi_usb_camera_offline_pack.zip`，再在树莓派上解压。

## 第 7 步：启动 USB 摄像头服务器

SSH 中输入：

```bash
cd ~/chro-usb-camera
bash start_usb_camera_server.sh
```

看到类似输出：

```text
Preview URL: http://0.0.0.0:8080/
```

再查 IP：

```bash
hostname -I
```

如果 IP 是 `192.168.1.24`，电脑浏览器打开：

```text
http://192.168.1.24:8080/
```

能看到画面，就说明服务器成功。

## 第 8 步：接入 CH-RO 网页

1. 电脑运行 CH-RO 后端。
2. 打开 CH-RO 网页。
3. 选择网络摄像头模式。
4. 输入：

```text
http://<树莓派IP>:8080
```

5. 点击连接。
6. 再点击开始游戏或开始识别。

## 第 9 步：设置开机自启

手动启动确认能看到画面后，再执行：

```bash
cd ~/chro-usb-camera
bash install_service.sh
```

查看状态：

```bash
systemctl status chro-usb-camera --no-pager
```

查看日志：

```bash
journalctl -u chro-usb-camera -f
```

## 常见问题

如果打不开 URL：

```bash
hostname -I
systemctl status chro-usb-camera --no-pager
journalctl -u chro-usb-camera -n 50 --no-pager
```

如果日志说摄像头不支持 MJPEG，说明纯离线 V4L2 模式不适配这个摄像头。后续需要临时给树莓派联网安装：

```bash
sudo apt update
sudo apt install -y fswebcam
```

或者：

```bash
sudo apt update
sudo apt install -y python3-opencv
```

然后重新运行：

```bash
bash start_usb_camera_server.sh
```
