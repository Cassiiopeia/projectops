# Test window for `launch_cli.py desktop` (#985): text box, password box, checkbox, Next and Install buttons.
# The status label shows what happened, so the E2E test can read the result through UI Automation.
Add-Type -AssemblyName System.Windows.Forms
$form = New-Object System.Windows.Forms.Form
$form.Text = "PopsDesktopFixture"
$form.Width = 420; $form.Height = 300
$form.StartPosition = "Manual"; $form.Left = 200; $form.Top = 200
$form.TopMost = $true

$label = New-Object System.Windows.Forms.Label
$label.Text = "step 0"; $label.Name = "statusLabel"; $label.Left = 20; $label.Top = 20; $label.Width = 360
$form.Controls.Add($label)

$box = New-Object System.Windows.Forms.TextBox
$box.Name = "nameBox"; $box.AccessibleName = "Name"; $box.Left = 20; $box.Top = 55; $box.Width = 250
$form.Controls.Add($box)

$pw = New-Object System.Windows.Forms.TextBox
$pw.Name = "pwBox"; $pw.AccessibleName = "Password"; $pw.UseSystemPasswordChar = $true
$pw.Left = 20; $pw.Top = 90; $pw.Width = 250
$form.Controls.Add($pw)

$check = New-Object System.Windows.Forms.CheckBox
$check.Text = "Remember"; $check.Left = 20; $check.Top = 125
$form.Controls.Add($check)

$next = New-Object System.Windows.Forms.Button
$next.Text = "Next"; $next.Left = 20; $next.Top = 165
$next.Add_Click({
    $script:n++
    $label.Text = "step $script:n name=" + $box.Text + " remember=" + $check.Checked + " pwlen=" + $pw.Text.Length
})
$form.Controls.Add($next)

$install = New-Object System.Windows.Forms.Button
$install.Text = "Install"; $install.Left = 120; $install.Top = 165
$install.Add_Click({ $label.Text = "installed" })
$form.Controls.Add($install)

$script:n = 0
[void]$form.ShowDialog()
