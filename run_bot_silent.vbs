Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
ProjectRoot = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = ProjectRoot
cmd = "pythonw.exe " & Chr(34) & FSO.BuildPath(ProjectRoot, "server\feishu_bot_server.py") & Chr(34)
WshShell.Run cmd, 0, False
