param([Parameter(Mandatory=$true)][string]$Directory, [int]$FrameCount = 1)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
function Convert-OneBitmap([string]$Source, [string]$Destination) {
    # Keep the decoder's stream alive until Save completes, then release both
    # native GDI+ memory and the file handle before opening the next capture.
    $stream = $null
    $bitmap = $null
    try {
        $stream = [System.IO.File]::OpenRead($Source)
        $header = New-Object byte[] 14
        if ($stream.Read($header, 0, 14) -ne 14 -or
            $header[0] -ne 66 -or $header[1] -ne 77 -or
            [BitConverter]::ToUInt32($header, 2) -gt $stream.Length) {
            throw 'Invalid or truncated BMP header/data'
        }
        $stream.Position = 0
        $bitmap = [System.Drawing.Image]::FromStream($stream)
        $bitmap.Save($Destination, [System.Drawing.Imaging.ImageFormat]::Png)
    } catch {
        Write-Warning "Skipping invalid BMP '${Source}': $($_.Exception.Message)"
    } finally {
        if ($null -ne $bitmap) { $bitmap.Dispose() }
        if ($null -ne $stream) { $stream.Dispose() }
    }
}
# Enumerate paths only; never retain decoded images in a pipeline/collection.
foreach ($source in [System.IO.Directory]::EnumerateFiles(
        (Resolve-Path -LiteralPath $Directory).Path, '*.bmp',
        [System.IO.SearchOption]::AllDirectories)) {
    $destination = [System.IO.Path]::ChangeExtension($source, '.png')
    if (-not (Test-Path -LiteralPath $destination)) {
        Convert-OneBitmap $source $destination
    }
}
if ($FrameCount -gt 1) {
    $destination = Join-Path $Directory 'sheet.png'
    if (Test-Path -LiteralPath $destination) { return }
    $sheet = $null
    $graphics = $null
    try {
        $sheet = New-Object System.Drawing.Bitmap(800, (113 * [int][Math]::Ceiling($FrameCount / 4.0)))
        $graphics = [System.Drawing.Graphics]::FromImage($sheet)
        try {
            $graphics.Clear([System.Drawing.Color]::Black)
            for ($i = 0; $i -lt $FrameCount; $i++) {
                $source = Join-Path $Directory ('frame_{0:D2}/backbuffer.png' -f $i)
                if (-not (Test-Path -LiteralPath $source)) {
                    Write-Warning ('Missing backbuffer: frame_{0:D2}' -f $i)
                    continue
                }
                $bitmap = $null
                try {
                    $bitmap = [System.Drawing.Image]::FromFile($source)
                    $graphics.DrawImage($bitmap, [int](($i % 4) * 200), [int]([Math]::Floor($i / 4.0) * 113), 200, 113)
                } finally { if ($null -ne $bitmap) { $bitmap.Dispose() } }
            }
        } finally {
            if ($null -ne $graphics) { $graphics.Dispose(); $graphics = $null }
        }
        $sheet.Save($destination, [System.Drawing.Imaging.ImageFormat]::Png)
    } finally {
        if ($null -ne $graphics) { $graphics.Dispose() }
        if ($null -ne $sheet) { $sheet.Dispose() }
    }
}
