# OmniShot user guide

## Use

Click the camera icon in the Omarchy bar, or press **Print**.

| Shortcut | Action |
|---|---|
| Print | Capture menu |
| Ctrl + Print | Capture area |
| Shift + Print | Capture focused display |
| Super + Shift + Print | Scrolling capture |
| Alt + Print | Screen recording |
| Super + Ctrl + Print | Capture text |

Super + Print keeps Omarchy's existing color picker.
Print, Alt + Print, and Super + Ctrl + Print replace the corresponding stock
screenshot, screen recording, and OCR commands. Configuration is backed up first.

Settings → Shortcuts can also assign **Capture area & copy/save/annotate/pin**
and **Annotate last screenshot**. Area shortcuts perform their named action plus
the screenshot actions selected in General. Disable “Also run After Capture
actions with area shortcuts” to perform only the named action. Explicit CLI/URL
`action` parameters continue to select only that action. Annotate last screenshot
reopens its editable annotations and skips newer imported files, clipboard images
and recordings.

You can assign separate **Capture text with line breaks** and **Capture text
without line breaks** shortcuts. These override the OCR preference for that
capture; the original Capture text shortcut follows your preference. The same
actions are available as `omnishot ocr-lines` and `omnishot ocr-single-line`.

### Scrolling capture

1. Open scrolling capture and drag around the scrolling content.
2. Click **Start Capture**.
3. Scroll manually, or click **Auto-Scroll**. Keep the pointer inside the capture.
4. Click **Done** to open the corner preview.
5. Choose **Annotate**, **Copy**, **Save**, **Pin**, or drag the image into another app.

Before starting, drag the selection's edges to resize or its top grip to move.
Hold Shift while resizing to preserve proportions. After clicking the frame,
arrow keys move it and Ctrl+arrows resize it; add Shift for ten-pixel steps.
The frozen selection also supports these keys and links its exact width/height
fields when an aspect ratio is selected.

Swipe a preview sideways to dismiss it or down to temporarily hide it. Its context
menu opens a larger preview; videos play silently while hovered. Rotate, flip,
scale new captures to 1×, rename, Save All, and Move to Trash are available there.
Automatically saved captures also show a Trash button. It moves their unchanged
saved files to Trash; files edited or replaced outside OmniShot are kept.
Trash retains a portable editable project for recovery, including edits to imported
recordings. Restore the folder from your desktop Trash and open its `.omnishot`
or `.omnishot-video` file. While hovering a preview,
use Ctrl+C to copy, Ctrl+S to save, Ctrl+E to annotate, Ctrl+P to pin, Ctrl+W
to close, or Space for a larger preview. Existing global shortcuts take precedence.
These actions preserve focus in your current app. Save writes directly to the
configured folder; Save As opens a destination dialog. Enable “Ask for a
destination when saving” in Quick Access settings to always show that dialog.
Alt-click Save reverses that preference for one save. Successful drags close the
preview by default; hold Alt as you begin dragging to keep it open. Quick Access
settings can disable close-after-drag or save captures automatically on timeout.
General settings provide separate screenshot and recording columns, so copying,
saving, editing and retaining the preview can happen together.
The clipboard can offer a file and image together, or either representation
alone. Copied images and recordings use independent snapshots that survive later edits or
history deletion and are retained for the configured history period.
**From clipboard** opens copied local image, video or project files. Clipboard
images retain transparency and their embedded color profile.
Advanced settings customize capture filenames with clickable/draggable date,
time, window, app, random and sequence tokens. UTC and an optional naming prompt
are available; exported files use these names while history keeps stable IDs.
In the naming prompt, **Discard** removes the new screenshot or recording before
any copy, save, pin, editor or preview action runs. **Cancel** keeps its automatic
name. Invalid names stay in the dialog for correction.
Screenshot settings include automatic 1× scaling, an optional 1 px inner border,
crosshair/magnifier controls and remembering the All-In-One selection. With
Freeze screen disabled, All-In-One shows changing desktop content and a live
magnifier, then captures the current image when you confirm. Enable Freeze to
keep the frame from when selection began. Hold Shift when confirming a selection
to skip its automatic background preset, or Ctrl to additionally copy the result.
All-In-One has direct Area, Fullscreen, Window, Scrolling, Timer, OCR and Recording
buttons beside the exact dimensions. Select an area and click its capture mode,
or use Enter for the current mode. Fullscreen needs no selection; Window lets you
point to a window or cycle with Tab. Right-click Scrolling for horizontal capture.
Ctrl+C captures directly to the clipboard. Timer shows a countdown with Cancel
and an Escape shortcut while your source app keeps focus. The standalone Self
Timer command also selects the area first, then starts the countdown; it captures
current pixels even when screen freezing is enabled.
Annotate preferences control arrow direction, pencil smoothing, shadows and
automatic canvas expansion. Alt reverses the arrow direction while drawing.
Expansion is preserved in editable projects; an explicit crop fixes the current
image's canvas and can be followed by re-enabling expansion from Edit.

