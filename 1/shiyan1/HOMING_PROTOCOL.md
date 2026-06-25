# 启动 Homing 通信协议

## 网络参数

- ESP8266 / STM32 TCP Server：`192.168.0.101:8086`
- 上位机和 NetAssist 都使用 TCP Client。
- NetAssist 可用于人工查看和调试，但不是上位机程序的转发器。
- ESP8266 已开启多连接，上位机与 NetAssist 可以同时连接。

## 启动命令

上位机点击“开始游戏”后发送：

```text
-17.1848,-55.6304,0,0,99
```

- 第 1 项：M1 相对转角，单位为度。
- 第 2 项：M2 相对转角，单位为度。
- 第 3、4 项：Homing 保留字段，当前固定为 `0`。
- 第 5 项：`99` 表示 Homing。

STM32 完成 M1、M2 运动后回传：

```text
STATE:0,RESULT:1
```

`STATE:0` 表示 Homing 完成并已回到空闲状态。新版固件也可以回传：

```text
STATE:0,RESULT:1,CMD:99
```

只有收到上述 Homing 成功回执，上位机才会开启棋局和视觉识别。普通走棋
完成仍使用 `STATE:5,RESULT:1`，不会被误判为 Homing 完成。

## 普通走子

普通走子继续使用：

```text
startX,startY,endX,endY,signal
```

- `signal=0`：不吃子。
- `signal=1`：吃子。

## 使用前检查

1. 在 Keil 中打开 `text1.uvprojx`。
2. 重新编译固件，确认无错误。
3. 将新固件烧录到 STM32F103C8。
4. 确认 ESP8266 加入 `ACE` Wi-Fi，并获得 `192.168.0.101`。
5. NetAssist 选择 TCP Client，目标为 `192.168.0.101:8086`，按“连接”。
6. 启动电脑端网页。系统日志第一条应显示 STM32 连接成功。

未连接下位机时，开始游戏会被拒绝，不会启动视觉识别。
