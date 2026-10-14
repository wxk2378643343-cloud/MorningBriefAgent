Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
ScriptsDir = FSO.GetParentFolderName(WScript.ScriptFullName)
ProjectRoot = FSO.GetParentFolderName(ScriptsDir)
WshShell.Run "wscript.exe " & Chr(34) & FSO.BuildPath(ProjectRoot, "run_bot_silent.vbs") & Chr(34), 0, False