Horizontal scrolling is available from the capture menu. If content cannot be
aligned, automatic scrolling pauses with a message. Captures stop growing at
120 megapixels. Slow down or scroll back slightly after a failed alignment.

### Annotate

The toolbar offers arrows, line, rectangle, filled rectangle, ellipse, pencil,
highlighter, text, numbered counters, blur, pixelation, solid concealment and
spotlight. Hover a tool to see its name and shortcut. Shift constrains proportions;
Ctrl + wheel zooms. Hold Space and drag to pan a zoomed image, including during
a crop; releasing Space restores the active tool. Smart Highlighter adjusts to the text line’s height; hold
Ctrl while drawing to keep your chosen rectangle without text snapping.
Select a highlight and open its color picker to change opacity. New highlights
start at about 39% opacity; saved projects retain their previous appearance.
Select an annotation to move or resize it. Arrows can be selected and dragged
from their shaft or arrowhead. New standard arrows have a tapered shaft; existing
projects retain their previous shape. Double-click text
to edit it. Drag any resize handle or an arrow endpoint. Shift-resizing a shape
keeps its proportions and the opposite edge or corner fixed; side handles grow
around the perpendicular center. Shift locks movement
to one axis, and Alt-drag duplicates objects. Arrow keys nudge selections. Undo/redo, crop, resize, rotate, flip, combine, backgrounds, clipboard,
file export and multipage printing are available in the editor.
Ctrl+C copies selected annotations as editable objects; Ctrl+V pastes them as a
selected group with one undo step. Text, transforms, styles, freehand paths and
embedded images are preserved. With nothing selected, Ctrl+C copies the full
image, as does the toolbar Copy button. Other applications receive the full
rendered image when copying annotations. Annotation clipboard data and its PNG representation remain available after
closing or quitting OmniShot, until the clipboard is replaced.
Text presets are Standard, Rounded, Monospaced, Outlined, Boxed, Rounded Boxed,
and Monospaced Boxed. Rounded presets include the offline Nunito font. Long
words wrap within narrow text boxes; changing fonts or sizes reflows the text.
Existing projects retain their older text styles, shown as legacy entries when
selected.
Click the color swatch for an integrated saturation/brightness field, hue and
opacity sliders, Hex/RGB values, and saved colors. Changes preview live and close
as one undo step. Add favorites explicitly with **Add to My Colors**; right-click
a favorite to remove it. The screen eyedropper can sample the captured image
while the editor remains visible. Escape cancels sampling.
Spotlight supports rectangular, rounded, and elliptical openings. Choose the shape,
set corner radius for rounded rectangles, and drag the dimming slider to adjust
the surrounding image. A slider drag is one undo step. Selected spotlights retain
ordinary movement and resizing. Transparent areas retain their alpha in both the
preview and export, including after rotation/crop.
Crop opens an adjustable session with eight handles, a thirds grid, exact pixel
dimensions and aspect ratios. Click **Image size** for pixel width and height;
choose **Custom** for editable ratio fields. The fill swatch offers automatic,
transparent, or custom expansion color, including opacity and the screen
eyedropper. Fill colors use the same saved favorites as annotation colors.
Move or resize the frame, then click **Crop** or
press Enter. Escape or **Cancel** restores the image and annotations from before
the session, including provisional rotation/flips. **Revert to Original** restores
the source image and maps current annotations back to it. Click Crop to keep
the restoration, or Cancel to return to the cropped state. New editable projects
and history drafts retain this ability across sessions, including after rotation,
flipping and resizing. Legacy projects can restore only the pixels they contain.
Enable **Snap to edges** or hold Ctrl while dragging to
snap to the canvas or inserted-image edges. Drag past the image to expand it;
a uniform border color fills the added area, otherwise it stays transparent.

