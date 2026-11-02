# r7原生RAW帧源实验

**r7不是完整取景版本，严格菜单重开回归未通过；正常主入口仍保留r6。** 本层让原固件驱动真正的RAW批次写入和通道2完成，不再依靠宿主手动提供这些边界。

研究启动：

```bat
python -X utf8 -B tools\run_z62_raw_stream.py --experimental-parameters --capcom-sync --raw-completion --capture-preset init-mode --paired-sync --input-drain --no-auto-menu
```

控制台：<http://127.0.0.1:8677>。当前仍可能一直黑屏；页面关闭按钮只结束本会话。支持与r6相同的候选固件参数，但不把此版本的运行成功当作真机安全结论。

原生二进制：`.build/z62-raw-stream-2026.10.29-r7/runtime/qemu-system-arm.exe`，SHA256为 `838e82868251e94d57ee72b6f94ff7bf9d6412df56915cf9d66fc5d7b02062b3`。

已验证245批自动四槽RAW写入、原固件描述符换组和停止；还缺统计内容、完整ISP/LCD消费和拍照存卡。`raw_stream_status` 提供只读尝试/成功/失败/背压计数，`live_view_verified`仍为false。

- [详细实施与失败证据](../history/2026-10-29_实施-Z62原生RAW帧源r7与后续统计缺口-report.md)
- [设备合同](../../qemu/z62-raw-stream/CONTRACT.md)
- [r6使用说明](README-Z62-QEMU.md)
