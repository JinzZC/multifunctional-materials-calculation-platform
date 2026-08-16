# 多功能计算平台 — 项目指南（Claude 会话自动加载）

面向材料测试的 Windows 桌面计算平台（Python 3.14 + PySide6 6.11，中文界面），v0.2.0。

## ⚠️ 环境铁律

- **一切 Python 命令用 `py -3`**（PATH 中 `python` 被 Windows 商店存根遮蔽，静默失败）
- 数据库：`%LOCALAPPDATA%\FiberTensile\fiber_tensile.db`（环境变量 `FT_DB_PATH` 可覆盖，测试/验证用临时库）
- 验证/测试脚本**严禁触碰真实数据库**（历史教训：曾误删用户数据）

## 常用命令

```bat
py -3 main.py                                    :: 运行（源码）
py -3 -m pytest tests/                           :: 154 个单元测试
py -3 scripts/smoke_ui.py                        :: UI 冒烟（自动全流程，临时库+临时QSettings）
py -3 scripts/build.py                           :: 一键双打包（中文名 EXE；build.bat 是其 ASCII 包装）
powershell -NoProfile -File scripts/verify_exe.ps1  :: 验证打包 EXE（自动发现 dist 下文件夹版）
:: 分享包 zip：py -3 -c "import shutil; shutil.make_archive('dist/多功能计算平台-分享包','zip','dist/多功能计算平台')"
```

打包产物：`dist\多功能计算平台\多功能计算平台.exe`（文件夹版，启动快，推荐）+ `dist\多功能计算平台单文件版.exe`（便携）。**用户开着软件时无法打包**（文件锁），需先请其关闭。

## 架构

```
fiber_tensile/
├── config.py            应用名/版本/数值范围/sanitize_filename/matplotlib 中文配置
├── core/                纯计算层（仅 numpy+标准库，禁 Qt/pandas/sqlite）
│   ├── modes.py         ★ 计算模式注册表（ModeSpec：标签/单位/维度字段/公式）——加新模式的单一入口
│   ├── formulas.py      σ=4F/πd²（锚点 2598.45 MPa）、纺织强度、σ=强度×ρ×100
│   ├── statistics.py    ddof=1、CV%
│   └── weibull.py       median rank (i-0.5)/N + 最小二乘，m=斜率、σ₀=exp(−a/m)
├── data/db.py           ★ 迁移机制 MIGRATIONS 列表（只增不改）：v1 纤维、v2 表面能(内置8液体)、v3 曲线+复材
├── fileio/              纤维导入/模板/报告；parse_decimal_text（欧式小数逗号兼容）
├── surface_energy/      接触角模块：core(METHODS 注册表：OWRK lstsq/Wu Gauss-Newton+Fowkes/Zisman)、液体库、导入、报告、UI
├── curve_analysis/      单丝曲线：平台校正 x₀=−b/k、E=k·标距/面积、断裂点取峰值平台终点
├── composites/          复材模块：混合法则(E₂为反混合法则)、酸解法按 ASTM D3171（真实 V_f=ρ_c·w_f/ρ_f）
└── ui/                  主窗口（左侧导航 3 模块 + 纤维模块 4 子页签）、richtext.py（公式富文本/真上下标/分数/HtmlHeaderView）、csv_export、prefs(QSettings)
```

- 公式显示约定：符号记法（γ_S^d、⟨分子|分母⟩）经 `ui/richtext.py` 的 `to_rich`/`equation_line_html` 渲染为真上下标/分数；中文仅作独立符号说明，不混入公式
- 重库（pandas/openpyxl/reportlab/matplotlib）全部函数内延迟导入，保持启动快
- 数据库结果缓存列由 repository 写入，UI 展示读缓存；导出时按输入重算
- 冒烟脚本直接操作 `tab._xxx` 私有控件，改名时要同步更新

## 当前状态（2026-08-16）

- 三模块全部完成；**全部公式经 3 个独立 agent 以不同方法验证正确（≤1e-15）**，计算过程文本逐数字审计通过
- 154 测试 + 冒烟全绿；git 提交历史完整（`git log` 可回溯所有决策）
- 功能：手动+批量导入(Excel/CSV/TXT/曲线)、统计/Weibull/四方法表面能/混合法则/体积分数、Excel/PDF/CSV 导出、历史管理、批次对比、Zisman/Weibull/曲线图

## 下一步候选（按之前规划）

1. **EMI 电磁屏蔽模块**（第三个功能域）：迁移 v4 建表 + `fiber_tensile/emi/` 包 + 导航项，照 surface_energy 模式
2. 纤维模块加 IFSS 界面剪切强度、单丝模量已做（曲线分析）
3. 可选：common/ 目录重构（多域时再做）、pytest-qt

## 易错点备忘

- HtmlHeaderView 不能调基类 sizeHint/sectionSizeFromContents（无限递归）；paintSection 先 setClipRect 再 translate
- PyInstaller 中文名：走 build.py；.bat/.ps1 保持纯 ASCII
- 迁移 v3 尚未发布可改；已应用的版本绝不修改
- 冒烟/测试隔离：QSettings 指向临时 ini、数据库用 temp 文件
