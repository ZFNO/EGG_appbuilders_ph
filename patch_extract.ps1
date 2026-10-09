$p = 'Z:\__repo\EGG_appbuildersph\webcode\mobile\src\extract.js'
$s = [IO.File]::ReadAllText($p)
$a = "env.localModelPath = './models/';"
$b = "env.localModelPath = new URL('models/', document.baseURI).href;"
$c = "env.backends.onnx.wasm.wasmPaths = './ort/';"
$d = "env.backends.onnx.wasm.wasmPaths = new URL('ort/', document.baseURI).href;"
if (-not $s.Contains($a)) { Write-Host "ERR: anchor A not found"; exit 1 }
if (-not $s.Contains($c)) { Write-Host "ERR: anchor C not found"; exit 1 }
$s = $s.Replace($a, $b).Replace($c, $d)
[IO.File]::WriteAllText($p, $s)
Write-Host "patched OK"
Select-String -Path $p -Pattern 'localModelPath|wasmPaths' | ForEach-Object { $_.Line.Trim() }
