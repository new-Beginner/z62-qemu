# Z6II AF-ON、Fn、录像键与独立摇杆

这个入口包含此前普通按键和主副拨轮，并新增 **AF-ON、Fn1、Fn2、录像键、独立摇杆八方向及中央按压**。原厂输入报文和原版／候选HTTP路径已验证；这不等于对焦、录像保存或全部自定义功能已经完成。

## 启动

运行 `start-z6ii-extra-controls.cmd`，打开 <http://127.0.0.1:8678>。

| 操作 | 方法 |
|---|---|
| AF-ON | 按住界面按钮或键盘A |
| Fn1、Fn2 | 界面按钮或键盘F、G |
| 录像键 | 界面按钮或键盘V；视频编码与保存未完成 |
| 独立对焦摇杆 | 按住九宫格中的方向或中央按钮，松开回中 |
| 释放全部 | Esc或界面“释放全部按键” |

摇杆与原来的上下左右多重选择器是独立硬件输入。短点击保持至少150ms相机内时间；网页失焦和停止会释放输入，心跳超时也会释放持续按压。

当前无镜头，自动对焦、光圈及Fn自定义效果还需对应功能验收。新按钮通过控制器GPIO和输入扩展器进入原固件，宿主不直接写菜单、对焦点或曝光参数。

## 当前版本范围

这个按键入口仍使用r13内核及原有近似预览。独立r21内核已增加运行时ADC，完成24组原生采样测试及旧ADC回归；模式盘八挡原厂显示与切换正在独立验证，暂未并入本入口。照片／视频拨杆、电源拨杆、触屏、肩屏和镜头协议仍未完成。

自己的候选包继续使用 `--firmware`，例如：

```bat
start-z6ii-extra-controls.cmd --firmware "Z6_2_0170 (1).bin"
```

仅支持C1.70固定布局，候选健康未知；详见 [候选限制](README-FIRMWARE-TEST.md)。模拟通过不构成真机刷写安全结论。

## 稳定运行目录

新入口默认把ASCII暂存会话放在用户目录下的 `Documents/Z62-QEMU-runtime/sessions`，不再依赖系统Temp。可用进程环境变量 `Z62_RUNTIME_ROOT` 指定其他ASCII目录，或沿用已有 `PI_SCRATCH_DIR`。这不会改变系统全局环境变量。

本轮已有临时工具和实验镜像消失的情况，原因未确认。新的512MiB实验卡、合成NOR23与Ghidra独立记录在稳定目录的 `fixtures/r21-runtime.json`，不冒充旧4GiB镜像。

## 复核

```bat
python -X utf8 -B tools\verify_z62_extra_inputs.py
python -X utf8 -B -m unittest discover -s tests -p test_z62_extra_inputs.py -v
```

完整目标与正在运行的模式盘观察见 [工作计划](../GOAL-Z62-QEMU.md)。
