---
name: package-release
description: 把当前代码重新打成 exe、压缩包和安装程序，产出可双击运行的交付物。Use this when 用户说"打包"、"出安装包"、"发版"、"生成 exe"。
---

## 什么时候用

改完代码要重新生成 `dist/` 与安装包时。顺序不能乱：先打 exe，再压缩，最后做安装程序。

## 步骤

1. 先确认没有旧进程占着文件（打包会失败）：

   ```
   Get-Process MiniCursor -ErrorAction SilentlyContinue | Stop-Process -Force
   ```

2. 打 exe（spec 已经有 datas / hiddenimports，不要手改）：

   ```
   .venv\Scripts\pyinstaller.exe --noconfirm desktop-agent.spec
   ```

3. 验证 exe 能起、工具齐全（不要跳过，这一步是「打出来但不能用」的唯一防线）：

   ```
   .venv\Scripts\python.exe scripts/selftest.py
   ```

4. 压缩免安装版（注意是 `dist\MiniCursor\*`，少一层目录会多套一层文件夹）：

   ```
   Compress-Archive -Path "dist\MiniCursor\*" -DestinationPath "dist\MiniCursor_1.0.0_Windows_x64.zip" -Force
   ```

5. 出安装程序：

   ```
   & "C:\Users\Lenovo\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer\install.iss
   ```

6. 报告三件产物的路径 + 体积，并说明「双击 Setup.exe 安装」。

## 不要做什么

- 不要手动删 `build/` 里的中间产物来「清理」，会让下次打包变慢且可能缺文件。
- 不要在 `dist\MiniCursor\` 里直接改代码：下次打包会被覆盖，改源码。
- 不要忘记先杀旧进程 —— 报 `PermissionError: [WinError 5]` 就是它。
- 不要用 `python app.py` 代替 exe 验证。

## 怎么算做完了

- `dist/MiniCursor/MiniCursor.exe`、`dist/*.zip`、`installer/*_Setup.exe` 三个文件都存在且时间戳是刚才；
- 自检 13/13 通过。
