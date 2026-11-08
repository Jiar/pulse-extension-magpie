# 可选的 Pulse 滚动修复与扩展图标支持

Python 扩展通过 Pulse 的公开扩展协议提供数据，无需重新编译 Pulse 即可读取用量。卡片布局和图标显示由原生应用控制；下面两项能力需要相应的 Pulse 构建。额度很多时，使用扩展的 `configure.py --details` 可直接查看全部详情。

## 卡片滚动修复

这里附带一个独立的通用原生修复，供希望自行构建 Pulse 的开发者使用：

- 固定账号标题与当前圆环选中的额度，其余明细在列表中滚动。
- 卡片最多占所属屏幕可用高度的 75%；空间不足时进一步缩短。
- 保持箭头尖端对齐圆环，处理侧边 Dock 和屏幕边缘的放置。
- 打开、切换和滚动卡片时不改变面板窗口大小；极窄空间下使用整卡滚动。

### 源码与补丁

- Fork：[Jiar/Pulse 的 fix/detail-card-overflow 分支](https://github.com/Jiar/Pulse/tree/fix/detail-card-overflow)。
- 固定提交：[cae542ec79748e752f9d5eb0b7487556b0413495](https://github.com/Jiar/Pulse/commit/cae542ec79748e752f9d5eb0b7487556b0413495)。
- 基线提交：`32075864aee68d7310672a1544c30df8f96405b9`（Pulse 1.12.7）。
- [detail-card-overflow.patch](detail-card-overflow.patch) 包含 11 个源码、测试和文档文件的通用改动。

补丁没有 Magpie 品牌、专用平均算法或账号信息。平均用量始终由 Python 扩展计算，再通过 Pulse 的 **Ring shows** 选择。

在单独的 Pulse checkout 中，先确认所用基线兼容：

```bash
git apply --check /path/to/pulse-extension-magpie/native-pulse/detail-card-overflow.patch
```

再应用补丁：

```bash
git apply /path/to/pulse-extension-magpie/native-pulse/detail-card-overflow.patch
```

也可以直接检出固定提交。构建与打包按 Pulse 自身的 README 和开发说明执行，需要完整 Xcode；保留所有 SwiftUI 预览并运行原生测试与本地化检查。这里不提供自动替换、退出或重启已安装应用的脚本。

### 验证范围

该固定提交在发布前使用 Xcode 27.2 完成无警告构建、2,156 项测试（262 个测试组）和本地化检查。测试包含视口预算、屏幕边缘与侧边 Dock 的放置、箭头路径和托管 SwiftUI 布局。

托管组件捕获与程序化滚动不能证明真实非 key 面板的滚轮或触控板输入。自行构建后仍应在自己的显示器、Dock 布局和输入设备上检查交互。

## 扩展图标支持

[Jiar/Pulse 的 feat/extension-icons 分支](https://github.com/Jiar/Pulse/tree/feat/extension-icons) 在上述滚动修复基础上，增加 schemaVersion 1 清单的可选 `icon` 字段。它是所有扩展通用的能力，不在 Pulse 内硬编码 Magpie 名称或图标。字段格式、路径与图片大小限制见该分支的 [Docs/extensions.md](https://github.com/Jiar/Pulse/blob/feat/extension-icons/Docs/extensions.md#optional-icon)。

扩展安装目录现在包含 `magpie-icon.png`，清单声明 `"icon": "magpie-icon.png"`。Pulse 从该扩展目录读取 PNG，在圆环、用量卡片标题、设置列表和菜单中按原色显示。无效或缺失图标回退为通用拼图图标，不影响用量。更换图片后执行 **Look again** 即可更新；选择机器人时圆环仍优先显示机器人。

**此前发布的 [custom-1.12.7-scroll.1](https://github.com/Jiar/Pulse/releases/tag/custom-1.12.7-scroll.1) 和这里附带的滚动补丁不包含图标支持。** 要在新电脑显示 Magpie 图标，需要使用 `feat/extension-icons` 的 Pulse 构建，并重新运行本扩展安装器。仅更新扩展、重新扫描或重启旧版 Pulse 不会添加原生图标能力。

源码构建方法见 Pulse 的 [Docs/build-from-source.md](https://github.com/Jiar/Pulse/blob/feat/extension-icons/Docs/build-from-source.md)。源码构建的应用不等同于官方签名和公证发行版；官方更新可能覆盖这些改动。

## 许可

Pulse：Copyright 2026 qunqin24，Apache License 2.0。许可证副本见 [LICENSE-Pulse.txt](LICENSE-Pulse.txt)。本项目对附带补丁的修改为 Copyright 2026 Jiar and contributors，同样采用 Apache-2.0；变更范围在补丁与对应提交中记录。

本目录不分发 Pulse 应用或图标。扩展根目录的 Magpie 图标用于标识集成，其第三方权利说明见 [NOTICE](../NOTICE)。名称用于说明兼容性，不表示上游认可或支持该集成。
