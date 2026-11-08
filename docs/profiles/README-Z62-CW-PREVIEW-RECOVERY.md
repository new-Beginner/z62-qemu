# r105 状态驱动的 CW 预览恢复观察

这是运行在冻结 r104 内核上的研究探针。它等待真实菜单进入后半按，只在四个新来源和新预览恢复后进入第二轮。默认交互入口仍 r75／r69，云端当前为 r104。

本地30.000884916秒窗口正常退出、没有通信超时；原厂从菜单回到拍摄界面，但背景黑色、CW203／preview37停止，没有完成新帧恢复。**两轮与预览恢复未通过**，不会自动重放按键或重启试验。完整证据、失败和下一步见[r105报告](../history/2026-11-04_研究-Z62状态驱动菜单返回与采集停用r105-report.md)。

```powershell
$env:TEMP='<WORKSPACE>/.runtime/tmp'
$env:TMP=$env:TEMP
& '.build/tools/video-r26/Scripts/python.exe' -X utf8 -B tools/probe_z62_cw_preview_recovery.py --card .runtime/migrated/c-runtime/fixtures/card-r22-4096.raw --group23 .runtime/migrated/c-runtime/fixtures/group23.bin --fixture .runtime/fixtures/group17-reference-r95.bin --output analysis/z62-cw-preview-recovery-r105/my-window --duration 30 --wall-limit 600
```

要求已有合法输入、专用普通文件虚拟卡、r104完整父构建、现有宿主GDB，以及经过同目录检查的Q:别名。所有新文件在工作目录。没有原始输入和构建缓存的新克隆不能直接运行。

首次真实通信超时会在清理之前保留Python调用现场、最近操作和所属QEMU宿主栈；若发生调试附加，该窗口不能作恢复功能验收。本轮无超时，抓栈分支没有触发，不证明旧超时已修复。

源包／帧身份核对与控制写入重放分别用 `tools/verify_z62_cw_preview_recovery.py`、`tools/analyze_z62_cw_recovery_controls.py`。它们的成功退出表示证据检查完成；只有独立结果中 `two_menu_cycles_and_preview_resume_verified=true` 才表示这个受限恢复检查通过。完整相机、AF及刷机安全需要另行验收。
