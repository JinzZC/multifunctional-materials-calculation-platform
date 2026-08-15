@echo off
REM 一键打包脚本：生成两种发布形态
REM   1) dist\FiberTensileAnalyzer\           文件夹版（启动快，推荐日常使用与分享：整个文件夹打包成 zip 即可）
REM   2) dist\FiberTensileAnalyzerOneFile.exe 单文件版（一个 exe 分享方便，但每次启动需自解压、稍慢）
REM 注意：本机 PATH 中 python 被 Windows 商店存根遮蔽，必须用 py 启动器
cd /d "%~dp0.."
echo [1/3] 安装打包依赖...
py -3 -m pip install -r requirements-dev.txt
echo [2/3] 打包文件夹版（约 2-5 分钟）...
py -3 -m PyInstaller --noconfirm --clean --windowed ^
    --name FiberTensileAnalyzer ^
    --hidden-import matplotlib.backends.backend_qtagg ^
    --exclude-module tkinter ^
    --exclude-module PySide6.QtWebEngineWidgets ^
    main.py
echo [3/3] 打包单文件版（约 2-5 分钟）...
py -3 -m PyInstaller --noconfirm --clean --windowed --onefile ^
    --name FiberTensileAnalyzerOneFile ^
    --hidden-import matplotlib.backends.backend_qtagg ^
    --exclude-module tkinter ^
    --exclude-module PySide6.QtWebEngineWidgets ^
    main.py
echo.
echo 打包完成：
echo   文件夹版：dist\FiberTensileAnalyzer\FiberTensileAnalyzer.exe（启动快）
echo   单文件版：dist\FiberTensileAnalyzerOneFile.exe（便携单文件）
pause
