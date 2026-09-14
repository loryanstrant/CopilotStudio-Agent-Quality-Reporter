/** Shared first-run setup content — imported by both SetupWizard (Settings) and
 *  SetupGuidePage (/help) so the two can never drift apart. */

export const APP_DISPLAY_NAME = "Copilot Studio Agent Quality Reporter";
// Microsoft Graph PowerShell: creates the app registration, (optionally) adds
// Directory.Read.All + grants admin consent, creates a client secret, and prints
// the Tenant ID, Client ID, and secret. Permission GUIDs are resolved by name at
// runtime so nothing is hard-coded or can drift.
export const ENTRA_SCRIPT = `# Microsoft Graph PowerShell. Requires Global Administrator (or Application
# Administrator + rights to grant admin consent).
Install-Module Microsoft.Graph -Scope CurrentUser -Force   # first time only
Connect-MgGraph -Scopes "Application.ReadWrite.All","AppRoleAssignment.ReadWrite.All"

$graphSp = Get-MgServicePrincipal -Filter "appId eq '00000003-0000-0000-c000-000000000000'"
# Directory.Read.All is ONLY needed if you gate the dashboard by an Entra group.
# Dataverse read access is granted separately in Part B (application user).
$needed  = "Directory.Read.All"
$roles   = $graphSp.AppRoles | Where-Object { $needed -contains $_.Value }

$app = New-MgApplication -DisplayName "Copilot Studio Agent Quality Reporter" -RequiredResourceAccess @{
  ResourceAppId  = "00000003-0000-0000-c000-000000000000"
  ResourceAccess = @($roles | ForEach-Object { @{ Id = $_.Id; Type = "Role" } })
}
$sp = New-MgServicePrincipal -AppId $app.AppId

# Grant admin consent for the application permission(s)
foreach ($r in $roles) {
  New-MgServicePrincipalAppRoleAssignment -ServicePrincipalId $sp.Id \`
    -PrincipalId $sp.Id -ResourceId $graphSp.Id -AppRoleId $r.Id | Out-Null
}

$secret = Add-MgApplicationPassword -ApplicationId $app.Id \`
  -PasswordCredential @{ DisplayName = "aqp"; EndDateTime = (Get-Date).AddYears(1) }

Write-Host "Tenant ID:     $((Get-MgContext).TenantId)"
Write-Host "Client ID:     $($app.AppId)"
Write-Host "Client secret: $($secret.SecretText)"
# Next: run Part B to register this app as an application user per environment.`;

// One-shot PAC CLI command: creates the Entra app registration AND registers it
// as an application user in the target environment, then prints the IDs + secret.
export const PAC_SCRIPT = `# Power Platform CLI (pac). Install: https://aka.ms/PowerPlatformCLI
# Run once per environment you want to scan. Requires Power Platform admin rights.
pac auth create
pac admin list                 # copy the Environment ID you want to scan

pac admin create-service-principal \\
  --environment <ENVIRONMENT-ID> \\
  --role "System Administrator"

# Prints: Application (client) ID, Tenant ID, and Client secret.
# 'System Administrator' is convenient for a lab; scope to a least-privilege
# custom role (read on the tables listed above) for production.`;

export const DATAVERSE_TABLES = [
  "Bot",
  "Bot Component",
  "Connection Reference",
  "Environment Variable Definition",
  "Solution",
];