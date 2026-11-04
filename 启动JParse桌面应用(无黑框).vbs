' JParse Windows 无黑框静默启动器
Set ws = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)
batPath = """" & currentDir & "\启动JParse桌面应用.bat"""
ws.Run batPath, 0, False
