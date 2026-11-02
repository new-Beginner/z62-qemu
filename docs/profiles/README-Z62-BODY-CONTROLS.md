# Z6II 机身按键实验入口 r19

新增 9 个普通按键，沿用 r13 内核、r16 无镜头和双段快门配置。**这是机身输入的增量实现，完整机身、触屏、镜头和拍照保存尚未完成。** 默认 `start-z6ii-qemu.cmd` 保持原配置。

## 启动

双击 `start-z6ii-body-controls.cmd`，打开 <http://127.0.0.1:8676>。
测试自己的 C1.70 布局修改包：

```bat
start-z6ii-body-controls.cmd --firmware "Z6_2_0170 (1).bin"
```

候选限制沿用 [候选固件说明](README-FIRMWARE-TEST.md)：只执行 master、slave、controller；其他两个成员不执行，候选健康未知。界面“关闭模拟器”正常退出本次会话。

## 新增按键

| 按键 | 快捷键 | Z6II 扩展输入 | 当前证据 |
|---|---|---:|---|
| 播放 | P | 8 | 原厂 PLAY 位、APPPLAY、无卡提示、半按返回和连续预览已验证；照片回放未验证 |
| 删除 | Delete | 23 | 原版／候选电平按下与释放通过；删除照片未验证 |
| 连拍／自拍 | R | 1 | 电平通过；释放模式选择功能未验证 |
| i | I | 2 | 电平通过；本次浏览器观察未显示 i 菜单，仍待追踪 |
| ISO | O | 19 | 电平通过；组合拨轮未接入 |
| 曝光补偿 | E | 18 | 电平通过；组合拨轮未接入 |
| DISP | D | 10 | 电平通过；显示布局切换未验收 |
| 放大 | +（主键盘等号键） | 22 | 电平通过；取景及回放缩放未验收 |
| 缩小 | − | 21 | 电平通过；缩略图及缩放未验收 |

MENU、OK、四方向、X 半按、S 全按沿用原入口。按键使用原队列、去抖时长和释放机制，支持鼠标及键盘；拍照结果仍未完成。

ISO、放大、缩小、删除的编号与参考 Z72 页面不同。新的映射取自 Z6II C1.70 原厂输入表。固件中的内部名称是逻辑动作，不意味着机身上存在该名称表中的所有按钮。

## 复核

```bat
python -X utf8 -B tools\verify_z62_body_controls.py
python -X utf8 -B -m unittest discover -s tests -p test_z62_body_controls.py -v
```

`/status` 的 `body_controls` 记录适配器身份和按键表；运行时 `electrical_input` 回读真实扩展器输入电平。该字段不推断固件功能成功。各新键的 `functional_acceptance=pending` 是保守标记；播放的有限验收由独立证据复核器报告。

实验过程与后续入口见 [r19 报告](../history/2026-10-30_实施-Z62机身按键映射与控制台r19-report.md)。
