param(
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroup,

    [Parameter(Mandatory = $true)]
    [string]$Location,

    [Parameter(Mandatory = $true)]
    [string]$AcrName,

    [Parameter(Mandatory = $true)]
    [string]$ContainerEnvName,

    [Parameter(Mandatory = $true)]
    [string]$ContainerAppName,

    [Parameter(Mandatory = $true)]
    [string]$ApiFootballKey,

    [Parameter(Mandatory = $true)]
    [string]$TelegramBotToken
)

$ErrorActionPreference = "Stop"

Write-Host "Creating resource group..."
az group create --name $ResourceGroup --location $Location | Out-Null

Write-Host "Creating Azure Container Registry..."
az acr create --resource-group $ResourceGroup --name $AcrName --sku Basic --admin-enabled true | Out-Null

Write-Host "Creating Container Apps environment..."
az containerapp env create --name $ContainerEnvName --resource-group $ResourceGroup --location $Location | Out-Null

$acrLoginServer = az acr show --name $AcrName --resource-group $ResourceGroup --query loginServer -o tsv
$acrUser = az acr credential show --name $AcrName --resource-group $ResourceGroup --query username -o tsv
$acrPass = az acr credential show --name $AcrName --resource-group $ResourceGroup --query passwords[0].value -o tsv

Write-Host "Building first image in ACR..."
az acr build --registry $AcrName --image bet-telegram-bot:initial . | Out-Null

$image = "$acrLoginServer/bet-telegram-bot:initial"

Write-Host "Creating Container App..."
az containerapp create `
  --name $ContainerAppName `
  --resource-group $ResourceGroup `
  --environment $ContainerEnvName `
  --image $image `
  --registry-server $acrLoginServer `
  --registry-username $acrUser `
  --registry-password $acrPass `
  --secrets api-football-key=$ApiFootballKey telegram-bot-token=$TelegramBotToken `
  --env-vars API_FOOTBALL_KEY=secretref:api-football-key TELEGRAM_BOT_TOKEN=secretref:telegram-bot-token `
  --min-replicas 1 `
  --max-replicas 1 | Out-Null

Write-Host "Done."
Write-Host "ACR login server: $acrLoginServer"
Write-Host "Container app name: $ContainerAppName"
