Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

param(
    [string]$RepoRoot = "C:\Users\hamza\CADream-Generate-Editable-CAD",
    [string]$InputDir = "sample-files",
    [int]$RasterSize = 512,
    [int]$CropCount = 64,
    [double]$MinLabelIntersection = 0.20,
    [int]$Epochs = 160,
    [int]$Batch = 8,
    [double]$LearningRate = 3e-4,
    [double]$WeightPresence = 0.15
)

Set-Location $RepoRoot

$venvActivate = Join-Path $RepoRoot "cadream\backend\.venv\Scripts\Activate.ps1"
if (!(Test-Path $venvActivate)) {
    throw "Missing virtual environment activation script: $venvActivate"
}
& $venvActivate

$runId = Get-Date -Format "yyyyMMdd_HHmmss"
$runRoot = Join-Path $RepoRoot "tmp\ml_runs\$runId"
$datasetDir = Join-Path $runRoot "dataset"
New-Item -ItemType Directory -Force -Path $runRoot | Out-Null

Write-Host "Run ID: $runId"
Write-Host "Run Root: $runRoot"

python cadream/backend/scripts/build_ml_dataset.py `
  --input_dir $InputDir `
  --out_dir $datasetDir `
  --size $RasterSize `
  --crop_count $CropCount `
  --min_label_intersection $MinLabelIntersection

$outModel = Join-Path $runRoot "model.pt"
python cadream/ml/train.py `
  --dataset_dir $datasetDir `
  --out $outModel `
  --epochs $Epochs `
  --batch $Batch `
  --lr $LearningRate `
  --weight_presence $WeightPresence

$logPath = Join-Path $runRoot "train_log.json"
if (!(Test-Path $logPath)) {
  throw "Missing train log: $logPath"
}

$json = Get-Content $logPath -Raw | ConvertFrom-Json
$last = $json.log[-1]

$currentValEquip = [double]$last.val_iou_equip
$currentValSite  = [double]$last.val_iou_site
$currentBoundary = $null
if ($null -ne $last.val_boundary_coverage_site) {
  $currentBoundary = [double]$last.val_boundary_coverage_site
}
$currentNoise = [double]$last.val_noise_ratio_site
$currentSiteContext = [double]$last.val_site_context_ratio_site
$currentComposite = [double]$last.val_composite_score
$currentSamples  = [int]$json.samples_total

Write-Host "samples_total      : $currentSamples"
Write-Host "samples_train      : $($json.samples_train)"
Write-Host "samples_val        : $($json.samples_val)"
Write-Host "val_iou_site       : $currentValSite"
Write-Host "val_iou_equip      : $currentValEquip"
Write-Host "val_boundary_site  : $currentBoundary"
Write-Host "val_site_ctx_site  : $currentSiteContext"
Write-Host "val_noise_site     : $currentNoise"
Write-Host "val_composite      : $currentComposite"
Write-Host "mean_w_site        : $($last.mean_w_site)"
Write-Host "mean_w_equip       : $($last.mean_w_equip)"
Write-Host "num_samples_seen   : $($last.num_samples_seen)"

$historyPath = Join-Path $RepoRoot "tmp\ml_runs\history.csv"
if (!(Test-Path $historyPath)) {
  "run_id,samples_total,val_iou_site,val_iou_equip,val_boundary_coverage_site,val_site_context_ratio_site,val_noise_ratio_site,val_composite_score,model_path,train_log_path" | Out-File -Encoding utf8 $historyPath
}
"$runId,$currentSamples,$currentValSite,$currentValEquip,$currentBoundary,$currentSiteContext,$currentNoise,$currentComposite,$outModel,$logPath" | Out-File -Append -Encoding utf8 $historyPath

$bestMetaPath = Join-Path $RepoRoot "tmp\ml_runs\best_metrics.json"
$deployModelPath = Join-Path $RepoRoot "cadream\ml\model.pt"

$bestScore = -1.0
if (Test-Path $bestMetaPath) {
  $bestMeta = Get-Content $bestMetaPath -Raw | ConvertFrom-Json
  $bestScore = [double]$bestMeta.val_composite_score
}

if ($currentComposite -gt $bestScore) {
  Copy-Item $outModel $deployModelPath -Force
  $newBest = [pscustomobject]@{
    run_id         = $runId
    val_composite_score = $currentComposite
    val_iou_equip  = $currentValEquip
    val_iou_site   = $currentValSite
    val_boundary_coverage_site = $currentBoundary
    val_site_context_ratio_site = $currentSiteContext
    val_noise_ratio_site = $currentNoise
    samples_total  = $currentSamples
    model_path     = $outModel
    train_log_path = $logPath
    updated_at     = (Get-Date).ToString("s")
  }
  $newBest | ConvertTo-Json -Depth 5 | Out-File -Encoding utf8 $bestMetaPath
  Write-Host "NEW BEST MODEL -> deployed to $deployModelPath"
} else {
  Write-Host "No promotion. Current best composite score remains $bestScore"
}

Write-Host "Done. Run folder: $runRoot"
Write-Host "History: $historyPath"
Write-Host "Best metrics: $bestMetaPath"
