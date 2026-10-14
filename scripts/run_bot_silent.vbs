Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
ScriptsDir = FSO.GetParentFolderName(WScript.ScriptFullName)
ProjectRoot = FSO.GetParentFolderName(ScriptsDir)
WshShell.CurrentDirectory = ProjectRoot
cmd = "pythonw.exe " & Chr(34) & FSO.BuildPath(ProjectRoot, "server\feishu_bot_server.py") & Chr(34)
WshShell.Run cmd, 0, False
