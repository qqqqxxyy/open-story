param(
    [ValidateSet('open', 'generate', 'sync', 'test', 'typecheck')]
    [string]$Action = 'open',
    [string]$StoryId,
    [string]$DataRoot
)
$ErrorActionPreference = 'Stop'
$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
if ($nodeCommand) { $nodeExecutable = $nodeCommand.Source }
else {
    $nodeExecutable = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
    if (-not (Test-Path -LiteralPath $nodeExecutable)) { throw '请先安装 Node.js 22.18+ 或 24+，并添加到 PATH。' }
}
Push-Location -LiteralPath $PSScriptRoot
try {
    switch ($Action) {
        'open' { & $nodeExecutable 'scripts/generate.ts' '--open' }
        'generate' { & $nodeExecutable 'scripts/generate.ts' }
        'sync' {
            if (-not $StoryId) { throw '同步需要 -StoryId 参数。' }
            $syncArgs = @('scripts/sync-story.ts', $StoryId)
            if ($DataRoot) { $syncArgs += @('--data-root', $DataRoot) }
            & $nodeExecutable @syncArgs
        }
        'test' { & $nodeExecutable '--test' 'tests/*.test.ts' }
        'typecheck' { & $nodeExecutable 'node_modules/typescript/bin/tsc' '--noEmit' }
    }
    if ($LASTEXITCODE -ne 0) { throw "命令执行失败，退出码 $LASTEXITCODE" }
} finally { Pop-Location }
