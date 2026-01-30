param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$env:GIT_SSH_COMMAND = "C:/Windows/System32/OpenSSH/ssh.exe -p 443"

if (-not $Args -or $Args.Count -eq 0) {
    Write-Host "Usage: .\\scripts\\git_ssh_443.ps1 <git-args>"
    Write-Host "Example: .\\scripts\\git_ssh_443.ps1 ls-remote origin"
    exit 1
}

git @Args
