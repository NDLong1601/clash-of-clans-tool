' Double-click this file to start CocMagic without opening a console window.
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
appDir = files.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = appDir

command = "pythonw.exe " & Chr(34) & files.BuildPath(appDir, "gui.py") & Chr(34)
For Each argument In WScript.Arguments
    command = command & " " & Chr(34) & Replace(argument, Chr(34), Chr(34) & Chr(34)) & Chr(34)
Next
shell.Run command, 0, False
