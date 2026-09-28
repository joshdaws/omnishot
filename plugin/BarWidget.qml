import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
    id: root
    moduleName: "io.github.joshdaws.omnishot"
    ipcTarget: "io.github.joshdaws.omnishot"
    manageIpc: false
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight
    property var status: ({})
    property double now: Date.now() / 1000
    property int selectedIndex: 0
    property bool cursorActive: false
    property string pendingCommand: ""
    // Installed with `omarchy plugin add`, this folder's parent is a git
    // checkout; scripts/setup.sh builds it into the app folder and stamps the
    // commit. A manual install.sh copy has no .git, so these stay inactive.
    readonly property string pluginRoot: decodeURIComponent(Qt.resolvedUrl("..").toString().replace(/^file:\/\//, "")).replace(/\/$/, "")
    readonly property string dataHome: Quickshell.env("XDG_DATA_HOME") || Quickshell.env("HOME") + "/.local/share"
    property string pluginHead: ""
    property string builtHead: ""
    readonly property bool managed: pluginHead !== ""
    readonly property bool setupNeeded: managed && builtHead === ""
    readonly property bool updateReady: managed && builtHead !== "" && builtHead !== pluginHead
    readonly property bool recording: status.recording === true && now - (status.updated || 0) < 4
    readonly property bool showTime: status.show_time !== false
    readonly property string elapsed: String(Math.floor((status.seconds || 0) / 60)).padStart(2, "0") + ":" + String((status.seconds || 0) % 60).padStart(2, "0")
    readonly property var actions: {
        if (setupNeeded) return [{label: "Finish setup", command: "@setup"}]
        var items = updateReady ? [{label: "Apply update", command: "@setup"}] : []
        items = items.concat(recording ? [
            {label: "Stop recording", command: "stop"},
            {label: status.paused ? "Resume recording" : "Pause recording", command: "pause"}
        ] : [])
        return items.concat([
            {label: "All-in-one", command: "select"},
            {label: "Capture area", command: "area"},
            {label: "Capture window", command: "window"},
            {label: "Capture display", command: "fullscreen"},
            {label: "Scrolling capture", command: "scroll"},
            {label: "Horizontal scroll", command: "scroll-horizontal"},
            {label: "Previous area", command: "previous"},
            {label: "Self timer", command: "timer"},
            {label: "Record screen", command: "record"},
            {label: "Capture text", command: "ocr"},
            {label: "Open image", command: "open"},
            {label: "From clipboard", command: "clipboard"},
            {label: "History", command: "history"},
            {label: "Settings", command: "settings"},
            {label: "Restore preview", command: "restore"},
            {label: "Show / hide pins", command: "toggle-pins"},
            {label: "Save all previews", command: "save-all"},
            {label: "Close all previews", command: "close-all"},
            {label: "Unlock pins", command: "unlock-pins"},
            {label: "Close all pins", command: "close-pins"},
            {label: "Quit OmniShot", command: "quit"}
        ], managed ? [{label: "Uninstall OmniShot", command: "@uninstall"}] : [])
    }
    function shellQuote(value) { return "'" + value.replace(/'/g, "'\\''") + "'" }
    function runScript(name) {
        // Setup may ask for a password (omarchy pkg add), so it needs a terminal.
        Quickshell.execDetached(["omarchy-launch-floating-terminal-with-presentation",
            "bash " + shellQuote(pluginRoot + "/scripts/" + name + ".sh")])
    }
    function activate(index) {
        if (index < 0 || index >= actions.length || launchTimer.running) return
        pendingCommand = actions[index].command
        close()
        // Let the shared panel's 140 ms fade finish before capture begins.
        launchTimer.restart()
    }
    function revealSelection() {
        var item = actionButtons.itemAt(selectedIndex)
        if (!item) return
        var top = item.mapToItem(column, 0, 0).y
        if (top < scroll.contentY) scroll.contentY = top
        else if (top + item.height > scroll.contentY + scroll.height)
            scroll.contentY = top + item.height - scroll.height
    }
    onOpenedChanged: if (opened) {
        headProcess.running = true
        stampFile.reload()
        selectedIndex = 0
        cursorActive = false
        scroll.contentY = 0
    }
    onActionsChanged: selectedIndex = Math.min(selectedIndex, actions.length - 1)
    onSelectedIndexChanged: if (cursorActive) revealSelection()
    IpcHandler {
        target: root.ipcTarget
        function state(): string { return JSON.stringify({panelApi: 1, opened: root.opened, visible: panel.visible, recording: root.recording, text: button.text, width: button.width, selected: root.selectedIndex, actions: root.actions, cardX: panel.cardOrigin.x, cardY: panel.cardOrigin.y, cardWidth: panel.contentWidth, cardHeight: panel.contentHeight, managed: root.managed, pluginRoot: root.pluginRoot, pluginHead: root.pluginHead, builtHead: root.builtHead}) }
        function open(): void { root.open() }
        function close(): void { root.close() }
        function toggle(): void { root.toggle() }
    }
    FileView {
        id: stateFile
        path: Quickshell.env("XDG_RUNTIME_DIR") + "/omnishot-status.json"
        printErrors: false
        watchChanges: true
        onFileChanged: reload()
        onLoadFailed: root.status = ({})
        onLoaded: {
            try { root.status = JSON.parse(text()) } catch (e) { root.status = ({}) }
        }
    }
    Timer { interval: 1000; running: true; repeat: true; onTriggered: { root.now = Date.now() / 1000; stateFile.reload() } }
    Process {
        id: headProcess
        running: true
        // Only this folder's own checkout; ~/.config may itself be a dotfiles repo.
        command: ["sh", "-c", "[ -d \"$1/.git\" ] && git -C \"$1\" rev-parse HEAD", "sh", root.pluginRoot]
        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: root.pluginHead = text.trim()
        }
    }
    // `omarchy plugin update` moves HEAD without reloading this widget. The
    // stamp watch cannot fire for a file that did not exist when it started,
    // so poll quickly while setup or an update is pending.
    Timer { interval: root.setupNeeded || root.updateReady ? 2000 : 60000; running: root.managed; repeat: true; onTriggered: { headProcess.running = true; stampFile.reload() } }
    FileView {
        id: stampFile
        path: (Quickshell.env("OMNISHOT_INSTALL_DIR") || root.dataHome + "/omnishot-app") + "/.omnishot-source"
        printErrors: false
        watchChanges: true
        onFileChanged: reload()
        onLoadFailed: root.builtHead = ""
        onLoaded: root.builtHead = text().trim()
    }
    Timer {
        id: launchTimer
        interval: 220
        onTriggered: {
            if (root.pendingCommand.charAt(0) === "@") root.runScript(root.pendingCommand.slice(1))
            else Quickshell.execDetached([Quickshell.env("HOME") + "/.local/bin/omnishot", root.pendingCommand])
            root.pendingCommand = ""
        }
    }
    WidgetButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        text: root.recording ? (root.status.paused ? "Ⅱ " : "● ") + (root.showTime ? root.elapsed : "") : "󰄀"
        tooltipText: root.recording ? "OmniShot — " + (root.status.paused ? "Paused " : "Recording ") + root.elapsed
            : root.setupNeeded ? "OmniShot — Finish setup" : root.updateReady ? "OmniShot — Update ready" : "OmniShot — Capture & Annotate"
        foreground: root.recording ? Color.urgent : root.setupNeeded || root.updateReady ? Color.accent : root.barForeground
        fixedWidth: root.bar && root.bar.vertical ? -1 : Style.space(root.recording && root.showTime ? 85 : 27)
        fixedHeight: root.bar && root.bar.vertical ? Style.space(26) : -1
        onPressed: function(b) { if (b === Qt.LeftButton || b === Qt.RightButton) root.toggle() }
    }
    KeyboardPanel {
        id: panel
        anchorItem: button
        owner: root
        bar: root.bar
        open: root.opened
        focusTarget: keys
        contentWidth: panel.fittedContentWidth(Style.space(440))
        contentHeight: panel.fittedContentHeight(column.implicitHeight, Style.space(620))
        PanelKeyCatcher {
            id: keys
            anchors.fill: parent
            onCloseRequested: root.close()
            onTabRequested: function(direction) { root.switchPanel(direction) }
            onMoveRequested: function(dx, dy) {
                if (!root.cursorActive) { root.cursorActive = true; root.revealSelection(); return }
                root.selectedIndex = Math.max(0, Math.min(root.actions.length - 1, root.selectedIndex + dx + dy * 2))
            }
            onActivateRequested: root.activate(root.selectedIndex)
            Flickable {
                id: scroll
                anchors.fill: parent
                contentWidth: width
                contentHeight: column.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                flickableDirection: Flickable.VerticalFlick
                interactive: contentHeight > height
                Column {
                    id: column
                    width: scroll.width
                    spacing: Style.spacing.md
                    Text {
                        text: "OmniShot"
                        color: Color.foreground
                        font.family: Style.font.family
                        font.pixelSize: Style.font.title
                        font.bold: true
                    }
                    Text {
                        width: parent.width
                        text: root.recording ? (root.status.paused ? "Recording paused · " : "Recording · ") + root.elapsed
                            : root.setupNeeded ? "OmniShot needs to be built before first use. Setup opens a terminal and may ask for your password."
                            : root.updateReady ? "An update was downloaded. Apply it to rebuild OmniShot." : "Capture, annotate, and share."
                        color: root.recording ? Color.urgent : Qt.darker(Color.foreground, 1.4)
                        font.family: Style.font.family
                        font.pixelSize: Style.font.body
                        wrapMode: Text.WordWrap
                    }
                    PanelSeparator { width: parent.width }
                    Grid {
                        id: grid
                        width: parent.width
                        columns: 2
                        spacing: Style.spacing.xs
                        Repeater {
                            id: actionButtons
                            model: root.actions
                            Button {
                                required property var modelData
                                required property int index
                                width: (grid.width - grid.spacing) / 2
                                text: modelData.label
                                leftAlign: true
                                fontSize: Style.font.body
                                hasCursor: root.cursorActive && root.selectedIndex === index
                                onClicked: root.activate(index)
                                onHovered: function(hovered) {
                                    if (hovered) { root.cursorActive = true; root.selectedIndex = index }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
