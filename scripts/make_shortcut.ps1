# 在桌面创建「IELTS Pod」快捷方式（自绘 app.ico；项目移动后重跑本脚本即可）。
$root = Split-Path -Parent $PSScriptRoot
$desktop = [Environment]::GetFolderPath('Desktop')
$lnk = Join-Path $desktop 'IELTS Pod.lnk'

$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($lnk)
$sc.TargetPath = Join-Path $root 'open_app.bat'
$sc.WorkingDirectory = $root
$sc.IconLocation = Join-Path $root 'app.ico,0'
$sc.Description = 'Bruce 英语播客工作台（选题-作答-母语者音频-离线收听）'
$sc.WindowStyle = 7  # 运行瞬间最小化，避免控制台闪屏
$sc.Save()

Write-Host "快捷方式已创建: $lnk"
