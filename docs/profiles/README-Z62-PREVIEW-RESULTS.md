# Z62 r47b 预览结果设备

r47b在已存在的RAW→NV12功能预览上实现了逐单元结果通知。只有已观察配置匹配、4份实际RAW读入和12路NV12全部写回后，才锁存`2010001C=61`。原厂固件已实际进入82回调和三个事件发布点。

这仍是实验内核：IRQ路由为B层，像素运算沿用C层近似；银行0的11节点图未执行，原厂拍照保存、模式恢复、完整镜头与AF及整机验收仍未完成。默认相机入口保持原验收范围。

## 内核与开关

- 当前内核：`.build/z62-preview-results-format-2026.11.02-r47b/runtime/qemu-system-arm.exe`
- SHA256：`145520bd35f763957f6be0e0cce33cb84312f34a6501991f49a93af91f9e46e8`
- 新功能默认关闭；在已有实验预览配置上显式添加：`-global nikon-z72-boot-config.z62-preview-results=on`。
- r24、r21及初版r47均保留；初版r47不接受后续格式变化，不作为本阶段推荐内核。

## 已验证的范围

| 项目 | 范围 |
|---|---|
| 物理单元 | 54、49、55，分别产生结果位20、01、40 |
| 可见输出 | 1920×1080、1024×682、1024×680 |
| 内部行数 | 当前C1.70实验配置写出1108、700、698；不同于Z72 |
| 格式变化 | 54／55接受实际观察的bit9变化；49保持所观察的LCD配方 |
| 数据前提 | 普通RAM参数、有效提交、正确几何及真正写回；配置寄存器本身不产生完成 |
| 保护 | W1C逐位确认、共享IRQ102、屏蔽待定、背压、取消／停止、复位、从引擎隔离 |
| 软件字段 | RAM参数+8C回调和+90事件值不决定硬件成功；原生测试种入无关值且保持不变 |
| 未支持 | 任意节点算子、部分输出图、银行0统计图和尼康ISP数值等价性 |

像素处理仍为已有的裁边、CFA单元颜色、缩放和NV12功能近似。它不提供实机画质或处理器时序的校准结果。VMState45登记了新增开关和计数，完整系统及外部模型快照恢复仍待验收。

## 验证命令

在工作区根目录运行，输出使用新的文件或目录，避免覆盖既有证据：

```powershell
.build/tools/video-r26/Scripts/python.exe -X utf8 -B tools/check_z62_preview_results_format.py --headers qemu/z62-preview-results-format --output analysis/z62-results-r47/format-new
.build/tools/video-r26/Scripts/python.exe -X utf8 -B tools/probe_z62_preview_results.py --output analysis/z62-results-r47/native-new.json
.build/tools/video-r26/Scripts/python.exe -X utf8 -B tools/trace_z62_preview_result_delivery.py --output analysis/z62-results-r47/delivery-new --card <USERPROFILE>/Documents/Z62-QEMU-runtime/fixtures/card-r22-4096.raw --group23 <USERPROFILE>/Documents/Z62-QEMU-runtime/fixtures/group23.bin --duration 12
.build/tools/video-r26/Scripts/python.exe -X utf8 -B -m unittest discover -s tests -q
```

前两项为无原厂固件的C／原生QEMU检查；第三项执行固定原始C1.70并通过GDB观察，使用普通文件snapshot卡，不连接相机。第三项不是完整拍摄验收，事件发布点也不等于下游任务全部完成。

## 构建与来源

构建器只创建独立工作目录，不覆盖已有构建；顺序为冻结r24→r47→r47b：

```powershell
.build/tools/video-r26/Scripts/python.exe -X utf8 -B tools/build_z62_preview_results.py --jobs 8
.build/tools/video-r26/Scripts/python.exe -X utf8 -B tools/build_z62_preview_results_format.py --jobs 8
```

已有构建无需重新创建。各层manifest绑定父二进制、适配器、生成源及运行库；r47b独立校验见`tools/run_z62_preview_results_format.py`。物理参数来自本机8份快照（本地证据，未分发：`analysis/z62-results-r47/config-1/physical-configs.json`），[两份配方](../../qemu/z62-preview-results/observed-profile.json)均保留；Z72固定`d91718fd`仅作为结果通知设计的参考。

[本轮报告](../history/2026-11-02_实施-Z62预览逐单元结果r47b-report.md)记录原生检查、原厂回调配对、窗口末尾的未完成记录和剩余工作；[能力覆盖表](../CAPABILITY-COVERAGE.md)仍是完整相机范围的清单。