Window captures use desktop or custom wallpaper from Settings → Wallpaper.
Hold Shift when selecting a window for transparency. Tab switches between windows,
including windows behind another window. The captured background remains editable.
Text is edited directly on the image. Backgrounds include gradients, custom
images, padding, shadows and aspect ratios. PNG, JPEG, WebP and HEIC are supported.
Edits to captures are retained when you reopen them from History. Imported files
also appear there; history keeps a local copy and leaves the external original alone.
History uses a horizontal thumbnail strip with All, Screenshots, Videos and GIFs
tabs. Use the arrow keys or scroll gesture to browse, Ctrl-click or Shift-click
to select several captures, and Restore to bring their previews back. Double-click
opens an editor; Ctrl+F searches filenames. The actions menu includes Pin, Delete
and Clear History. Clearing asks for confirmation and preserves external files.

In Annotate, Alt-click **Save as…** to save directly to your configured capture
folder and keep editing. Repeated saves receive a new filename. Ordinary Save As
opens the destination chooser in the last folder used for an image export.

Save an `.omnishot` project to preserve the original and editable annotations.
Project files retain the source image; share an exported PNG/JPEG/WebP when
concealing information. Solid concealment removes covered pixels from the export.

Settings → Annotate includes a **Pin shortcut** for the current edited image.
Saving applies it to open editors; clearing it disables the shortcut. Modified
shortcuts can finish inline text and pin it immediately. Unmodified letter keys
continue to type normally while editing text.

Pinned images stay above other windows. Scroll to resize; two-finger scrolling
or Alt+scroll changes opacity. Lock makes the image click through, with a small
Unlock control. Middle-click closes an unlocked pin. Settings → Shortcuts can
assign **Hide/show pinned images** and **Close all pinned images**. Hide/show
preserves position, size, opacity and locks; closing pins keeps their History.

### Record

The video editor keeps the preview beside a tool sidebar, with playback and
editable tracks below. Choose Cursor, Keystrokes, Audio, Camera, Background, Motion,
Trim or Export to adjust that part of the recording. Gradient swatches and
appearance controls update the preview directly. Space plays/pauses; Ctrl+S
exports and Ctrl+Shift+S saves an editable project.
Ctrl+Z undoes a completed edit; Ctrl+Shift+Z or Ctrl+Y redoes it. The header
buttons provide the same actions. Timeline and slider drags form one undo step;
Escape cancels a drag. Undo restores timeline, appearance, audio and export
settings together. The session keeps up to 100 steps; a new edit clears redo.
Cursor settings use a size multiplier slider, three Arrow/Rounded Arrow/Dot
tiles, and Natural/Smooth motion buttons. The More cursor options button opens
Effects for fill/outline colors and Crosshair. A selected Crosshair remains
visible in the inspector, including after undo or project reopening. The tiles
reflect the colors used in preview and export. The multiplier uses 28
source pixels as 1×; existing projects retain their pixel sizes.
Press effect briefly compresses the cursor on a recorded click. Ripple animation
controls the growing, fading click highlight. Enable either or both; these
choices are preserved with the editable recording and applied during export.
The timeline shows source thumbnails with zoom segments above them. Use the
minus/plus slider or Ctrl+wheel to zoom, and the scrollbar or wheel to pan.
Ctrl+0 fits the recording. Drag clip edges to adjust trim, cuts or zooms; hold
at an edge to scroll farther, or press Escape to cancel the drag. Seeking
resumes playback only if it was playing before the drag.
Press B or click the bottom scissors button, then click the video strip to
split a clip. Ctrl+B splits at the playhead. Escape returns to selection.
Select a clip and press Delete to omit it from playback and export; select
the resulting cut range and press Delete again to restore it. Right-click
a boundary and choose Remove split to merge adjacent clips.
Select a clip to reveal its edge handles. Drag inward to trim to a video frame,
or outward to restore material up to a neighboring split or retained clip.
The omitted ranges remain visible on the source-time ruler and are skipped
during playback and export. Each drag is one undo step; Escape cancels it.
The preview’s expand button, F11 or a double-click opens full-screen playback
on the editor’s display. Escape, F11, double-click or Exit returns to the editor
without resetting playback or edits. Space plays/pauses; Left/Right step frames,
Shift+Left/Right seek one second, and Home/End seek to the trim boundaries.
Controls and the pointer hide during playback and reappear on movement.

