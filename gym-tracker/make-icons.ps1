Add-Type -AssemblyName System.Drawing

function Create-Icon {
    param([int]$size, [string]$path)
    $bmp = New-Object System.Drawing.Bitmap($size, $size)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = 'AntiAlias'
    $g.Clear([System.Drawing.Color]::FromArgb(11, 12, 14))

    $amber = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 176, 32))
    $steel = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(138, 143, 152))
    $s = $size / 100.0

    function RoundRect([System.Drawing.Brush]$brush, [float]$x, [float]$y, [float]$w, [float]$h, [float]$r) {
        $gp = New-Object System.Drawing.Drawing2D.GraphicsPath
        $d = $r * 2
        $gp.AddArc($x, $y, $d, $d, 180, 90)
        $gp.AddArc($x + $w - $d, $y, $d, $d, 270, 90)
        $gp.AddArc($x + $w - $d, $y + $h - $d, $d, $d, 0, 90)
        $gp.AddArc($x, $y + $h - $d, $d, $d, 90, 90)
        $gp.CloseFigure()
        $g.FillPath($brush, $gp)
        $gp.Dispose()
    }

    # barbell: bar + inner big plates + outer small plates (amber), steel collars
    RoundRect $steel ($s*14) ($s*46.5) ($s*72) ($s*7) ($s*3)      # bar
    RoundRect $amber ($s*28) ($s*26) ($s*9)  ($s*48) ($s*4)       # big plate L
    RoundRect $amber ($s*63) ($s*26) ($s*9)  ($s*48) ($s*4)       # big plate R
    RoundRect $amber ($s*18) ($s*34) ($s*7)  ($s*32) ($s*3.5)     # small plate L
    RoundRect $amber ($s*75) ($s*34) ($s*7)  ($s*32) ($s*3.5)     # small plate R
    RoundRect $steel ($s*39) ($s*42) ($s*4)  ($s*16) ($s*2)       # collar L
    RoundRect $steel ($s*57) ($s*42) ($s*4)  ($s*16) ($s*2)       # collar R

    $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose()
    $bmp.Dispose()
    Write-Host "Created $path ($size x $size)"
}

Create-Icon -size 192 -path "$PSScriptRoot\icon-192.png"
Create-Icon -size 512 -path "$PSScriptRoot\icon-512.png"
Write-Host "Done! Icons ready."
