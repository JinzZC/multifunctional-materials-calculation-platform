# 开发、验证与发布

## 测试

```bat
:: 单元测试（计算/统计/Weibull/数据库/导入/报告/发布工具）
py -3 -m pip install pytest
py -3 -m pytest tests/

:: UI 冒烟测试（自动跑全流程后退出，窗口会闪现约 1 秒）
py -3 scripts/smoke_ui.py
```

单元测试在收集阶段、冒烟测试在导入应用前自动创建独立临时目录，覆盖默认数据库路径，隔离界面设置、日志与缓存。即使外部设置了 `FT_DB_PATH`，测试也会改用临时路径。测试数量与结果以实际运行输出为准。

## 打包成 EXE

```bat
:: 直接双击 scripts\build.bat（内部调用 scripts\build.py 以支持中文名），产出两种形态：
::   文件夹版  dist\多功能计算平台\多功能计算平台.exe   启动快（1-3 秒），推荐日常使用
::   单文件版  dist\多功能计算平台单文件版.exe           一个 exe 便携，但每次启动需自解压（5-10 秒）
```

程序已做启动优化：pandas/openpyxl/reportlab/matplotlib 全部按需加载（只在导入文件、导出报告、绘制图表时才加载），启动时只加载录入界面必需的组件。

双打包完成后验证两个 EXE：

```powershell
powershell -NoProfile -File scripts/verify_exe.ps1
```

该命令以 `--verify-package` 启动两个产物，验证六模块界面、合成拉伸计算、历史保存与 Excel/PDF/CSV 导出。数据库、偏好设置和缓存均放入临时目录，完成后程序自动退出。

### 发布附件准备与核验

完成双打包和 EXE 验证后运行：

```bat
py -3 scripts/release.py prepare
```

该命令从现有 `dist` 产物生成 `dist/release-v<版本号>/`，包含带版本号的英文 ZIP、便携 EXE 和 `SHA256SUMS.txt`。ZIP 内保留中文程序名；已有输出目录不会被覆盖。版本号读取自 `fiber_tensile/config.py`。准备附件不会重新构建，发布前须确认构建产物来自目标版本。

在 GitHub 创建对应标签的空附件 Release 后，使用已登录的 GitHub CLI 上传：

```bat
py -3 scripts/release.py upload
:: 上传后自动检查；也可单独重复核验
py -3 scripts/release.py verify
```

上传工具拒绝替换已有附件；核验严格检查三个附件的名称、数量、大小和 GitHub 提供的 SHA-256。若上传中断，应先检查远程已上传附件再处理；工具不会自动删除附件。现有 v0.4.1 的无版本号英文附件继续保留，这套命名规则用于后续发布。
