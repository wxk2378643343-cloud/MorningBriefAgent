Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
ProjectRoot = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = ProjectRoot
cmd = "pythonw.exe -m server.feishu_bot_server"
WshShell.Run cmd, 0, False
