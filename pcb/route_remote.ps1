$ErrorActionPreference = 'Stop'
$routingTools = Join-Path $env:TEMP 'revgen-routing'
$javaRuntime = Get-ChildItem (Join-Path $routingTools 'java') -Filter java.exe -Recurse | Select-Object -First 1 -ExpandProperty FullName
if (-not $javaRuntime) { throw 'Portable Java runtime not found in the routing tools directory.' }
$pcbRoot = Join-Path $PSScriptRoot 'remote'
& $javaRuntime '-Djava.awt.headless=true' '-Xmx2g' '-jar' (Join-Path $routingTools 'freerouting.jar') '--gui.enabled=false' '--router.max_passes=40' '--router.max_threads=2' '--usage_and_diagnostic_data.disable_analytics=true' '-da' '-de' (Join-Path $pcbRoot 'artifacts/placement.dsn') '-do' (Join-Path $pcbRoot 'artifacts/routed.ses') '-mp' '40' '-mt' '2' '-oit' '1'
if ($LASTEXITCODE -ne 0) { throw "Freerouting failed: $LASTEXITCODE" }
