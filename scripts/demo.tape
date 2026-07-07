# excubitor crash-test demo → animated GIF, via charmbracelet/vhs (https://github.com/charmbracelet/vhs).
#
# The committed scripts/demo.svg is a static, always-regenerable frame (no tooling needed). This tape
# is the OPTIONAL animated version: install vhs, then
#
#   vhs scripts/demo.tape        # writes scripts/demo.gif
#
# It records a real run of scripts/demo.sh — same shipped guard code, same stdin→decision contract.
Output scripts/demo.gif

Set Shell bash
Set FontSize 15
Set Width 1180
Set Height 780
Set Padding 18
Set Theme "Github Dark"

Hide
Type "clear" Enter
Show
Sleep 400ms
Type "./scripts/demo.sh" Sleep 500ms Enter
Sleep 9s
