# Z6II QEMU r9实验预览

r9已把合成RAW数据经功能近似转换写入原厂NV12输出，并由原厂LCD显示测试图样。**统一入口现使用r9内核加r10b输入：已验证真实半按快门返回菜单后的连续预览。** 下文保留r9旧“EXIT”（扩展输入0）失败记录；这条原始输入的停流恢复仍未解决。r9不是完整相机模拟器，不能据此判定真机刷写安全。

独立研究入口（已实际验证HTTP启动、设备状态读取及正常关闭）：

日常测试请使用 [统一入口与半按按钮](README-Z62-QEMU.md)。以下旧研究入口保留原输入映射，适合复现历史对照。

```powershell
python -X utf8 -B tools/run_z62_preview.py --experimental-parameters --capcom-sync --functional-raw --raw-completion --capture-preset init-mode --no-auto-menu
```

地址为 <http://127.0.0.1:8679>。候选输入仍支持`--firmware`或`--members`，健康状态保持未知。`--no-preview`关闭新增模型作对照。当前画面是合成RAW测试图样，不是真实相机画质。

内核：`.build/z62-preview-2026.10.29-r9/runtime/qemu-system-arm.exe`。

SHA256：`cdd260cba6d28801e00ada2df0ce496b2037bdd6b43beb887118c50246be1961`。

## 已验证的范围

- 实际RAW → 固定裁边、RGGB单元颜色、sRGB响应、缩放、NV12 → 原厂提交的三路输出 → LCD。
- 22.107客体秒的原固件运行完成187批、2244路输出，拒绝0；画面背景16个抽查点与独立计算逐像素相同。
- 原生DMA测试覆盖完整12输出预检、越界/重叠拒绝、已生产源验证、屏蔽/W1C、背压、取消重启、复位和主从隔离。
- 独立C像素测试和旧RAW/有限统计原生回归通过；261项全量测试通过。
- 三轮菜单状态/导航通过；候选ARM测试指令在同一内核实际执行，候选HTTP入口保持健康状态未知。

## 尚未通过的范围

退出菜单后返回APPLV，停留11.319客体秒，预览批次仍停在425；图像通道保持停止状态，未重新提交预览。因此菜单导航通过不代表预览恢复通过。使用MENU再次关闭菜单的对照也没有离开菜单，不能拿它替代原验收。

本模型只报告自己处理的预览命令bank1完成。统计bank0未执行；任意加载包中的矩阵、LUT、降噪、锐化和其它裁剪算子仍未复现。修改这些参数的候选固件不能在此验证其数值效果。拍照编码、保存回放和完整更新流程也尚未完成。

详细依据见 [设备合同](../../qemu/z62-preview/CONTRACT.md)及 [实施报告](../history/2026-10-29_实施-Z62预览像素r9与恢复缺口-report.md)。严格复核：

```powershell
python -X utf8 -B tools/verify_z62_preview_evidence.py --require-resume
```

这条历史命令仍应返回非零，因为它检查旧输入0的恢复条件；不得把其它测试的通过数覆盖这一失败。真实半按的独立验收用 `python -X utf8 -B tools/verify_z62_shutter_evidence.py`，输入映射及混入全按的修正过程见 [报告](../history/2026-10-29_修复-Z62快门输入与预览连续性-report.md)。