Keystrokes has a size slider, Dark/Light styles, nine-position placement and
command-only/all-keys display options. More options retains font, duration and
custom colors. Display filtering is reversible; a recording captured with only
command shortcuts cannot restore ordinary typing that was never recorded.
These changes participate in undo/redo and are retained in editable projects.

On Intel GPUs, Qt video previews default to software decoding to avoid a
reproduced VAAPI surface-transfer crash during rapid seeks. Capture and export
hardware encoding remain available. An explicitly configured
`QT_FFMPEG_DECODING_HW_DEVICE_TYPES` takes precedence over this default.

Choose area, window or fullscreen; MP4/GIF; FPS; quality; microphone and system
audio with source selection and a microphone level meter. Controls support
pause/resume, stop, restart, hide and cancel. Recording preferences remember the
area, countdown, control visibility, outside dimming and Do Not Disturb. Video
resolution limits and 1× scaling are independent of GIF size, frame rate,
quality and optimization. Audio can use a combined track or separate mono/stereo
tracks. New Studio recordings retain microphone and system sources separately.
The Audio tool gives each source an inclusion toggle and 0–200% volume; exported
mixes include both sources at their chosen levels. Original tracks remain in the
editable project. Preview streams the same mix locally and follows playback,
seeking, cuts, speed and stereo-to-mono changes. Older recordings and imported
files retain their previous audio behavior; enable **Mix audio tracks** to use
individual source controls. Imported tracks use their own names or numbered labels.
Already mixed audio cannot be separated afterward. GIF switching
retains the MP4 audio edits. The bar can show elapsed time: click
to stop, or right-click to pause/resume. The tray menu also offers these commands.

Studio mode retains separate screen, cursor, click, keystroke and camera data.
The saved recording includes selected effects; the source remains available for
editing. The video editor has draggable trim, zoom and cut tracks, cursor
smoothing and styles, editable camera framing, gradient/image backgrounds, motion blur, speed and MP4/GIF
export. Camera placement has a nine-position grid, square/circle framing and
an optional shrink-during-zoom effect. During recording, click the camera overlay
to fill the capture area, click again or press Escape to return, and drag to move
it. Right-click the overlay to choose Circle, Square, Rounded or Rectangle.
Placement, fullscreen and shape changes replay in the saved recording, with pauses
removed. Set the camera width from 10–80% beside its shape in recording setup; the last
accepted size is remembered and bounded to fit small areas. Its recorded
placement scales with the exported video.
In Camera, clear **Use recorded camera framing** to use one framing throughout;
**Fullscreen camera** fills the frame throughout. Live fullscreen requires preview
exclusion; captures spanning displays retain an outside-area preview.
Save an `.omnishot-video` project to bundle the original screen track,
camera track, input metadata and edits in one portable local file.
Use Effects to style cursors, clicks, keystrokes and the camera. Edit input events
to hide clicks or change individual keystroke labels and timing. New Studio
recordings create automatic zooms from captured clicks, including when visible
click effects are off. Keyboard capture still follows its recording preference.
Click or drag an empty part of the zoom track to add a zoom. Select a zoom to
adjust its level, apply that level to all zooms, or choose Follow Cursor/Manual
in the inline inspector. Drag or resize the manual focus frame; arrow keys nudge
it and Shift moves farther. Escape cancels an active framing or timeline drag.
Adjacent zooms transition directly between their framing targets. Animation
Settings opens the Motion tool with Smooth/Dynamic choices. Motion Blur has
None, Low, Medium and High settings. Cursor and zoom blur appear in both preview
and export, and reset at cut boundaries. Ctrl+Shift+B splits
a zoom at the playhead; its context menu also offers Duplicate and Remove.
Delete/Backspace removes a selected zoom. Double-click still opens precise
timing and focus values. Hardware H.264 export is verified on this machine.

