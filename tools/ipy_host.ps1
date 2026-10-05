param([string]$Py, [string]$Arg = "", [string]$Runtime = "netfx")
# Runs a Python file in pyRevit's own IronPython 2.7.12 engine, outside Revit (for tests):
#   powershell -STA -ExecutionPolicy Bypass -File tools\ipy_host.ps1 -Py tests\ipy_number_wpf.py [-Arg before]
# netfx   = the .NET Framework engine (run with Windows PowerShell 5.1, as above).
# netcore = the Revit 2025+ engine (run with pwsh). pwsh 7.6 is .NET 10, where IronPython 2.7 cannot subclass a
#           WPF Window, so there only the imports can be checked; Revit 2026 itself runs .NET 8.
# The script gets ENGINE_DIR, ARG and REPO (this repository's folder).
$eng = "C:\Program Files\pyRevit-Master\bin\$Runtime\engines\IPY2712PR"
foreach ($d in 'pyRevitLabs.Microsoft.Scripting.dll', 'pyRevitLabs.Microsoft.Dynamic.dll',
               'pyRevitLabs.IronPython.dll', 'pyRevitLabs.IronPython.Modules.dll') {
    [Reflection.Assembly]::LoadFrom((Join-Path $eng $d)) | Out-Null
}
"host: {0} engine, .NET {1}, thread {2}" -f $Runtime, [Environment]::Version, [Threading.Thread]::CurrentThread.GetApartmentState()
$engine = [IronPython.Hosting.Python]::CreateEngine()
$scope = $engine.CreateScope()
$scope.SetVariable("ENGINE_DIR", $eng)
$scope.SetVariable("ARG", $Arg)
$scope.SetVariable("REPO", (Split-Path $PSScriptRoot -Parent))
try {
    $engine.ExecuteFile((Resolve-Path $Py).Path, $scope) | Out-Null
} catch {
    $ex = $_.Exception
    while ($ex.InnerException) { $ex = $ex.InnerException }
    "PYERROR: " + $ex.GetType().Name + ": " + $ex.Message
}
