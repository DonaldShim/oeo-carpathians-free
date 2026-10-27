# C-Lab OAuth V11 dedicated rollback. DEFAULT READ-ONLY. Never touches production.
param([switch]$Execute)
$ErrorActionPreference='Stop'
$P='project-4e9f56f4-a524-4759-91f'
$Region='europe-west1'
$ServiceName='c-lab-oauth-v11-test'
$ExpectedSA='clab-oauth-v11-test@project-4e9f56f4-a524-4759-91f.iam.gserviceaccount.com'
$ExpectedImage='ghcr.io/donaldshim/clab-oauth-v11-synthetic@sha256:a2e28d9c746073b9455c0a75e03bcf2892f3b0bf8339d5990759da27121b9d64'
$Production='c-lab-gcp-control'
$ExpectedProdRevision='c-lab-gcp-control-custody-v1-prod-20261020'
$Root=Join-Path $env:USERPROFILE 'Documents\C_LAB_V11_AUDIT_20261027'
$Receipt=Join-Path $Root 'ROLLBACK_V11_READBACK.json'
$status=[ordered]@{utc=(Get-Date).ToUniversalTime().ToString('o');scope='ONLY_NEW_TEST_SERVICE';execute_requested=[bool]$Execute;delete_performed=$false;state='OPEN'}
function RunG {param([string[]]$Argv);$ErrorActionPreference='Continue';$r=& gcloud.cmd @Argv 2>&1;if($LASTEXITCODE -ne 0){throw (($r|Out-String).Substring(0,[math]::Min(400,($r|Out-String).Length)))};return ($r|Out-String)}
function J {param([string[]]$Argv);return (RunG (@($Argv)+'--format=json')|ConvertFrom-Json)}
try {
  $curProj=(RunG @('config','get-value','project')).Trim()
  if($curProj -ne $P){throw 'WRONG_GCLOUD_PROJECT'}
  $prod=J @('run','services','describe',$Production,"--project=$P","--region=$Region")
  if($prod.status.latestReadyRevisionName -ne $ExpectedProdRevision){throw 'PRODUCTION_REVISION_DRIFT'}
  $svc=J @('run','services','describe',$ServiceName,"--project=$P","--region=$Region")
  if($svc.metadata.name -ne $ServiceName){throw 'TEST_NAME_MISMATCH'}
  if($svc.spec.template.spec.serviceAccountName -ne $ExpectedSA){throw 'TEST_SERVICE_ACCOUNT_MISMATCH'}
  if(@($svc.spec.template.spec.containers).Count -ne 1 -or $svc.spec.template.spec.containers[0].image -ne $ExpectedImage){throw 'TEST_IMAGE_MISMATCH'}
  $status.test_revision=$svc.status.latestReadyRevisionName
  $status.production_revision=$prod.status.latestReadyRevisionName
  $status.state='ROLLBACK_PREPARED'
  if($Execute){
    $response=RunG @('run','services','delete',$ServiceName,"--project=$P","--region=$Region",'--quiet')
    $status.delete_performed=$true
    $ls=J @('run','services','list',"--project=$P","--region=$Region")
    if(@($ls|Where-Object{$_.metadata.name -eq $ServiceName}).Count -ne 0){throw 'DELETE_NOT_CONFIRMED'}
    $after=J @('run','services','describe',$Production,"--project=$P","--region=$Region")
    if($after.status.latestReadyRevisionName -ne $ExpectedProdRevision){throw 'PROD_REVISION_DRIFT_AFTER_DELETE'}
    $status.state='TEST_SERVICE_DELETED_PRODUCTION_PRESERVED'
  }
} catch {
  $status.state='STOP_OR_PARTIAL'
  $status.error=$_.Exception.Message
} finally {
  $status.completed_utc=(Get-Date).ToUniversalTime().ToString('o')
  $status|ConvertTo-Json -Depth 12|Set-Content -Path $Receipt -Encoding UTF8
  Write-Output ('ROLLBACK_GATE='+$status.state+' EXECUTE='+[bool]$Execute+' DELETED='+$status.delete_performed)
  Write-Output ('RECEIPT='+$Receipt)
}
