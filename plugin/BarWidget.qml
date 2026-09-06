import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
    id: root
    moduleName: "local.omnishot"
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight
    property var status: ({})
    property double now: Date.now() / 1000
    readonly property bool recording: status.recording === true && now - (status.updated || 0) < 4
    readonly property bool showTime: status.show_time !== false
    readonly property string elapsed: String(Math.floor((status.seconds || 0) / 60)).padStart(2, "0") + ":" + String((status.seconds || 0) % 60).padStart(2, "0")
    IpcHandler {
        target: "local.omnishot"
        function state(): string { return JSON.stringify({path: stateFile.path, recording: root.recording, show_time: root.showTime, text: button.text, width: button.width, clock: root.now, status: root.status}) }
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
    WidgetButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        text: root.recording ? (root.status.paused ? "Ⅱ " : "● ") + (root.showTime ? root.elapsed : "") : "󰄀"
        tooltipText: root.recording ? "OmniShot recording — click to stop, right click to pause/resume" : "OmniShot — Capture & Annotate"
        foreground: Color.accent
        fixedWidth: root.bar && root.bar.vertical ? -1 : Style.space(root.recording && root.showTime ? 85 : 27)
        fixedHeight: root.bar && root.bar.vertical ? Style.space(26) : -1
        onPressed: function(b) {
            if (root.bar) root.bar.run(root.recording ? (b === Qt.RightButton ? "omnishot pause" : "omnishot stop") : "omnishot menu")
        }
    }
}
