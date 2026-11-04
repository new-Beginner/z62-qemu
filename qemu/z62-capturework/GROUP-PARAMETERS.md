# r94／r95：采集组资源来源与独立虚拟输入

此路线使用冻结r93内核，不改C1.70或原厂AF。新的group17文件是**显式虚拟参数**，不是相机标定、NOR dump或可刷写升级包；默认r75界面／r69内核不变。

## 已更正的参数布局

固定Z62原字节证明：

| 数据 | 地址／调用 | 下层实现 |
|---|---|---|
| 参数结构 | C26A0884h | 原厂参数提供者写入 |
| 三组packed系数 | 结构+3Eh，即C26A08C2h；10239C60h调用1020C132h | 10208CB0h将24个byte写入B820h三行，后7列保留低7位 |
| 另一组配置 | 结构+58h，即C26A08DCh；10239C14h调用1020C13Eh | 10208CF4h；它不是系数setter |
| 曲线指针槽 | 结构+80h，即C26A0904h；10239C6Ah调用1020C14Ah | 10208DB6h读取65个u16 |

r93的parameter-source标签把+58误称为系数实参。旧脚本及回执保持，当前以r94 resource-contract和本表为准；底层group数值模型本来使用实际B820寄存器，未受该标签错误影响。

## 从虚拟资源到实际寄存器

Z62 ROM表118D74C0h的行是`{0,11500h,2C00h,00270300h}`，资源ID为39。原厂链路包括1021F3E2h→103DFC14h→102ABBC0h→102AB28Ah；提供者从上下文+18h取得资源地址，以+1800h为主体基址。四个系数变体在186Ch／18CCh／192Ch／198Ch，另一个在26B0h，每个24个u32；65点u16曲线在1A1Ch。

被动观察读到上下文C21835D4h、来源C8159500h、曲线C25DAF18h。完整128KiB候选缓存与staged group17有10字节不同，不能称为整块文件镜像。独立诊断只修改group17中资源曲线第17点为0123h：该标签经原厂加载进入实际资源缓存、曲线缓冲及寄存器，其他点和系数保持0，模型仍拒绝处理、不发完成。此对照确立本实验的加载路径，而非依赖两个全零区域的相等。

## 两种明确输入

`tools/create_z62_group_parameter_input.py`只接受原有冻结的合成group17基线，拒绝非零资源体和重复变换，输出与manifest均不覆盖既有文件。

- `marker`只改2字节，用于诊断数据流，不提供可处理数值配置。
- `reference`改140字节，设置`min(i*1024,65535)`的65点曲线；五套变体各声明三组+1／−1差分FIR，tap3与tap4/5/6成对。它供C参考算子使用，不是测量得到的Nikon滤波或离焦标定。

除声明的曲线和系数字段外，原文件字节、ENDM及固件成员全部保持。独立实验通过已有参数窗口132C0000h的preboot loader加载新输入；CPU运行后没有写原厂软件对象、寄存器、ready或发送完成事件。MAIN仍来自已有显式场景接口，实际数值／DMA成功后设备才发事件96。

```powershell
$prior=Get-Content -Raw analysis/z62-capture-group-r93/original-1/result.json | ConvertFrom-Json
$source=Join-Path $prior.session 'parameters/group17.bin'
python -X utf8 -B tools/create_z62_group_parameter_input.py --source $source --output .runtime/fixtures/group17-reference-new.bin --contract analysis/z62-group-parameter-origin-r94/resource-contract-1/result.json --mode reference
python -X utf8 -B tools/probe_z62_group_parameter_dma.py --card .runtime/migrated/c-runtime/fixtures/card-r22-4096.raw --group23 .runtime/migrated/c-runtime/fixtures/group23.bin --fixture .runtime/fixtures/group17-reference-new.bin --output analysis/my-group-reference --duration 8 --wall-limit 300
```

需要既有父构建、合法C1.70和专用卡镜像，TEMP／TMP设在工作目录内，输出用新路径。命令中的baseline必须是该基线生成器的原始group17，不能用真实标定或任意参数替代。

## 当前通过范围

原厂8.009客体秒窗口在C参考输入下完成13次group工作和13次CPU事件96 ACK。保留4组实际DMA、总256字节；其中216个已分类字节与独立运算一致。原厂窗口没有另行验证未分类字节发布前后的保持，相关证据来自r93原生测试。

硬件时钟资格只等原始寄存器的频率变为非零，不替代频率、时间或成功值。HMP一致读取会短暂停机，因此这些窗口不作真实时序、AF性能或完整功能验收。710项宿主回归通过；未重跑RawPy/LibRaw。

LCD仍全黑，preview=0，ready_join／input_inhibit最终仍为1。后续需跟踪实际AND等待CALL／RETURN与帧对象来源，再实现四槽／readout／ISP交付；不能把已完成group数据等同于整机就绪或安全刷机。