Recording controls and the camera preview remain visible without appearing in
single-display recordings. An on-demand Hyprland component creates a separate
capture image containing the content underneath those controls. Selections
spanning displays currently use hidden or outside-region controls.

## Install / update

Follow the [installation instructions](../README.md#install) for supported
versions, the complete package list, and first-time setup in `~/projects/omnishot`.
OmniShot is a desktop application with a companion shell widget; `omarchy plugin
add` alone cannot install its Python environment and native helpers. Python
dependencies are isolated in the checkout's `.venv`.

Run the installer as your desktop user, without sudo, inside an unlocked Omarchy
session. For an update, finish capture/recording and save/close editable windows first:

```sh
omnishot quit
cd ~/projects/omnishot
git pull --ff-only
bash install.sh
omnishot menu
```

The installer adds a launcher, desktop entry, shell bar widget and user-owned
Hyprland rules/bindings. It never edits `/usr/share/omarchy/`. Existing user
configuration backups are under `backups/<timestamp>/` (excluded from Git).
Widget updates refresh the Omarchy shell when the QML changes, avoiding stale
components in its live cache. The desktop entry handles local images, editable
projects, GIF/MP4/WebM/MOV/MKV recordings and `omnishot://` URLs. File managers
can offer OmniShot through Open With; existing default image and video apps
are preserved. Global shortcuts can be changed in Settings.
Settings → Shortcuts includes **Save all previews** and **Close all previews**.
Save All asks for a folder and closes successfully saved previews. Close All
keeps captures in History; Restore brings back the most recently closed preview.

The clean recording component checks the running Hyprland ABI before loading.
Re-run the installer after compositor upgrades; restart the session if the running
compositor and installed headers differ. It activates only during recording and
automatically deactivates if the recording application exits.

The application's installer also updates the widget; `omarchy plugin update`
does not update this checkout. Captures and editable projects remain in history.

The source checkout and `.venv` must remain at their installed location.
User captures, history, settings and editable exports live under
`$XDG_DATA_HOME/omnishot` (normally `~/.local/share/omnishot`). Normal file exports
default to `~/Pictures/OmniShot`; change this in Settings.

## CLI

```sh
omnishot menu
omnishot all-in-one
omnishot area --action annotate
omnishot area-annotate
omnishot last-screenshot
omnishot scroll
omnishot scroll-horizontal
omnishot fullscreen --action copy
omnishot area --geometry '100,100 800x600'
omnishot open /absolute/path/image.png
omnishot history
omnishot save-all
omnishot close-all
omnishot toggle-pins
omnishot close-pins
omnishot record
omnishot pause
omnishot restart
omnishot stop
omnishot scroll-done
```

Coordinates are Hyprland logical pixels. Image pixels retain native capture
resolution. Commands are delivered to one running instance using a user-only
local socket.
For example, `omnishot 'omnishot://capture-area?action=annotate'` opens the area
workflow. URL coordinates follow the reference API's lower-left convention;
CLI `--geometry` uses Hyprland's upper-left convention.
`omnishot timer --delay 5 --action annotate` selects an area, waits five seconds,
and opens Annotate. Scrolling URLs treat `start` and `autoscroll` independently:
`omnishot://scrolling-capture?start=false&autoscroll=true` waits for Start Capture,
then scrolls automatically; `start=true&autoscroll=false` starts capture and waits
for you to scroll.
`omnishot 'omnishot://open-settings?tab=about'` opens About with the installed
version. Settings links support `general`, `wallpaper`, `shortcuts`, `quickaccess`,
`recording`, `screenshots`, `annotate`, `advanced`, `about`, and `text`.
Every page follows the active Omarchy theme.
Text links accept `filepath` or screen coordinates, plus `linebreaks=true|false`;
omitting `linebreaks` uses the saved OCR preference. A coordinate-based
`record-screen` link opens recording setup and uses that region when you press
Record. Both workflows have been verified through the installed link handler.
