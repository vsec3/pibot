param(
    [string]$Message = "Describe what you changed"
)

Write-Host "Checking repo status..."
git status

Write-Host "`nStaging files..."
git add .

Write-Host "`nCommitting..."
git commit -m "$Message"

Write-Host "`nPulling latest changes (rebase)..."
git pull origin main --rebase

Write-Host "`nPushing to GitHub..."
git push origin main

if ($LASTEXITCODE -ne 0) {
    Write-Host "`nPush failed, trying force push..."
    git push origin main --force
}
